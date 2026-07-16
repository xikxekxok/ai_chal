# Неделя 7, день 1

## Сделано

- Ассистент TaskBoard: RAG по `project/` + MCP (`git_branch`, `list_files`).
- CLI: `--index`, `--ask`, `--chat` (/help), `--demo`, `--mcp-test`, `--show-index`.

## Интересное

- Игрушечный проект только как docs (README + architecture + OpenAPI), без реального кода сервиса.
- RAG (Ollama `nomic-embed-text`) и live-контекст (MCP git) в одном `/help`.

## Проблемы

- Пока Ollama не был установлен — временно уходили в TF-IDF; вернули Ollama после `ollama pull nomic-embed-text`.

## Вывод

- Видео: `python weeks/week-07/day-01/main.py --demo`
- Smoke без LLM: `--show-index`, `--mcp-test`
