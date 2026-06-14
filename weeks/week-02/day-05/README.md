# Неделя 2, день 5 — три стратегии контекста

## Задание

Управление контекстом **без summary**: Sliding Window, Sticky Facts (key-value), Branching. Переключатель стратегий + сравнение на одном сценарии.

## Модель

`deepseek/deepseek-v3.2` — окно **131 072** tok, 35/51 ₽ за 1M (in/out). Переопределение: `DOCKHOST_MODEL` в `.env`.

## Запуск

```bash
source .venv/bin/activate
pip install -r weeks/week-02/day-05/requirements.txt
cp .env.example .env   # DOCKHOST_AI_KEY
```

### One-shot / чат

```bash
python weeks/week-02/day-05/main.py
python weeks/week-02/day-05/main.py --strategy facts "Бюджет 500k, срок 3 месяца"
python weeks/week-02/day-05/main.py --clear --chat
python weeks/week-02/day-05/main.py --clear --chat --strategy branching
python weeks/week-02/day-05/main.py --clear --chat --strategy facts
```

После каждого хода — `[context]`, для facts — блок `[facts]` с ключами, `[tokens]`.

### Демо: сравнение 3 стратегий (~1–3 ₽)

```bash
python weeks/week-02/day-05/main.py --demo-compare
```

Сценарий **OpossumEats** — клиент диктует пункты ТЗ по очереди, агент только фиксирует (без вопросов), затем recall.

Быстрая проверка (8 ходов + recall, ~1 ₽):

```bash
python weeks/week-02/day-05/main.py --demo-compare-quick
```

Параметры окна:

```bash
python weeks/week-02/day-05/main.py --demo-compare --window 4
```

## Стратегии

| Стратегия | `--strategy` | Суть |
|-----------|--------------|------|
| Sliding Window | `sliding` | Только последние N сообщений, остальное отбрасывается |
| Sticky Facts | `facts` | KV-блок фактов (обновляется после каждого user) + последние N |
| Branching | `branching` | Checkpoint + независимые ветки (`/checkpoint`, `/fork`, `/switch`) |

## Сценарий видео

1. `--demo-compare` — таблица: sliding теряет бюджет среди жуков и мусорных баков, facts показывает `[facts]`, branching — fork payment/delivery.
2. `--clear --chat --strategy facts` — пара реплик, смотрим обновление `[facts]` после каждого хода.
3. `--clear --chat --strategy branching` — `/checkpoint`, `/fork payment delivery`, `/switch delivery`.
4. Показать `chat_history.json` — `facts` vs `shared`/`branches`.

## Результат

Агент с 3 стратегиями управления контекстом + сравнение recall/токены/₽ на сценарии OpossumEats.

## Статус

- [x] Код готов
- [ ] Видео записано
- [ ] Ссылка в таблице курса
- [ ] Обновлён [submissions.md](../../../submissions.md)

## Артефакты

| Тип | Ссылка |
|-----|--------|
| Видео | |
| Код | `weeks/week-02/day-05/` |

## Структура

| Файл | Назначение |
|------|------------|
| `context.py` | SlidingWindow, Facts, Branching + persist |
| `agent.py` | `ChatAgent`, `print_facts()`, Dockhost API |
| `main.py` | CLI: `--chat`, `--demo-compare`, opossum-сценарий |
| `chat_history.json` | Создаётся при работе |

## Заметки

- `--window 6` (default) — sliding намеренно теряет ранние решения к recall.
- Facts: extra LLM-вызов на обновление KV; токены в `extra=` и таблице сравнения.
- Branching: shared-префикс сохраняет бюджет/стек на обеих ветках.
