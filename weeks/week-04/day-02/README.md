# Неделя 4, день 2

## Задание

Свой MCP-сервер с tools `web_search` и `read_page`, подключение к агенту через tool-loop.

## Структура

```
day-02/
  mcp/           # MCP-сервер (stdio)
  agent.py       # агент с tool-loop
  mcp_client.py  # stdio-клиент
  llm.py         # Dockhost
  main.py        # CLI
```

## Запуск

```bash
source .venv/bin/activate
pip install -r weeks/week-04/day-02/requirements.txt

# Smoke-test MCP без LLM
python weeks/week-04/day-02/main.py --mcp-test

# Демо с агентом (нужен DOCKHOST_AI_KEY)
python weeks/week-04/day-02/main.py --demo

# Для записи видео
python weeks/week-04/day-02/main.py --demo --video

# Интерактив
python weeks/week-04/day-02/main.py --chat
```

## Результат

На видео — `python main.py --demo` (или `--demo --video`):

- `[demo]` — план, подключение к MCP
- `[mcp] tools (2)` — schemas
- `[user]` / `[agent]` — диалог (2 хода)
- `[mcp] call …` — вызовы tools агентом
- `[tokens]` — usage и стоимость

## Статус

- [ ] Код готов
- [ ] Видео записано
- [ ] Ссылка в таблице курса
- [ ] Обновлён [submissions.md](../../../submissions.md)

## Артефакты

| Тип | Ссылка |
|-----|--------|
| Видео | |
| Код | `weeks/week-04/day-02/` |

## Заметки

- Поиск: `ddgs` (без API-ключа).
- Чтение страниц: `trafilatura` + `httpx` (основной текст, не весь HTML).
- MCP transport: stdio (`mcp/server.py`).
