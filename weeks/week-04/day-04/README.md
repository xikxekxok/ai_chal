# Неделя 4, день 4 — Композиция MCP-инструментов

## Задание

Один MCP-сервер с несколькими tools; агент с tool-loop **сам** вызывает цепочку по запросу пользователя (без хардкода порядка в клиенте).

Пример сценария: «найди факты → оформи отчёт → сохрани в файл».

## Tools (один MCP-сервер)

| Tool | Назначение |
|------|------------|
| `web_search` | поиск в интернете |
| `read_page` | чтение страницы по URL |
| `build_report` | markdown-отчёт из findings + sources (без LLM) |
| `save_note` | запись в `data/notes/` |

## Запуск

```bash
source .venv/bin/activate
pip install -r weeks/week-04/day-04/requirements.txt

# Smoke-test MCP без LLM
python weeks/week-04/day-04/main.py --mcp-test

# One-shot (нужен DOCKHOST_AI_KEY) — default prompt
python weeks/week-04/day-04/main.py

# Свой запрос
python weeks/week-04/day-04/main.py "Найди три факта про MCP и сохрани в note.md"

# Интерактив
python weeks/week-04/day-04/main.py --chat
```

## Что показать на видео

1. `--mcp-test` — tools работают, файл создан
2. One-shot с default prompt — в stdout ≥3 `[mcp] call` (search → report → save)
3. `[pipeline] saved: data/notes/...` — preview файла
4. `[agent]` — ответ с путём к заметке

## Статус

- [ ] Код готов
- [ ] Видео записано
- [ ] Ссылка в таблице курса
- [ ] Обновлён [submissions.md](../../../submissions.md)

## Артефакты

| Тип | Ссылка |
|-----|--------|
| Видео | |
| Код | `weeks/week-04/day-04/` |
