# Week 04 Day 04 — композиция MCP-tools

## Сделано

- Один MCP-сервер `notes-pipeline`: `web_search`, `read_page`, `build_report`, `save_note`.
- Агент `PipelineAgent` — tool-loop; LLM сама собирает цепочку по запросу.
- CLI: `--mcp-test`, `--chat`, one-shot (`python main.py [prompt]`).

## Интересное

- `build_report` — шаблон markdown без LLM в MCP (как уточнял Алексей в чате).
- One-shot default prompt про MCP → 5 tool calls (search, 2× read_page, report, save).

## Проблемы

- `--mcp-test` с web_search в sandbox падает по DNS — нужен полный доступ к сети.

## Вывод для видео

```bash
python weeks/week-04/day-04/main.py --mcp-test
python weeks/week-04/day-04/main.py
```

Показать `[mcp] call` ×3+ и `[pipeline] saved: data/notes/mcp_facts.md`.
