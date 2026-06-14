# Неделя 2, день 3 — подсчёт токенов и recall

**Задание:** токены/стоимость после каждого вызова, демо роста контекста, sweep recall с Gutenberg-корпусом.

## Что сделали

- `agent.py`: модель из `.env` (дефолт `deepseek/deepseek-v3.2`), окно **131k**, тарифы 35/51 ₽/M.
- С qwen recall набивал 90% от 262k → HTTP 400 на deepseek; лимит окна привязан к модели.
- `corpus.py`: скачивание PG#37199/2441/55704 в `.cache/`, `build_recall_messages(pct)` — изолированная история на каждый %, user-only filler без «запомни».
- `main.py`: `--chat`, `--demo`, `--demo-recall` (10→95%), `--demo-recall-quick` (10/50/90), `--demo-overflow`.

## Интересное

- Recall-тест: анекдот — casual user-сообщение, книги — как paste документации, один LLM-вызов на финальный вопрос; эвристика ✓/✗ по ключевым словам.
- Оценка токенов для набивки контекста — chars/3.5, без tiktoken; actual `prompt_tokens` после API для таблицы.

## Проблемы

- Gutenberg: у PG#37199 нет `37199-0.txt` — fallback на `/cache/epub/`.
- С `deepseek` из `.env` на 90% recall — HTTP 400, если `MODEL_CONTEXT_LIMIT` был 262k (корпус набивался под qwen). Исправлено: 131k.
- `--demo-recall-hard`: анекдот после 3 книг, 5 distractor-ов, нейтральный вопрос; sweep 20–95%.

## Вывод

Для видео: `--clear --chat` → `--demo` → `--demo-recall` (полный sweep ~19 ₽). Verify: `ruff check`, `--demo`, `--demo-recall-quick`.
