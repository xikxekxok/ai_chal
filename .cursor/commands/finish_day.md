# finish_day

Закоммитить и запушить задание дня в `master` (без PR). День определяется по `git status`.

## Перед коммитом

1. `ruff check weeks/week-NN/day-DD/` и один smoke-test `main.py` (см. `verify-after-code.mdc`).
2. Убедись, что `.env` не попадёт в коммит.
3. **Все файлы дня в индексе:** `git status` — в `weeks/week-NN/day-DD/` и `journal/week-NN/day-DD.md` нет `??`. Перед скриптом: `git add weeks/week-NN/day-DD/ journal/week-NN/day-DD.md` — иначе `finish_day` может разнести staged/unstaged по разным коммитам.
4. **Сброс runtime в `data/`** (неделя 3 и stateful-дни): после `--demo` / `--chat` не коммить артефакты прогона — только seed.

   ```bash
   python weeks/week-NN/day-DD/main.py --clear profiles
   python weeks/week-NN/day-DD/main.py --clear working
   python weeks/week-NN/day-DD/main.py --clear short
   # если long не меняли намеренно в задании:
   python weeks/week-NN/day-DD/main.py --clear all-long-reset
   ```

   Проверка: `git diff weeks/week-NN/day-DD/data/` — нет runtime-карточек, `learned` в profiles пустой, short пустой или seed.

5. Опционально dry-run: `./scripts/finish_day.sh -n -m "..."` — посмотреть split extra/day до реального коммита.

## Запуск (важно: права)

Запускай скрипт **одной** shell-командой с **`required_permissions: ["all"]`**.

Не используй `git_write` + `full_network` — в sandbox Cursor push часто падает с `Could not resolve hostname github.com`, хотя коммиты уже созданы.

```bash
./scripts/finish_day.sh -m "Week N day D: краткое описание на английском."
```

- **`-m`** — сообщение коммита задания (стиль: `Week 2 day 1: simple LLM chat agent.`).
- Без `-m` — первый пункт из `## Задание` в README дня.
- **`-n`** — dry-run, без commit/push.

## Если push упал

Скрипт печатает `DAY_COMMIT=...` **до** push. Если в конце `PUSH_FAILED`:

1. Не создавай новые коммиты — они уже локально.
2. Повтори только push с **`required_permissions: ["all"]`**:
   ```bash
   git push origin master
   ```
3. Задача завершена только при `PUSH_OK=true` в выводе скрипта или успешном ручном push.

## Логика скрипта

1. День — по путям `weeks/week-NN/day-DD/` и `journal/week-NN/day-DD.md`.
2. Несколько дней в diff → ошибка, коммит вручную.
3. Прочие файлы (rules, AGENTS.md и т.д.) → отдельный коммит `Update repo config and tooling.`
4. Файлы задания + **plan дня** из `.cursor/plans/` → коммит с `-m`.
   Plan ищется по ссылкам на `weeks/week-NN/day-DD/` в содержимом; запасной вариант — по имени файла (`week3_day01_*`, `day_05_*`).
5. Ссылки на коммиты → `git push origin master`.

## Результат

Сообщи **ссылку на коммит задания** (`DAY_COMMIT=...`). Extra-коммит упомяни кратко. Убедись, что push дошёл до origin.

Без amend и force-push.

## После коммита

Кратко **проанализируй чат сессии** — не только ответы агента и сбои, но и **команды и уточнения пользователя** (что просил, что переопределил, какие ограничения задал) — и **предложи пользователю**, что имеет смысл добавить в `.cursor/rules/` или эту команду, без правок правил без запроса. Примеры: user_sim уходит от сценария, сброс `data/` перед push, streaming/кодировка, экономия токенов на smoke-test.
