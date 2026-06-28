# Неделя 4, день 3 — MCP Scheduler + 24/7 агент

## Задание

MCP-инструмент с отложенным или периодическим выполнением:

- сохранение задач (SQLite);
- выполнение по расписанию;
- агрегированный результат через `check_due`.

Агент работает в **host**-процессе; пользовательский ввод — в отдельном **input**-терминале.

## Архитектура

Два MCP-сервера (stdio) + TCP IPC host↔input:

| Компонент | Назначение |
|-----------|------------|
| `host` | агент, scheduler ticker, TCP-сервер, stdout |
| `input` | stdin → TCP-клиент |
| web-search MCP | `web_search`, `read_page` |
| scheduler MCP | `schedule_once`, `schedule_recurring`, `list_jobs`, `cancel_job`, `check_due`, `clear_jobs` |

Host ждёт событие (user или scheduler-due), обрабатывает очередь подряд. Если агент занят — новые сообщения ставятся в очередь.

Cron — 5 полей, **UTC** (`*/5 * * * *` = каждые 5 минут).

## Запуск

```bash
source .venv/bin/activate
pip install -r weeks/week-04/day-03/requirements.txt

# Smoke-test MCP без LLM
python weeks/week-04/day-03/main.py --mcp-test

# Очистить все задачи
python weeks/week-04/day-03/main.py --clear

# Терминал 1 — host (снимаем на видео)
python weeks/week-04/day-03/main.py host \
  --seed-once 30 "Найди три факта про Model Context Protocol и сделай краткую сводку" \
  --tick-seconds 10

# Терминал 2 — input
python weeks/week-04/day-03/main.py input
```

Выход из input: `quit`, `exit`, `q` (host продолжает работать). Host: Ctrl+C.

## Что показать на видео

1. Старт `host` → `[host] listening`, `[scheduler] seeded …`
2. `input` → «Напомни через 2 минуты…» → на host `[user] dispatch`
3. Тик → `[scheduler] tick due_count=1` → web_search + сводка
4. (Опционально) «перезапиши напоминалку» → `list_jobs` → `cancel_job` → `schedule_once`
5. (Опционально) писать в input пока агент занят → `[host] queued user (N pending)`

## Stdout (host)

- `[host]` — TCP, очередь
- `[mcp]` — tools
- `[scheduler]` — тик, seed
- `[user]` / `[scheduler]` — dispatch
- `[agent]` — ответы
- `[tokens]` — usage

## Статус

- [ ] Код готов
- [ ] Видео записано
- [ ] Ссылка в таблице курса
- [ ] Обновлён [submissions.md](../../../submissions.md)

## Артефакты

| Тип | Ссылка |
|-----|--------|
| Видео | |
| Код | `weeks/week-04/day-03/` |
