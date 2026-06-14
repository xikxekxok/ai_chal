# Неделя 2, день 3 — подсчёт токенов и перегрузка контекста

## Задание

На базе day-02: подсчёт токенов и стоимости после каждого вызова, демо роста контекста и recall-тест с набивкой окна книгами Gutenberg про опоссумов.

## Модель

`deepseek/deepseek-v3.2` — окно **131 072** tok, 35/51 ₽ за 1M (in/out). Дефолт в `agent.py`; переопределение: `DOCKHOST_MODEL` в `.env`.

## Запуск

```bash
source .venv/bin/activate
pip install -r weeks/week-02/day-03/requirements.txt
cp .env.example .env   # DOCKHOST_AI_KEY
```

### One-shot / чат

```bash
python weeks/week-02/day-03/main.py
python weeks/week-02/day-03/main.py --clear --chat
```

После каждого хода — блок `[tokens]`: дельта запроса, вся история, ответ, ₽, % окна, накопление за сессию.

### Демо: короткий vs длинный диалог (~0.05–0.15 ₽)

```bash
python weeks/week-02/day-03/main.py --clear --demo
```

7 вызовов: 1 короткий вопрос + 6 ходов одной темы → таблица роста `prompt_tok` / ₽ / % окна.

### Демо: recall sweep (главное шоу, ~19 ₽)

```bash
python weeks/week-02/day-03/main.py --demo-recall
```

10 изолированных прогонов (10% → 95%): на каждом шаге **полный** ответ LLM в stdout; в конце — таблица + **LLM-саммари** деградации recall (отдельный запрос).

Быстрая проверка (3 точки, ~2–3 ₽):

```bash
python weeks/week-02/day-03/main.py --demo-recall-quick
```

Полный sweep ~25–40 ₽ (deepseek дороже qwen, но отвечает быстрее).

### Демо: жёсткий recall (деградация, ~15–25 ₽)

```bash
python weeks/week-02/day-03/main.py --demo-recall-hard
```

5 точек (20→95%): анекдот **после** 3 фрагментов книг, русские distractor-сообщения про опоссумов, нейтральный вопрос «какой анекдот я **упоминал**» (без «в начале»). Полные ответы + LLM-саммари.

Сравните с мягким `--demo-recall`, где анекдот в начале и recall держится до 95%.

### Опционально: переполнение (HTTP 400, ~4 ₽)

```bash
python weeks/week-02/day-03/main.py --demo-overflow
```

Только на видео — один вызов с контекстом > 262k tok.

## Сценарий видео

1. `--clear --chat` — пара сообщений, смотрим `[tokens]`.
2. `--demo` — короткий vs длинный, таблица роста.
3. `--demo-recall` — мягкий sweep (анекдот в начале).
4. `--demo-recall-hard` — жёсткий sweep (деградация recall).
5. (опционально) `--demo-overflow` — HTTP 400.

## Результат

На видео видно: рост токенов/стоимости в диалоге, как recall анекдота ломается при заполнении окна книгами, опционально — ошибка переполнения.

## Статус

- [x] Код готов
- [ ] Видео записано
- [ ] Ссылка в таблице курса
- [ ] Обновлён [submissions.md](../../../submissions.md)

## Артефакты

| Тип | Ссылка |
|-----|--------|
| Видео | |
| Код | `weeks/week-02/day-03/` |

## Структура

| Файл | Назначение |
|------|------------|
| `agent.py` | `ChatAgent`, `TokenTracker`, `complete()` / `run()` |
| `corpus.py` | Gutenberg-кэш, `build_recall_messages(pct)` |
| `main.py` | CLI: `--chat`, `--demo`, `--demo-recall`, `--demo-overflow` |
| `.cache/` | Кэш книг (в `.gitignore`) |

## Заметки

- Recall без «запомни» / «дословно» — честнее для демо position bias.
- Полный `--demo-recall` ≈ 0.7M input tok на deepseek → ~25–40 ₽.
