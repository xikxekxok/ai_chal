# Week 5, day 02

- RAG day-02: retrieve по `opossum_index.json` (day-01), top-k=10 cosine; LLM через Dockhost.
- Слой перевода: вопрос RU → EN; ответ RU напрямую из LLM (без en→ru). Терминология: опossum, не енот.
- CLI: `--ask`, `--no-rag`, `--compare`, `--demo` (10 вопросов постранично), `--show-index`.
- Демо-вопросы: имена и сюжет — да; названия книг, Фитч, Канзас — нет (подсказки к source_id).

**На видео:** `python weeks/week-05/day-02/main.py --demo` — translate, retrieve, expect, RAG vs no-RAG.

**Smoke без API:** `--show-index`. Индекс не трогаем при finish_day.
