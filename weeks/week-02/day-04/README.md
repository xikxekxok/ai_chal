# Неделя 2, день 4 — сжатие истории

## Задание

Управление контекстом: последние N сообщений «как есть», старое — в summary (каждые 10 сообщений). Сравнение качества и расхода токенов с/без сжатия.

## Модель

`deepseek/deepseek-v3.2` — окно **131 072** tok, 35/51 ₽ за 1M (in/out). Переопределение: `DOCKHOST_MODEL` в `.env`.

## Запуск

```bash
source .venv/bin/activate
pip install -r weeks/week-02/day-04/requirements.txt
cp .env.example .env   # DOCKHOST_AI_KEY
```

### One-shot / чат

```bash
python weeks/week-02/day-04/main.py
python weeks/week-02/day-04/main.py --clear --chat
python weeks/week-02/day-04/main.py --no-compress --chat   # без сжатия
```

После каждого хода — `[tokens]` и (если сжатие вкл) `[compress]`.

### Демо: сравнение с/без сжатия (~1–3 ₽)

```bash
python weeks/week-02/day-04/main.py --demo-compare
```

12 ходов про опоссумов + recall анекдота из начала диалога — два прогона (без сжатия / со сжатием), таблица prompt_tok, ₽, recall ✓/✗.

Быстрая проверка (7 ходов + recall, ~1 ₽):

```bash
python weeks/week-02/day-04/main.py --demo-compare-quick
```

Параметры сжатия:

```bash
python weeks/week-02/day-04/main.py --demo-compare --keep 6 --compress-every 10
```

## Сценарий видео

1. `--demo-compare` — таблица: рост токенов без сжатия vs plateau со сжатием, recall анекдота.
2. `--clear --chat` — пара реплик про опоссумов, смотрим `[compress]` при первом summarize.
3. Показать `chat_history.json` — поле `summary` отдельно от `messages`.

## Результат

Агент с компрессией истории: summary подставляется вместо старых сообщений, последние N — как есть, на видео видно экономию токенов и trade-off recall.

## Статус

- [x] Код готов
- [ ] Видео записано
- [ ] Ссылка в таблице курса
- [ ] Обновлён [submissions.md](../../../submissions.md)

## Артефакты

| Тип | Ссылка |
|-----|--------|
| Видео | |
| Код | `weeks/week-02/day-04/` |

## Структура

| Файл | Назначение |
|------|------------|
| `agent.py` | `ChatAgent`, `TokenTracker`, интеграция с `ContextManager` |
| `context.py` | Summary, keep_recent, compress_every, сборка messages |
| `main.py` | CLI: `--chat`, `--demo-compare`, `--demo-compare-quick` |
| `chat_history.json` | `summary` + `messages` (создаётся при работе) |

## Заметки

- Демо — разговор про опоссумов (не абстрактный LLM-контекст): анекдот в начале, recall в конце.
- Summarize — отдельные LLM-вызовы; их токены учитываются в итоговой таблице.
- `--demo-compare-quick` — для smoke-test без полного прогона.
