# Неделя 5, день 2

## Задание

Первый **RAG-запрос** по индексу day-01: retrieve (cosine, top-k=10) → prompt с контекстом → ответ LLM.

- Вопросы пользователя — **на русском**; для embed/retrieve — перевод **RU→EN**; ответ LLM — **сразу RU** (контекст в prompt на EN).
- Генерация: **Dockhost**; эмбеддинги вопроса: **Ollama** (`nomic-embed-text`).
- Индекс: `weeks/week-05/data/opossum_index.json` (строится в day-01, не коммитится).
- Сравнение **с RAG / без RAG** на одном вопросе; демо — **10 вопросов** постранично.

## Результат

На видео — одна команда:

```bash
python weeks/week-05/day-02/main.py --demo
```

В stdout: перевод, retrieve (meta + score), ожидания, полные ответы RAG vs no-RAG по 10 вопросам.

## Setup

```bash
source .venv/bin/activate
pip install -r weeks/week-05/day-02/requirements.txt
```

Предварительно (если индекса нет):

```bash
python weeks/week-05/day-01/init_data.py
python weeks/week-05/day-01/main.py --index
```

Ollama + Dockhost — см. [day-01 README](../day-01/README.md) и `.env.example` (`DOCKHOST_AI_KEY`).

## Команды

```bash
# один вопрос (RU) — RAG, ответ RU
python weeks/week-05/day-02/main.py --ask "Почему дядюшка Билли Опоссум притворяется мёртвым?"

# без RAG
python weeks/week-05/day-02/main.py --ask "…" --no-rag

# сравнение двух режимов
python weeks/week-05/day-02/main.py --compare "Какие дикие плоды преобладали в помёте опоссумов?"

# демо для видео (10 вопросов, пауза между экранами)
python weeks/week-05/day-02/main.py --demo

# демо без паузы
python weeks/week-05/day-02/main.py --demo --no-pause

# smoke без Ollama/LLM
python weeks/week-05/day-02/main.py --show-index
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
| Код | `weeks/week-05/day-02/` |

## Заметки

Пайплайн: RU → translate (вопрос) → embed EN → cosine retrieve → RAG prompt (контекст EN, ответ RU).
