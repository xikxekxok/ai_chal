# Week 04 Day 03

## Сделано

- Два MCP subprocess: web + scheduler (SQLite, cron, check_due, clear_jobs).
- Split **host** / **input**: TCP JSON-lines, host — агент + очередь, input — stdin-клиент.
- Очередь user + scheduler: пока агент занят, новые события не теряются.

## Интересное

- Host/input решает конфликт stdin vs ticker без костылей с cancel input().
- Видео: один терминал host (stdout), второй input (по желанию).

## Вывод для видео

```bash
python weeks/week-04/day-03/main.py host --seed-once 30 "…" --tick-seconds 10
python weeks/week-04/day-03/main.py input
```
