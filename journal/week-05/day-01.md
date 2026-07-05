# Week 5, day 01

- Пайплайн индексации: `init_data.py` (8 книг Gutenberg → `data/raw/`) + `main.py --index` (overlap chunking → Ollama `nomic-embed-text` → JSON).
- Общий индекс недели: `weeks/week-05/data/opossum_index.json`; вся `data/` в gitignore.
- Chunking: 3200/320 chars, section из заголовков Gutenberg; meta самодостаточна для RAG (chunk_id, offsets, title, author).

**На видео:** `init_data.py` → `main.py --index` — этапы, прогресс embed с ETA, sample meta без дампа text/embedding.

**Smoke без Ollama:** `--show-index`, `--clear`.
