# Week 5, day 05

- CLI RAG-чат: история в `chat_history.json`, RAG на каждый ход.
- Пайплайн: query processor → retrieve k=20 → rerank k=4 → JSON answer + sources; без rewrite и wide fallback.
- **Шаг 1 (RAG_PLAN):** `query.py` — standalone EN + `is_follow_up`, вся история в промпт; translate убран из pipeline.
- Промпт: разговорный тон, до ~20 предложений; temperature 0.35.
- Сценарии: 2×12 реплик (экология Fitch + дядюшка Билли).
- Причесал тексты сценариев для видео: вопросы стали естественнее по-русски, но порядок и смысл 12 ходов сохранены.

**На видео:** `python weeks/week-05/day-05/main.py --scenario all --no-pause`.

**Smoke без API:** `--show-index`.

**Регрессия follow-up:** два `--ask` подряд — ход 2 «А какой из них…» → `[query] follow_up=true`, виноград + sources 37199:009/010.
