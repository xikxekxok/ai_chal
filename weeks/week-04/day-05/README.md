# Неделя 4, день 5 — Orchestration MCP: дело Тофика

## Задание

Оркестрация **трёх MCP-серверов** в одном агенте:

- агент выбирает нужный инструмент и маршрутизирует запросы;
- длинный флоу расследования с tools с разных серверов;
- проверка порядка и выбора вызовов.

**Сюжет:** 14 мая 2024 пропал фитбол **Тофика**. Архив + trail (метео, физика) для проверки показаний.

## MCP-серверы

| Сервер | Tools | Роль |
|--------|-------|------|
| `burrow` | `list_case_files`, `read_case_file`, `list_suspects` | архив (4 md + досье) |
| `trail` | `web_search`, `read_page` | полевые проверки |
| `snout` | `add_clue`, `list_clues`, `test_theory`, `build_timeline`, `accuse` | дедукция |

На каждый tool: рассуждение `[holmes]`, маршрут `[mcp]`, полный текст `[report]` / `[dossier]` / `[clue]`.

## Запуск

```bash
source .venv/bin/activate
pip install -r weeks/week-04/day-05/requirements.txt

# Smoke-test MCP без LLM (с полным выводом документов)
python weeks/week-04/day-05/main.py --mcp-test

# Demo для видео — постраничный вывод; агент не ждёт Enter, крутится в фоне
python weeks/week-04/day-05/main.py --demo --video

# То же без очистки экрана (листание вниз, как less)
python weeks/week-04/day-05/main.py --demo --pager --no-pager-clear

# Без цветов / без typewriter
python weeks/week-04/day-05/main.py --demo --no-stream --no-color

# One-shot
python weeks/week-04/day-05/main.py

# Интерактив
python weeks/week-04/day-05/main.py --chat

# Очистить доску улик
python weeks/week-04/day-05/main.py --clear
```

## Что показать на видео

1. `--mcp-test` — полные отчёты, досье, улики, вердикт
2. `--demo --video` — архив → **web_search погода/вес** → улики → `[verdict]`
3. `test_theory(crow) → ОТБРОШЕНО`, `accuse(pete) → [verdict]`
4. `[tokens]` в конце

## Статус

- [ ] Код готов
- [ ] Видео записано
- [ ] Ссылка в таблице курса
- [ ] Обновлён [submissions.md](../../../submissions.md)

## Артефакты

| Тип | Ссылка |
|-----|--------|
| Видео | |
| Код | `weeks/week-04/day-05/` |
