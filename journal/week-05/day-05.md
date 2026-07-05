# Week 5, day 05

- CLI RAG-чат: история в `chat_history.json`, RAG на каждый ход.
- Пайплайн: query processor → retrieve k=20 → rerank k=4 → JSON answer + sources; без rewrite и wide fallback.
- **Шаги 4–6 (RAG_PLAN):** Evidence/Conversation blocks в rag.py; rolling `recent_chunk_ids` + neighbor expansion; intent (follow_up/synthesis/new_topic); rerank sticky floor.
- Промпт: разговорный тон, до ~20 предложений; temperature 0.35.
- Сценарии: 2×12 реплик (экология Fitch + дядюшка Билли).
- Причесал тексты сценариев для видео: вопросы стали естественнее по-русски, но порядок и смысл 12 ходов сохранены.

**На видео:** `python weeks/week-05/day-05/main.py --scenario all --no-pause`.

**Smoke без API:** `--show-index`.

- **Run-log:** `logs/YYYYMMDD-HHMMSS-<mode>.log` — один запуск main.py → один файл; session/query/retrieve/rerank/rag; блоки `[llm_call:*]` с полными messages (system/user/assistant) и `[llm_response]`.
