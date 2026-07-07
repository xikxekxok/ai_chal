# Неделя 6, день 2 — локальный CLI-чат

## Задание

CLI-чат поверх локальной LLM (Ollama + **qwen3:8b**): one-shot запрос или интерактивный режим с историей диалога в памяти.

## Результат

На видео:

1. `python weeks/week-06/day-02/main.py --check` — Ollama и модель доступны.
2. One-shot: `python weeks/week-06/day-02/main.py "…"` — в stdout модель, запрос, краткий ответ, latency.
3. Интерактив: `python weeks/week-06/day-02/main.py --chat` — несколько ходов, агент помнит контекст сессии.

## Подготовка

```bash
source .venv/bin/activate
pip install -r weeks/week-06/day-02/requirements.txt

ollama serve          # если сервер ещё не запущен
ollama pull qwen3:8b  # ~5 GB, один раз
```

Опционально в `.env` (см. `.env.example`):

```bash
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=qwen3:8b
OLLAMA_THINK=false
```

## Запуск

```bash
# Smoke-test без генерации (перед коммитом)
python weeks/week-06/day-02/main.py --check

# One-shot
python weeks/week-06/day-02/main.py
python weeks/week-06/day-02/main.py "Объясни, что такое AI-агент, в двух предложениях."

# Интерактивный чат
python weeks/week-06/day-02/main.py --chat
```

## Структура

| Файл | Назначение |
|------|------------|
| `llm.py` | `complete_local()`, `check_ollama()` — вызов Ollama API |
| `agent.py` | `ChatAgent`: system prompt + история в памяти |
| `main.py` | CLI: `--check`, `--chat`, one-shot |

## Статус

- [x] Код готов
- [ ] Видео записано
- [ ] Ссылка в таблице курса
- [ ] Обновлён [submissions.md](../../../submissions.md)

## Артефакты

| Тип | Ссылка |
|-----|--------|
| Видео | |
| Код | `weeks/week-06/day-02/` |

## Заметки

- Дефолт **`qwen3:8b`** — комфортно на Ryzen AI 7 350 / 32 GB RAM (см. `week-06.mdc`).
- **qwen3 «думает» по умолчанию** — `OLLAMA_THINK=false`, иначе простой запрос может идти минутами.
- История только в памяти процесса; между запусками не сохраняется.
