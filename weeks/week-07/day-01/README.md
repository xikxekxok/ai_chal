# Неделя 7, день 1 — ассистент разработчика

## Задание

Ассистент по учебному проекту **TaskBoard**: RAG по `project/README` + `project/docs`, MCP (`git_branch`, `list_files`), команда `/help`.

## Результат

- `--demo` показывает индекс, git-ветку, список файлов и ответы на вопросы о структуре и API.
- `/help` / `--ask` опираются на документацию и MCP.

## Запуск

```bash
source .venv/bin/activate
pip install -r weeks/week-07/day-01/requirements.txt

# Ollama — только эмбеддинги RAG (ответы через Dockhost)
ollama serve   # в отдельном терминале, если ещё не запущен
ollama pull nomic-embed-text

# ключ: DOCKHOST_AI_KEY в корневом .env
python weeks/week-07/day-01/main.py --index
python weeks/week-07/day-01/main.py --demo
```

Другие режимы:

| Команда | Что делает |
|---------|------------|
| `--show-index` | сводка индекса без LLM |
| `--mcp-test` | git_branch + list_files без LLM |
| `--ask "…"` | one-shot /help |
| `--chat` | REPL: `/help <вопрос>`, `/quit` |

## Статус

- [x] Код готов
- [ ] Видео записано
- [ ] Ссылка в таблице курса
- [ ] Обновлён [submissions.md](../../../submissions.md)

## Артефакты

| Тип | Ссылка |
|-----|--------|
| Видео | |
| Код | `weeks/week-07/day-01/` |

## Заметки

Корпус RAG — только `project/` (TaskBoard). Индекс: `data/project_index.json` (gitignore).
