# Week 5, day 03

- RAG day-03: query rewrite (LLM) + CrossEncoder rerank (`ms-marco-MiniLM-L6-v2`) + порог `--min-score`.
- Retrieve k=20 → rerank/filter → rag k=4; режимы bare / rewrite / rerank / both.
- Демо: 10 вопросов из day-02 переписаны разговорно/косноязычно (сленг, слова-паразиты) — иначе rewrite был не нужен на уже хороших вопросах; translate сохраняет "мусор", rewrite его убирает.
- Демо: на экране все 4 режима + LLM-оценка точности (0–1) и рейтинг `[rating]`.

**На видео:** `python weeks/week-05/day-03/main.py --demo`.

**Smoke без API:** `--show-index`.
