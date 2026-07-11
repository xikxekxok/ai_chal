# Неделя 6, день 5

## Сделано

- FastAPI: SSE `/api/chat/stream` (thinking + answer), `/api/health`, Alpine.js UI.
- Светлая тема; local-only в UI (облако спрятано).
- qwen3:4b: `think=true`, native `/api/chat` stream; thinking collapsible в истории.
- Системный промпт: реальный Михаил Елизаров (биография, «Библиотекарь»,
  бард-панк-шансон); ответы слегка гротескные.
- Stateless бекенд, localStorage; rate limit, max context trim.
- `run.sh` для VPS.

## Интересное

- Паттерн stream из day-04 перенесён в веб: SSE → Alpine live update.
- `CHAT_MAX_TOKENS=2048` — иначе reasoning съедает budget.

## Проблемы

- Dockhost usage с nested dict ломал Pydantic — исправлено `dict[str, object]`.
- qwen3 через `/v1` + `think=false` всё равно медленный — нужен native stream.

## Вывод

- Видео: `./weeks/week-06/day-05/run.sh`, браузер — виден stream thinking/answer.
- Smoke: `python weeks/week-06/day-05/main.py --check`
