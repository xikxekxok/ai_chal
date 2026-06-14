# Неделя 2, день 5 — стратегии контекста

**Задание:** sliding window / sticky facts / branching без summary; сравнение на сценарии сбора ТЗ.

## Что сделали

- `context.py`: три стратегии (`SlidingWindow`, `Facts`, `Branching`) с общим интерфейсом и persist в JSON.
- `agent.py`: интеграция, extra-токены на обновление facts, `print_facts()` после каждого хода.
- `main.py`: `--demo-compare` — сценарий **OpossumEats** (опossum-клиенты/команда) на всех стратегиях + таблица recall/tok/₽.

## Интересное

- Facts: отдельный LLM-вызов после каждого user → JSON ключ-значение; в stdout блок `[facts]` с записями.
- Branching: shared-префикс + fork payment/delivery, recall ✓ на обеих ветках.
- `--demo-compare-quick`: sliding recall ✗, facts ✓ (31 fact, +24k extra tok), branching ✓.

## Проблемы

- LLM задавал вопросы при захардкоженном сценарии → system prompt «секретарь, только фиксируй», сообщения как «Пункт N. …».

## Вывод

Для видео: `--demo-compare` → `--clear --chat --strategy facts` (смотреть `[facts]`) → branching с `/fork`. Verify: `ruff check`, `--demo-compare-quick`.
