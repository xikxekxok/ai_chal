# Неделя 7, день 5

## Сделано

- CLI second brain: SQLite WAL + FTS5 bm25 + Ollama embeddings + RRF hybrid retrieve.
- Пайплайны save (LLM enrich → chunk → FTS/embed) и ask (expand → retrieve → two-stage pack → ответ).
- Команды: save/ask/search/list/show/stats/reindex/demo/clear; деградация FTS-only без Ollama.
- Demo: после каждого save печатает тело заметки через тот же `_print_note`, что и `--show`.

## Интересное

- Two-stage pack: карточки заметок + top-4 чанка — меньше токенов, чем полный dump.
- `[notes]` печатается из retrieve, не из «галлюцинаций» модели.
- Aliases в FTS помогают lexical recall при других формулировках.

## Проблемы

- Master был занят worktree → работа на ветке `feat/week-07-day-05` от свежего origin/master.

## Вывод

- Видео: `python weeks/week-07/day-05/main.py --demo`
- Smoke без API: `--stats`, `--list`, `--clear`
