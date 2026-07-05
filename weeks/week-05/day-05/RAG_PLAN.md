# Долгосрочный план: production multi-turn RAG (day-05)

Документ для пошаговых доработок. После каждого шага — прогон сценария,
смотрим stdout, правим следующий шаг.

**Тестовый кейс (регрессия follow-up):**

```
1. Какие дикие плоды преобладали в помёте опоссумов осенью?
2. А какой из них был на первом месте?   ← здесь ломалось
```

Команда: `python weeks/week-05/day-05/main.py --scenario 1 --no-pause`

---

## Проблема (зачем план)

В чате три источника информации — их нельзя смешивать:

| Источник | Роль | Можно цитировать? |
|----------|------|-------------------|
| Чанки из индекса | Факты из документов | Да (sources + citations) |
| История чата | Связность, местоимения | Нет |
| Знания модели | — | Нет (в grounded RAG) |

Сейчас на follow-up: история есть, но **retrieve** ищет по короткому
переводу без полноценного standalone-запроса → чанки не те → модель
говорит «не знаю», хотя на прошлом ходу ответила верно.

**Цель плана:** на каждый ход снова находить нужные чанки, даже если
вопрос — «а какой из них?».

---

## Целевая архитектура (production)

```
User (RU)
  → Session state (turns + last_query + last_chunk_ids)
  → Query processor → standalone_query_en, is_follow_up
  → Retrieve fusion (новый запрос + sticky при follow-up)
  → Rerank top-4
  → Generator (Evidence отдельно от Conversation)
  → Save session
```

---

## Todo: базовая реализация (день 5, v1)

- [x] CLI: `--chat`, `--scenario`, `--ask`, `--show-index`, `--clear`
- [x] История диалога: `chat_history.json` (turns: user + assistant + sources)
- [x] Пайплайн: translate → retrieve k=20 → rerank k=4 → structured RAG
- [x] Ответ с обязательными sources/citations (`context_sufficient=true`)
- [x] История в translate (разрешение местоимений при переводе)
- [x] История в RAG (последние 10 реплик в messages)
- [x] 2 сценария × 12 реплик (`scenarios.py`)
- [x] Вывод: `[user]` до пайплайна; превью вопросов в `--scenario`
- [x] Без query rewrite day-03 и без wide fallback day-04

---

## Todo: production-доработки (по порядку)

Внедрять **строго по номерам**. После каждого — дебаг, потом следующий.

### Шаг 1. Query processor

**Статус:** [x] сделано

**Что:** отдельный модуль `query.py` — не перевод, а **поисковый запрос**.

LLM получает историю + текущий вопрос (RU), возвращает JSON:

```json
{
  "standalone_query_en": "Which wild fruit ranked first in opossum scat in autumn?",
  "is_follow_up": true
}
```

**Правила:** самодостаточный EN-запрос для embed; местоимения разрешены;
не отвечать на вопрос.

**Куда встраивать:** `pipeline.py` — вместо `translate_to_en` для retrieve/rerank
(translate можно оставить для логов или убрать).

**Stdout:** `[query] standalone=… follow_up=true`

**Файлы:** новый `query.py`; правки `pipeline.py`, `console_out.py`

**Критерий готовности:** ход 2 сценария 1 — `standalone_query_en` содержит
opossum / wild fruit / scat / autumn; ответ «виноград» + sources не пустые.

---

### Шаг 2. Session state (метаданные retrieval)

**Статус:** [x] сделано

**Что:** расширить `chat_history.json` (или отдельный блок `session`):

```json
{
  "turns": [...],
  "session": {
    "last_standalone_query_en": "...",
    "last_chunk_ids": ["37199:009", "37199:010"]
  }
}
```

После каждого успешного хода сохранять:
- `last_standalone_query_en` из query processor;
- `last_chunk_ids` из `response.sources`.

**Файлы:** `history.py`, `chat.py`

**Критерий:** после хода 1 в JSON видны chunk_ids; после `--clear` session пуст.

---

### Шаг 3. Retrieve fusion

**Статус:** [x] сделано

**Что:** не один `retrieve(query)`, а объединение кандидатов:

1. `retrieve(standalone_query_en, k=20)` — основной проход
2. если `is_follow_up` и есть `last_standalone_query_en`:
   `retrieve(last_standalone_query_en, k=10)`
3. `fetch_chunks_by_id(last_chunk_ids)` — sticky
4. `dedupe_by_chunk_id` → общий пул → rerank

**Файлы:** `retrieve.py` (fetch_by_id, dedupe), `pipeline.py`

**Stdout:** `[retrieve] primary=20 sticky=2 fused=22 unique=18`

**Критерий:** на ходе 2 в `rag_hits` снова есть `37199:009` или `37199:010`.

---

### Шаг 4. Context assembly (Evidence vs Conversation)

**Статус:** [x] сделано

**Что:** в `rag.py` явно разделить блоки в финальном user-message:

```
=== Conversation (continuity only, NOT a factual source) ===
...

=== Evidence (ONLY source of facts; cite these) ===
--- chunk_id=... ---

=== Question ===
...
```

История — не в отдельных messages, а в блоке Conversation (или наоборот,
но граница должна быть явной в тексте промпта).

**Файлы:** `rag.py` (RAG_SYSTEM + `generate_with_rag`)

**Критерий:** модель не пишет «нет доступа к прошлому ответу»; факты только
из Evidence.

---

### Шаг 5. Grounding policy для follow-up

**Статус:** [x] сделано

**Что:** уточнить RAG_SYSTEM:

- follow-up при непустом Evidence → отвечать, не «не знаю»;
- «не знаю» только если Evidence реально не содержит ответа;
- запрет мета-объяснений про «другое исследование / нет доступа».

**Файлы:** `rag.py`

**Критерий:** ход 2 сценария 1 — ответ про виноград, sources ≥ 1.

---

### Шаг 6 (опционально). Intent / new topic

**Статус:** [x] сделано

**Что:** в query processor добавить `intent`: `new_topic` | `follow_up` |
`clarification`. При `new_topic` — не подмешивать sticky chunks.

**Когда:** если после шагов 1–5 sticky мешает смене темы в сценарии 2.

---

## Чеклист дебага после каждого шага

Смотреть в stdout на проблемном ходе:

| Метка | Что проверить |
|-------|----------------|
| `[user]` | Вопрос на русском виден до пайплайна |
| `[query]` / `[translate]` | Standalone EN полный, не «Which of them…» |
| `[retrieve]` | Достаточно кандидатов; sticky сработал |
| `[rerank]` | `kept≥1`, scores разумные (top ≥ 0.3 для явного попадания) |
| `[rag]` | `context=sufficient`, sources ≥ 1 |
| `[agent]` | Нет «не знаю» на уточняющем вопросе с теми же чанками |

---

## Карта файлов (текущая)

| Файл | Сейчас | После доработок |
|------|--------|-----------------|
| `main.py` | CLI | без изменений |
| `chat.py` | RagChat, run_turn | + обновление session |
| `history.py` | turns | + session block |
| `translate.py` | RU→EN + history | может остаться для логов или заменён query |
| `query.py` | — | **шаг 1** |
| `pipeline.py` | translate→retrieve→rerank | query + fusion |
| `retrieve.py` | cosine top-k | + fetch_by_id, dedupe |
| `rag.py` | JSON + history messages | Evidence/Conversation blocks |
| `scenarios.py` | 2×12 реплик | без изменений |

---

## Заметки по сессии (2026-07-05)

- Изначально без rewrite и wide fallback — осознанно.
- Температура RAG: 0.35; длина ответа до ~20 предложений.
- Баг follow-up воспроизведён на «А какой из них был на первом месте?».
- Следующий шаг для внедрения: **прогон сценария 1** — проверить follow-up «А какой из них…».
