# Week 03, day 01

## Сделано

- Три слоя памяти: `short` / `working` (per-opossum JSON) / `long` (charter.md).
- LLM-классификатор после хода → `working` или `long`, иначе только short.
- `--demo`: 3 диалога (приём Пушка → следующий день → директор меняет часы).
- В начале demo — блок «что происходит» (агент, слои, seed-состояние).
- `session_summary.py`: после каждой сессии LLM-саммари; user_sim на новый диалог видит саммари, не полный transcript.

## Интересное

- Агент и user_sim помнят по-разному: агент — structured memory в файлах; «Марта» — fuzzy summary прошлых смен.
- Классификатор иногда skip'ает очевидные факты — усилили prompt (фокус на реплику пользователя).

## Вывод

```bash
python weeks/week-03/day-01/main.py --demo
```

На видео: intro → 3 сессии с `[summary]` → dump + чеклист.
