# Week 04 Day 02

- MCP-сервер в `mcp/`: tools `web_search` (ddgs) и `read_page` (trafilatura + httpx), stdio transport, FastMCP.
- Агент в корне: tool-loop через Dockhost `tools` + `call_tool` к локальному subprocess.
- UX из week-03: typewriter (`--no-stream` отключает), `--video` постранично, `[tokens]` с ₽.
- Без памяти, user_sim, профилей — только `messages[]` в RAM на сессию.

**Проверка:** `ruff check`, `--mcp-test` (без ключа), `--demo --no-stream` (2 хода, web_search → read_page).

**Видео:** `python weeks/week-04/day-02/main.py --demo` или `--demo --video`.
