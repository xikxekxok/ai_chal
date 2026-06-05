# Неделя 1, день 2 — формат ответа через API

**Задание:** один промпт, два вызова — без ограничений и с `response_format`, `max_tokens`, `stop`.

## Что сделали

- CLI `weeks/week-01/day-02/main.py` на базе дня 1: `run_baseline` и `run_controlled`.
- Controlled: `response_format=json_object`, `max_tokens=80`, `stop=["---"]`.
- Вывод `finish_reason` и `completion_tokens` для сравнения на видео.
- Флаги `--baseline` / `--controlled`; по умолчанию — оба режима подряд.

## Интересное

- `json_object` требует упоминание JSON в messages — короткий system-message, user-промпт не меняется.
- При `max_tokens=80` JSON обрезается, `finish_reason: length` — наглядно для демо.

## Проблемы

- DNS в sandbox Cursor: запрос к Dockhost падает без `all`; локально обычно работает.

## Вывод

Для сдачи: `python weeks/week-01/day-02/main.py` — показать два блока в консоли и разницу в токенах/формате.
