# Неделя 5, день 4

## Задание

RAG с **обязательными источниками и цитатами** поверх rerank-пайплайна day-03 (без query rewrite).

- Пайплайн: translate RU→EN → retrieve k=20 → CrossEncoder rerank → top-4 в RAG.
- Модель возвращает **JSON**: `context_sufficient`, `answer`, `clarification_hint`, источники, цитаты.
- `context_sufficient=false` → ответ начинается с «Я не знаю» + пояснение; `clarification_hint` — что уточнить.
- **Fallback:** при `false` или `kept=0` — второй RAG на всех 20 cosine-чанках (`[rag-wide]`).
- Проверка на **10 вопросах** из day-02: `[verify]` + `[verify-total]`.

## Результат

На видео — одна команда:

```bash
python weeks/week-05/day-04/main.py --demo
```

В stdout: translate, retrieve, rerank, `[rag-rerank]` (+ `[rag-wide]` при fallback), `[verify]`, `[verify-total]`.

## Setup

```bash
source .venv/bin/activate
pip install -r weeks/week-05/day-04/requirements.txt
```

Предварительно (если индекса нет):

```bash
python weeks/week-05/day-01/init_data.py
python weeks/week-05/day-01/main.py --index
```

Ollama + Dockhost — см. [day-01 README](../day-01/README.md). Первый запрос с rerank скачает CrossEncoder (~90MB).

## Команды

```bash
# демо для видео (10 вопросов + verify)
python weeks/week-05/day-04/main.py --demo
python weeks/week-05/day-04/main.py --demo --no-pause

# один вопрос
python weeks/week-05/day-04/main.py --ask "Какие дикие плоды преобладали в помёте опоссумов осенью?"

# настройка rerank
python weeks/week-05/day-04/main.py --ask "…" --retrieve-k 20 --rag-k 4 --min-score 0.15

# smoke без Ollama/LLM/CrossEncoder
python weeks/week-05/day-04/main.py --show-index
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
| Код | `weeks/week-05/day-04/` |

## Заметки

Пайплайн: translate → retrieve k=20 → rerank (min_score) → structured RAG JSON. Вопросы — формальные из day-02.
