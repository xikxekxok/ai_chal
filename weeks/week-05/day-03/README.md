# Неделя 5, день 3

## Задание

Второй этап после retrieve: **CrossEncoder rerank** + **порог релевантности** + **query rewrite** (LLM).

- **Голый RAG** и **rewrite без rerank**: cosine top-6 → RAG (k=6).
- **Rerank** (с/без rewrite): retrieve k=20 → CrossEncoder → top-4 в RAG.
- **Query rewrite** — переформулировка EN-вопроса под semantic search (после translate RU→EN).
- Сравнение **4 режимов**: голый RAG · rewrite · rerank · rewrite+rerank.
- Демо — **10 вопросов** из day-02, переформулированные разговорно/косноязычно (постранично, все 4 режима на каждый), чтобы была видна польза rewrite.

## Результат

На видео — одна команда:

```bash
python weeks/week-05/day-03/main.py --demo
```

В stdout: translate, rewrite, 4 ответа по режимам, `[rating]` на каждый вопрос, в конце `[total-rating]` — средний балл и победитель.

## Setup

```bash
source .venv/bin/activate
pip install -r weeks/week-05/day-03/requirements.txt
```

Предварительно (если индекса нет):

```bash
python weeks/week-05/day-01/init_data.py
python weeks/week-05/day-01/main.py --index
```

Ollama + Dockhost — см. [day-01 README](../day-01/README.md). Первый `--retrieve` / `--ask` скачает CrossEncoder (~90MB).

## Команды

```bash
# демо для видео (10 вопросов)
python weeks/week-05/day-03/main.py --demo
python weeks/week-05/day-03/main.py --demo --no-pause

# один вопрос — полный пайплайн
python weeks/week-05/day-03/main.py --ask "Какие дикие плоды преобладали в помёте опossумов осенью?"

# сравнение четырёх режимов
python weeks/week-05/day-03/main.py --compare-modes "Почему дядюшка Билли притворяется мёртвым?"

# один режим
python weeks/week-05/day-03/main.py --ask "…" --mode both
python weeks/week-05/day-03/main.py --retrieve "…" --mode rerank

# настройка порога и top-K
python weeks/week-05/day-03/main.py --retrieve "…" --retrieve-k 20 --rag-k 4 --min-score 0.15

# smoke без Ollama/LLM/CrossEncoder
python weeks/week-05/day-03/main.py --show-index
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
| Код | `weeks/week-05/day-03/` |

## Заметки

Пайплайн bare/rewrite: translate → retrieve k=6 → RAG. Rerank/both: + rewrite (both) → k=20 → CrossEncoder → k=4.
