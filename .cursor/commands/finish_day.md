# finish_day

Закоммитить и запушить задание дня в `master` (без PR). День определяется по `git status`.

## Перед коммитом

1. `ruff check weeks/week-NN/day-DD/` и один smoke-test `main.py` (см. `verify-after-code.mdc`).
2. Убедись, что `.env` не попадёт в коммит.

## Запуск

Из корня репозитория:

```bash
./scripts/finish_day.sh -m "Week N day D: краткое описание на английском."
```

- **`-m`** — сообщение коммита задания (стиль: `Week 2 day 1: simple LLM chat agent.`).
- Без `-m` — первый пункт из `## Задание` в README дня.
- **`-n`** — dry-run, без commit/push.

## Логика скрипта

1. День — по путям `weeks/week-NN/day-DD/` и `journal/week-NN/day-DD.md`.
2. Несколько дней в diff → ошибка, коммит вручную.
3. Прочие файлы (rules, AGENTS.md и т.д.) → отдельный коммит `Update repo config and tooling.`
4. Файлы задания → коммит с `-m`.
5. `git push origin master`.

## Результат

Сообщи пользователю **ссылку на коммит задания** — строка `DAY_COMMIT=...` из вывода. Extra-коммит упомяни кратко.

Нужны права `git_write` и сеть. Без amend и force-push.
