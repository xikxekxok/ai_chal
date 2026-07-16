# Неделя 7, день 4

## Задание

Собрать self-contained Python CLI-проект с AI file assistant, который работает с локальными файлами через собственный `Tool Registry + Tool Executor`, а не через MCP.

Ассистент должен уметь:

- принимать goal-level prompt;
- самостоятельно читать, искать и анализировать файлы в sandbox workspace;
- при необходимости обновлять файлы через локальный tool `write_file`;
- не выходить за пределы sandbox workspace.

## Что реализовано

В `weeks/week-07/day-04/` собран минимальный агент:

- `llm.py` — OpenAI-compatible HTTP-клиент для Dockhost через `requests` с timeout и retry;
- `tools.py` — локальные tools `list_dir`, `read_file`, `search_files`, `write_file` с ограничением по `sandbox_workspace/`;
- `agent.py` — tool-loop агент, который вызывает LLM и исполняет tools локально;
- `main.py` — CLI с режимами `--tools-test`, `--reset`, `--demo`, `--chat` и positional prompt;
- `sandbox_seed/` — маленький проект из 4 файлов, который агент реально исследует и может обновлять.

## Сценарий демо

`--demo` запускает два сценария подряд:

1. ассистент находит все использования `fetch_user` по sandbox-проекту;
2. ассистент обновляет `README.md` в sandbox на основе реально прочитанного кода.

Вывод в stdout помечен короткими тегами:

- `[demo]` — этапы сценария;
- `[agent]` — prompt и финальный ответ;
- `[tool]` — локальные вызовы tools и результат;
- `[tokens]` — usage по LLM;
- `[retry]` / `[error]` — ошибки и повторы.

## Запуск

Из корня репозитория:

```bash
source .venv/bin/activate
pip install -r weeks/week-07/day-04/requirements.txt
```

Проверка tools без LLM:

```bash
python weeks/week-07/day-04/main.py --tools-test
```

Сброс sandbox workspace:

```bash
python weeks/week-07/day-04/main.py --reset
```

One-shot задача для агента:

```bash
python weeks/week-07/day-04/main.py "Find every usage of fetch_user"
```

Интерактивный режим:

```bash
python weeks/week-07/day-04/main.py --chat
```

Полное демо:

```bash
python weeks/week-07/day-04/main.py --demo
```

## Что показать на видео

- запуск `--tools-test`, чтобы показать локальный registry/executor и diff preview на записи файла;
- запуск `--demo`, где агент сам вызывает tools и решает обе задачи;
- что `README.md` в `sandbox_workspace/` обновлён по реальному коду, а не по выдуманному описанию.

## Ограничения

- tools читают и пишут только внутри `sandbox_workspace/`;
- опасные операции вроде delete не реализованы;
- `write_file` принимает полный новый текст файла и возвращает preview diff;
- без `DOCKHOST_AI_KEY` можно проверить только no-LLM режимы.

## Статус

- [x] Код готов
- [ ] Видео записано
- [ ] Ссылка в таблице курса
- [ ] Обновлён [submissions.md](../../../submissions.md)
