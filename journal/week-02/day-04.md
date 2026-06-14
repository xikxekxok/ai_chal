# Неделя 2, день 4 — сжатие истории

**Задание:** последние N сообщений как есть, старое → summary каждые 10 сообщений; сравнение с/без сжатия.

## Что сделали

- `context.py`: `ContextManager` — archive → summarize → summary, recent N, сборка messages для API.
- `agent.py`: интеграция сжатия в `run()`, `[compress]` в stdout, summary в `chat_history.json`.
- `main.py`: `--demo-compare` — диалог **про опоссумов** (12 ходов + recall анекдота), два прогона с таблицей tok/₽/recall.

## Интересное

- Summary подставляется парой user/assistant («Понял, учту») — модель принимает сжатый контекст.
- Демо на опоссумах: анекдот в начале, filler-вопросы про биологию, recall в конце — видно trade-off сжатия vs память.

## Проблемы

- (заполнить после прогона)

## Вывод

Для видео: `--demo-compare` → `--clear --chat` → показать `chat_history.json` с `summary`. Verify: `ruff check`, `--demo-compare-quick`.
