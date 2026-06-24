# Неделя 4, день 1

## Задание

Минимальный MCP-клиент на Python:

1. установить MCP SDK;
2. подключиться к публичному remote MCP-серверу (DeepWiki, Streamable HTTP);
3. получить и вывести список доступных tools.

LLM и API-ключи **не нужны** — только discovery (`initialize` + `list_tools`), без вызова tools.

## Запуск

```bash
source .venv/bin/activate
pip install -r weeks/week-04/day-01/requirements.txt
python weeks/week-04/day-01/main.py
```

Опционально: другой URL через `MCP_SERVER_URL` (по умолчанию `https://mcp.deepwiki.com/mcp`).

## Результат

На видео — один запуск `main.py`. В stdout видно:

- блок `[demo]` с планом;
- `[mcp] connecting` и `[mcp] connected` (имя и версия сервера);
- `[mcp] tools (3):` со списком tools DeepWiki.

Пример (схемы могут слегка отличаться):

```
[demo] MCP client — discovery tools (без вызова tools и без LLM)
...
[mcp] tools (3):
  - read_wiki_structure
    description:
    Get a list of documentation topics for a GitHub repository.
    Args: repoName: ...
    inputSchema:
    {
      "type": "object",
      ...
    }
```

## Статус

- [ ] Код готов
- [ ] Видео записано
- [ ] Ссылка в таблице курса
- [ ] Обновлён [submissions.md](../../../submissions.md)

## Артефакты

| Тип | Ссылка |
|-----|--------|
| Видео | |
| Код | `weeks/week-04/day-01/` |

## Заметки

- Сервер: [DeepWiki MCP](https://docs.devin.ai/work-with-devin/deepwiki-mcp) — бесплатный, без auth, только публичные GitHub-репозитории.
- Транспорт: Streamable HTTP (`/mcp`), через пакет `mcp` (Python SDK v1.x).
