# Неделя 6, день 1 — локальная LLM

## Задание

Установить и запустить локальную LLM (Ollama + **qwen3:8b**), проверить CLI и HTTP API, сделать минимум 3 запроса разной сложности.

## Результат

На видео одной командой:

1. Ollama запущен, модель скачана.
2. Ответ через **CLI** (`ollama run`) и **HTTP** (`/v1/chat/completions`).
3. Три запроса: простой факт, короткое объяснение, задача на рассуждение.

## Подготовка

```bash
# Установка Ollama: https://ollama.com
ollama serve          # если сервер ещё не запущен
ollama pull qwen3:8b  # ~5 GB, один раз
```

Опционально в `.env` (см. `.env.example`):

```bash
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=qwen3:8b
```

## Запуск

Из корня репозитория:

```bash
chmod +x weeks/week-06/day-01/run.sh

# Smoke-test без генерации (перед коммитом)
./weeks/week-06/day-01/run.sh --check

# Демо для видео: 3 запроса, CLI + HTTP
./weeks/week-06/day-01/run.sh --demo
```

Скрипт печатает промпт, latency и **краткое превью** ответа (не полный дамп).

## Ручная проверка

```bash
# CLI
ollama run qwen3:8b "Hello in one word."

# HTTP (OpenAI-compatible)
curl -s http://localhost:11434/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3:8b","messages":[{"role":"user","content":"2+2?"}],"stream":false}' \
  | python3 -m json.tool
```

## Статус

- [x] Код готов
- [ ] Видео записано
- [ ] Ссылка в таблице курса
- [ ] Обновлён [submissions.md](../../../submissions.md)

## Артефакты

| Тип | Ссылка |
|-----|--------|
| Видео | |
| Код | `weeks/week-06/day-01/` |

## Заметки

- Дефолт **`qwen3:8b`** — комфортно на Ryzen AI 7 350 / 32 GB RAM (см. `week-06.mdc`).
- `qwen3:14b` из лекции — stretch; ответы заметно медленнее на CPU/iGPU.
- **qwen3 «думает» по умолчанию** — в скрипте `OLLAMA_THINK=false` / `--think=false`, иначе простой запрос может идти минутами.
- На этом дне только установка и проверка; сравнение с облаком — день 2.
