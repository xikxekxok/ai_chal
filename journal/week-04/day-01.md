# Week 04 Day 01

- Standalone MCP-клиент: DeepWiki (`https://mcp.deepwiki.com/mcp`), Streamable HTTP, SDK `mcp` v1.x.
- Discovery only: `initialize` + `list_tools`, без LLM и без `call_tool`.
- Async через SDK (`asyncio.run` в `main`) — синхронной обёртки в библиотеке нет.
- Полный вывод `description`, `inputSchema`, `outputSchema` (у DeepWiki output — `{ result: string }`, FastMCP wrap).

**Проверка:** `ruff check`, `python weeks/week-04/day-01/main.py` (нужна сеть, ключей нет).

**Видео:** один запуск `main.py` — `[demo]`, connect, список 3 tools со схемами.
