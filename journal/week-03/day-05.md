# Week 03 Day 05

- TikTok FSM «Хvostik Clips»: переход делает **волонтёр** (`complete_stage`), FSM ограничивает **агента**.
- Порядок хода: **user → classifier/FSM → agent** (агент видит уже применённый переход).
- Блок «Результат перехода» в prompt агента; denied → не вести следующий этап.
- Убраны document blocks, `validate_stage_close`, блокировка пользователя regex-ами.
- Demo: Саша, Тофик на шаре; первый ход — нарушение порядка.

**Проверка:** `pytest weeks/week-03/day-05/test_transitions.py`, `--show-memory`, `--demo --no-stream`.

**Видео:** intro, `[classifier] update_step/complete_stage`, `[transition] denied/allowed`, resume до done.
