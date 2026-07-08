# Неделя 6, день 3 — локальный RAG с цитатами

## Задание

RAG-агент из [day-04 недели 5](../../week-05/day-04/) (rerank + обязательные цитаты) на **локальной генерации** (Ollama `qwen3:8b`). На каждый вопрос — два режима:

- **cite (5.4):** translate → retrieve k=20 → CrossEncoder rerank → top-4 → JSON с цитатами (+ wide fallback)
- **simple (5.2):** cosine top-10 → простой ответ RU без цитат

Перевод RU→EN — **облако** (Dockhost). Без query rewrite и без verify.

## Результат

На видео — одна команда:

```bash
python weeks/week-06/day-03/main.py --demo
```

В stdout: translate `[cloud]`, retrieve, rerank, `[local]` ответы cite и simple по 2 вопросам (плоды в помёте, король медведя).

## Подготовка

```bash
source .venv/bin/activate
pip install -r weeks/week-06/day-03/requirements.txt

ollama serve
ollama pull qwen3:8b
ollama pull nomic-embed-text
```

`.env`: `DOCKHOST_AI_KEY` (перевод), опционально `OLLAMA_CHAT_MODEL`, `OLLAMA_THINK=false`.

Индекс week-05 (если нет):

```bash
python weeks/week-05/day-01/init_data.py
python weeks/week-05/day-01/main.py --index
```

## Команды

```bash
# smoke без LLM (перед коммитом)
python weeks/week-06/day-03/main.py --show-index

# проверка Ollama
python weeks/week-06/day-03/main.py --check

# один вопрос (оба режима)
python weeks/week-06/day-03/main.py --ask "Какие дикие плоды преобладали в помёте опоссумов осенью?"

# только cite или simple
python weeks/week-06/day-03/main.py --ask "…" --mode cite
python weeks/week-06/day-03/main.py --ask "…" --mode simple

# демо для видео
python weeks/week-06/day-03/main.py --demo
python weeks/week-06/day-03/main.py --demo --no-pause
```

## Структура

| Файл | Назначение |
|------|------------|
| `llm.py` | `complete_local()` (Ollama), `complete_cloud()` (Dockhost) |
| `translate.py` | RU→EN через облако |
| `pipeline_cite.py` | retrieve → rerank → cite RAG |
| `rag_cite.py` | structured JSON с цитатами (локально) |
| `rag_simple.py` | простой RAG top-10 (локально) |
| `main.py` | CLI |

## Статус

- [x] Код готов
- [ ] Видео записано
- [ ] Ссылка в таблице курса
- [ ] Обновлён [submissions.md](../../../submissions.md)

## Артефакты

| Тип | Ссылка |
|-----|--------|
| Видео | |
| Код | `weeks/week-06/day-03/` |

## Заметки

- Первый запрос с rerank скачает CrossEncoder (~90 MB).
- `qwen3:8b` на CPU медленнее облака; `OLLAMA_THINK=false` обязателен.
