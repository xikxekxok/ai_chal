# Неделя 6, день 4

## Сделано

- Оптимизированный RAG на `qwen3:4b`: T=0, num_ctx=8192, без num_predict, retrieve 12→3, compact prompt.
- Стриминг reasoning: `[thinking]` → `[rag-*]` / `[answer-rag]` через `/api/chat` (`think=true`, `stream=true`).

## Интересное

- `stream_local()` разделяет `message.thinking` и `message.content` в NDJSON-потоке Ollama.
- Без `think=true` qwen3 «думает» в content; num_predict на этой модели только мешает.

## Проблемы

- OpenAI `/v1/chat/completions` игнорирует `think=false` для qwen3 — нужен native `/api/chat`.

## Вывод

- Видео: `python weeks/week-06/day-04/main.py --demo --no-pause`
- Smoke: `--show-index`, `--check`
