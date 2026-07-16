# TaskBoard

Мини-сервис учёта задач для учебной демонстрации RAG-ассистента.

## Структура

```
project/
  README.md              # этот файл
  docs/
    architecture.md      # слои и потоки данных
    api.yaml             # OpenAPI 3: эндпоинты и схемы
```

## Модули (логически)

| Модуль | Назначение |
|--------|------------|
| `api` | HTTP-эндпоинты `/health`, `/tasks` |
| `store` | in-memory хранилище задач |
| `models` | `Task`, `TaskCreate`, `TaskStatus` |

Кода приложения в этой папке нет — только документация для индексации.

## Запуск (условный)

```bash
uvicorn taskboard.app:app --reload --port 8080
```

Базовый URL: `http://localhost:8080`.

## Статусы задачи

- `todo` — создана
- `doing` — в работе
- `done` — завершена

Создание задачи: `POST /tasks` с полями `title` (обязательно) и `description` (опционально).
Список: `GET /tasks`. Одна задача: `GET /tasks/{task_id}`.
