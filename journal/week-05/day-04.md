# Week 5, day 04

- RAG day-04: JSON с `context_sufficient` + `clarification_hint` + answer + sources + citations.
- Post-normalize убран — модель сама формулирует «не знаю» и подсказку что уточнить.
- Fallback `[rag-wide]`: при insufficient или kept=0 — второй запрос на 20 cosine-чанках без rerank.
- `[verify]` / `[verify-wide]`; итог включает `wide fallback sufficient`.
- **Fix:** убраны учебные обрезки 600/1500 символов (day-02–04): в RAG и rerank — полный `text` чанка из индекса.

**На видео:** `python weeks/week-05/day-04/main.py --demo`.

**Smoke без API:** `--show-index`.
