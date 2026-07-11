# Неделя 6, день 4 — оптимизация локальной LLM для RAG

## Задание

Оптимизировать локальный RAG ([day-03](day-03/)) под **`qwen3:4b`**: параметры генерации, контекст, промпт.

| Параметр | Значение |
|----------|----------|
| Модель | `qwen3:4b` (Q4 из коробки Ollama) |
| Temperature | **0** |
| num_ctx | **8192** |
| num_predict | **не задаём** (дефолт Ollama) |
| reasoning | **включён**, стрим `[thinking]` → `[rag-*]` / `[answer-rag]` |
| retrieve → rag | **12 → 3** |
| simple top_k | **6** |
| Контекст чанков | **≤1200 символов** |
| Промпт cite | **compact**, ответ текстом + цитаты и source_id в ответе |

Перевод RU→EN — облако (Dockhost), как в day-03.

## Результат

На видео — одна команда:

```bash
python weeks/week-06/day-04/main.py --demo
```

В stdout: translate `[cloud]`, retrieve, rerank, стрим `[thinking]` и ответ `[rag-*]` / `[answer-rag]`, метаданные чанков — по 2 вопросам (плоды в помёте, король медведя). В начале — строка с параметрами оптимизации.

## Подготовка

```bash
source .venv/bin/activate
pip install -r weeks/week-06/day-04/requirements.txt

ollama serve
ollama pull qwen3:4b
ollama pull nomic-embed-text
```

`.env`: `DOCKHOST_AI_KEY` (перевод).

Индекс week-05 (если нет):

```bash
python weeks/week-05/day-01/init_data.py
python weeks/week-05/day-01/main.py --index
```

## Команды

```bash
# smoke без LLM (перед коммитом)
python weeks/week-06/day-04/main.py --show-index

# проверка Ollama
python weeks/week-06/day-04/main.py --check

# один вопрос (оба режима)
python weeks/week-06/day-04/main.py --ask "Какие дикие плоды преобладали в помёте опоссумов осенью?"

# только cite или simple
python weeks/week-06/day-04/main.py --ask "…" --mode cite
python weeks/week-06/day-04/main.py --ask "…" --mode simple

# демо для видео
python weeks/week-06/day-04/main.py --demo
python weeks/week-06/day-04/main.py --demo --no-pause
```

## Структура

| Файл | Назначение |
|------|------------|
| `profiles.py` | оптимизированный профиль (`load_profile()`) |
| `llm.py` | `stream_local()` с GenOptions, think=true |
| `pipeline_cite.py` | retrieve → rerank → cite |
| `main.py` | CLI `--demo`, `--ask`, `--show-index` |

## Статус

- [x] Код готов
- [ ] Видео записано
- [ ] Ссылка в таблице курса
- [ ] Обновлён [submissions.md](../../../submissions.md)

## Артефакты

| Тип | Ссылка |
|-----|--------|
| Видео | |
| Код | `weeks/week-06/day-04/` |

## Заметки

- Первый запрос с rerank скачает CrossEncoder (~90 MB).
- qwen3: reasoning через native `/api/chat` (`think=true`, `stream=true`); thinking и answer выводятся по мере генерации.
- Для видео: `--demo --no-pause`.
