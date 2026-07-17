# Неделя 7, день 5 — Second Brain

Личный CLI «второй мозг»: заметки в SQLite, гибридный поиск (FTS5 + Ollama embeddings + RRF), ответы через Dockhost с цитированием реальных note id.

## Задача

- `--save` — обогатить заметку (title/tags/aliases/summary), нарезать чанки, проиндексировать FTS и dense.
- `--ask` — expand запроса → hybrid retrieve → two-stage context pack → саммари + `[notes]` из retrieve.
- Масштаб ориентир: ~36k заметок; бэкап = `cp data/brain.db`.

## Стек

| Слой | Технология |
|------|------------|
| Persist | SQLite WAL (`data/brain.db`) |
| Lexical | FTS5 bm25 по чанкам (+ title/tags/aliases/summary) |
| Dense | Ollama `nomic-embed-text` |
| Fusion | RRF (FTS ∪ dense top-M≈40) |
| LLM | Dockhost Inference (`llm.py`, retries, UsageTracker) |

Зависимости: `requests`, `python-dotenv` (+ sqlite3 stdlib).

## Setup

```bash
source .venv/bin/activate
pip install -r weeks/week-07/day-05/requirements.txt

# .env в корне репо
# DOCKHOST_AI_KEY=...
# OLLAMA_BASE_URL=http://localhost:11434   # опционально
# OLLAMA_EMBED_MODEL=nomic-embed-text

ollama serve   # в другом терминале
ollama pull nomic-embed-text
```

## CLI

```bash
# демо для видео (clear → 2 save → search → ask)
python weeks/week-07/day-05/main.py --demo

python weeks/week-07/day-05/main.py --save "текст заметки"
python weeks/week-07/day-05/main.py --save "сырой текст" --no-enrich
python weeks/week-07/day-05/main.py --ask "вопрос к базе"
python weeks/week-07/day-05/main.py --search "throttle Retry-After"
python weeks/week-07/day-05/main.py --list --limit 10
python weeks/week-07/day-05/main.py --show 1
python weeks/week-07/day-05/main.py --stats
python weeks/week-07/day-05/main.py --reindex-embeddings
python weeks/week-07/day-05/main.py --clear
```

Stdout-метки: `[demo]`, `[save]`, `[embed]`, `[expand]`, `[retrieve]`, `[ask]`, `[notes]`, `[stats]`, `[tokens]`, `[retry]`, `[error]`.

## Деградация

| Ситуация | Поведение |
|----------|-----------|
| Нет `DOCKHOST_AI_KEY` | `--save` без enrich; `--ask`/`--demo` требуют ключ |
| LLM enrich упал | raw save |
| Ollama недоступен | чанки без embedding; ask в `mode=fts-only` |
| Нет embeddings в БД | FTS-only retrieve |

## Архитектура файлов

| Файл | Роль |
|------|------|
| `main.py` | CLI |
| `brain.py` | save / ask / demo seed |
| `store.py` | CRUD + FTS + embed progress |
| `retrieve.py` | FTS + dense + RRF |
| `pack.py` | two-stage context |
| `db.py` | schema WAL |
| `chunking.py` | ~1000 / overlap ~150 |
| `embeddings.py` | Ollama + float32 pack |
| `llm.py` | Dockhost + retries |

## Масштаб и next steps

Линейный dense-scan по ~100k векторов для персонального CLI приемлем. При росте — ANN (`sqlite-vec` / FAISS); сейчас не обязателен. Бэкап: скопировать `data/brain.db` (+ `-wal`/`-shm` если есть активные коннекты — лучше после закрытия CLI).

## Результат (видео)

Один запуск `--demo`: две рабочие заметки (rate limit + Redis cache), search и ask с hybrid retrieve и ссылками на note id.

## Статус

- [x] Код готов
- [ ] Видео записано
- [ ] Ссылка в таблице курса
- [ ] Обновлён [submissions.md](../../../submissions.md)

## Артефакты

| Тип | Ссылка |
|-----|--------|
| Видео | |
| Код | `weeks/week-07/day-05/` |
