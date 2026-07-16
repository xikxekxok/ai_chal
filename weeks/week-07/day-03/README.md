# Неделя 7, день 3

## Что здесь сделано

Самодостаточный Python CLI mini-service для саппорта:

- локальный keyword-based RAG по markdown-документам в `data/kb/`;
- локальный read-only MCP CRM по `data/crm.json`;
- агентский tool-loop с Dockhost LLM;
- CLI-режимы для демо, smoke-проверки и точечного вопроса по тикету.

Домен нейтральный: SaaS-сервис `NoteSync`.

## Структура

- `main.py` — CLI и demo-сценарии
- `agent.py` — tool-loop агента
- `llm.py` — Dockhost OpenAI-compatible клиент с retry
- `rag.py` — keyword search по локальной KB
- `mcp/server.py` — локальный stdio MCP CRM
- `mcp_client.py` — тонкий MCP-клиент
- `data/kb/*.md` — FAQ / docs
- `data/crm.json` — локальные пользователи и тикеты

## Установка

Из корня репозитория:

```bash
source .venv/bin/activate
pip install -e ".[dev]"
pip install -r weeks/week-07/day-03/requirements.txt
```

Нужен `.env` в корне репозитория:

```bash
cp .env.example .env
```

Минимум для LLM:

```bash
DOCKHOST_AI_KEY=...
OPENAI_BASE_URL=https://inference.dockhost.io/v1
DOCKHOST_MODEL=deepseek/deepseek-v3.2
```

## Команды

Показать локальную базу знаний:

```bash
python weeks/week-07/day-03/main.py --show-kb
```

Проверить MCP без LLM:

```bash
python weeks/week-07/day-03/main.py --mcp-test
```

Спросить ассистента по конкретному тикету:

```bash
python weeks/week-07/day-03/main.py --ask "Почему не работает авторизация?" --ticket T-1042
```

Запустить video-friendly demo:

```bash
python weeks/week-07/day-03/main.py --demo
```

## Что видно на видео

Удачный demo должен показать:

1. `[retrieve]` список локальных KB-документов.
2. `[tool]` работу локального MCP CRM (`list_tickets`, `get_ticket`, `get_user`).
3. `[tool]` и `[retrieve]` шаги агентского tool-loop.
4. Итоговый `[agent]` ответ по-русски с опорой на KB и CRM-контекст тикета `T-1042`.

## Ограничения

- RAG здесь нарочно простой: только keyword search, без embeddings.
- CRM read-only и локальный, без внешних API.
- Если нет `DOCKHOST_AI_KEY`, режимы `--show-kb` и `--mcp-test` работают, а `--ask` / `--demo` завершатся с понятной ошибкой.

## Статус

- [x] Код готов
- [ ] Видео записано
- [ ] Ссылка в таблице курса
- [ ] Обновлён [submissions.md](../../../submissions.md)
