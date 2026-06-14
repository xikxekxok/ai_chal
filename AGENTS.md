# AGENTS.md

Инструкции для Cursor при работе в репозитории. Контекст курса и правила — [`.cursor/rules/`](.cursor/rules/) (главное: `ai-advent.mdc`, проверка после кода: `verify-after-code.mdc`).

## Setup

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pip install -r weeks/week-NN/day-DD/requirements.txt   # если есть
```

Секреты: `cp .env.example .env`, не коммитить `.env`.

## Commands

| | |
|---|---|
| Lint | `ruff check weeks/` |
| Format | `ruff format weeks/` |
| Test | `pytest weeks/ -q` |
| Run | `python weeks/week-NN/day-DD/main.py` |
| Finish day | `/finish_day` в чате или `./scripts/finish_day.sh -m "…"` |

Пути подставляй под текущий день. Slash-команда: [`.cursor/commands/finish_day.md`](.cursor/commands/finish_day.md).
