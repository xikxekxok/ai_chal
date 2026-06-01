# AGENTS.md

Python 3.11+. Задание дня: `weeks/week-NN/day-DD/`. Работай только в активной папке дня, если пользователь не просит иначе.

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

Пути подставляй под текущий день.

## День задания

1. Код и файлы — в `weeks/week-NN/day-DD/`.
2. Зависимости дня — `requirements.txt` в той же папке.
3. После сдачи: README дня + [submissions.md](submissions.md).
4. Журнал: [journal/week-NN/day-DD.md](journal/) — кратко что сделали, проблемы, находки (см. `.cursor/rules/course-journal.mdc`).

## Boundaries

- Не коммитить `.env`, ключи, `*.mp4` и крупные файлы.
- Не трогать другие `week-* / day-*` без запроса.
- Минимальный diff, только текущее задание.
- Неделя 6+: VPS/локальные модели — только если пользователь просит.
