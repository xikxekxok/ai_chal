# Неделя 1, день 1

## Задание

Минимальный код: запрос в LLM через API → ответ → вывод в консоль (CLI).

Провайдер: [Dockhost Inference](https://docs.dockhost.ru/manual/ai/inference/use) (OpenAI-compatible).

## Результат

На видео: запуск `main.py`, в консоли виден ответ модели.

## Запуск

```bash
source .venv/bin/activate
pip install -r weeks/week-01/day-01/requirements.txt
cp .env.example .env   # если ещё нет
# В .env: DOCKHOST_AI_KEY=...

python weeks/week-01/day-01/main.py
python weeks/week-01/day-01/main.py "Объясни, что такое API, в двух предложениях"
```

Переменные окружения (альтернатива именам Dockhost — стандарт OpenAI SDK):

- `DOCKHOST_AI_KEY` или `OPENAI_API_KEY`
- `OPENAI_BASE_URL` (по умолчанию `https://inference.dockhost.io/v1`)
- `DOCKHOST_MODEL` (по умолчанию `deepseek/deepseek-v3.2`)

## Статус

- [x] Код готов
- [ ] Видео записано
- [ ] Ссылка в таблице курса
- [x] Обновлён [submissions.md](../../../submissions.md)

Журнал: [journal/week-01/day-01.md](../../../journal/week-01/day-01.md)

## Артефакты

| Тип | Ссылка |
|-----|--------|
| Видео | |
| Код | `weeks/week-01/day-01/` |

## Заметки

_
