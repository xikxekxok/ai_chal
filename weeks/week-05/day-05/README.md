# Неделя 5, день 5

## Задание

Мини-чат (CLI) с RAG + памятью диалога:

- история сохраняется между запусками;
- на каждый вопрос: query → retrieve k=20 → rerank k=4 → LLM с источниками;
- ответ всегда сопровождается блоком **источников** (и цитат при достаточном контексте);
- без query rewrite и без wide fallback.

Проверка: 2 сценария по 12 реплик с follow-up вопросами.

## Результат

На видео — одна команда:

```bash
python weeks/week-05/day-05/main.py --scenario all --no-pause
```

В stdout на каждом ходу: `[query]`, `[retrieve]`, `[rerank]`, `[rag]`, `[agent]`, `источники:`, `цитаты:`.

## Setup

```bash
source .venv/bin/activate
pip install -r weeks/week-05/day-05/requirements.txt
```

Предварительно (если индекса нет):

```bash
python weeks/week-05/day-01/init_data.py
python weeks/week-05/day-01/main.py --index
```

Ollama + Dockhost — см. [day-01 README](../day-01/README.md).

## Команды

```bash
# видео: оба сценария
python weeks/week-05/day-05/main.py --scenario all
python weeks/week-05/day-05/main.py --scenario all --no-pause

# один сценарий
python weeks/week-05/day-05/main.py --scenario 1

# интерактивный чат
python weeks/week-05/day-05/main.py --clear --chat

# один вопрос
python weeks/week-05/day-05/main.py --ask "Какие дикие плоды преобладали в помёте опоссумов осенью?"

# smoke без Ollama/LLM/CrossEncoder
python weeks/week-05/day-05/main.py --show-index
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
| Код | `weeks/week-05/day-05/` |

## Заметки

Пайплайн: query processor (standalone EN + follow-up, вся история) → retrieve k=20 → rerank top-4 → structured RAG JSON. Температура генерации: 0.35. История: `chat_history.json`.
