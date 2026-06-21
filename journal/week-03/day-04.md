# Week 03 Day 04

- Инварианты в `data/long/invariants.json` (9 id), отдельно от `short` и устава.
- LLM-валидатор (`invariant_validator.py`) — не regex; retry агента по `feedback_for_agent`.
- Demo adversarial: Марта после помойки, `break_invariant`, `[agent:invalid]` на видео.
- Checklist: финал ✓ + был ли REJECTED draft (sim «пробил» черновик).

**Вывод:** один `--demo --no-stream`; на записи видны invalid draft и retry.
