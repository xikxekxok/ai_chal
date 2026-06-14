# Неделя 2, день 1 (день 6 курса)

## Задание

Реализовать простого агента, который:

- принимает запрос пользователя;
- отправляет его в LLM через API;
- получает ответ;
- выводит результат в интерфейсе (CLI).

Агент — отдельная сущность (`ChatAgent`), логика запроса/ответа инкапсулирована в `agent.py`.

## Запуск

```bash
source .venv/bin/activate
pip install -r weeks/week-02/day-01/requirements.txt
cp .env.example .env   # если ещё нет; задать DOCKHOST_AI_KEY
```

One-shot (демо на видео):

```bash
python weeks/week-02/day-01/main.py
python weeks/week-02/day-01/main.py "Объясни, что такое AI-агент, в двух предложениях"
```

Интерактивный чат:

```bash
python weeks/week-02/day-01/main.py --chat
```

## Результат

На видео: одна команда `python weeks/week-02/day-01/main.py` — в stdout видны модель, запрос пользователя, ответ агента и usage-токены.

## Статус

- [x] Код готов
- [ ] Видео записано
- [ ] Ссылка в таблице курса
- [ ] Обновлён [submissions.md](../../../submissions.md)

## Артефакты

| Тип | Ссылка |
|-----|--------|
| Видео | |
| Код | `weeks/week-02/day-01/` |

## Структура

| Файл | Назначение |
|------|------------|
| `agent.py` | `ChatAgent`: контекст (system + history), вызов Dockhost API |
| `main.py` | CLI: one-shot и `--chat` |

## Заметки

_
