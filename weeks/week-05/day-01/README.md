# Неделя 5, день 1

## Задание

Построить пайплайн **индексации документов**: chunking → embeddings → сохранение индекса (JSON).

- Корпус: **8 книг Project Gutenberg** про опоссумов (~1.5 MB текста).
- Chunking: **overlap** (fixed-size 3200 символов, перекрытие 320).
- Эмбеддинги: **Ollama + `nomic-embed-text`** (768 dim).
- Индекс на всю неделю: `weeks/week-05/data/opossum_index.json` (day-02+ читают тот же файл).
- Raw-тексты: отдельный `init_data.py`; `main.py` только читает `data/raw/`.

## Результат

На видео — две команды подряд:

```bash
python weeks/week-05/day-01/init_data.py
python weeks/week-05/day-01/main.py --index
```

В stdout видны этапы `[init]` / `[index]`: загрузка книг, чанкинг, прогресс embed с ETA, сохранение индекса и sample meta (без text/embedding).

## Setup

```bash
source .venv/bin/activate
pip install -r weeks/week-05/day-01/requirements.txt
```

Ollama (Linux):

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama serve   # если не systemd
ollama pull nomic-embed-text
```

Переменные (опционально):

| Переменная | Default |
|------------|---------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` |

## Команды

```bash
# один раз: скачать raw в weeks/week-05/data/raw/
python weeks/week-05/day-01/init_data.py
python weeks/week-05/day-01/init_data.py --force   # перекачать

# индексация (нужен Ollama)
python weeks/week-05/day-01/main.py --index

# без Ollama
python weeks/week-05/day-01/main.py --show-index
python weeks/week-05/day-01/main.py --clear
```

## Метаданные чанка

Каждый элемент `chunks[]`: `{text, embedding, meta}`.

| Поле `meta` | Назначение |
|-------------|------------|
| `chunk_id` | Стабильный ключ, напр. `14732:012` |
| `source_id` | ID книги Gutenberg |
| `title` | Название книги |
| `author` | Автор |
| `section` | Ближайший заголовок или `"intro"` |
| `char_count` | Длина `text` |
| `start_offset` / `end_offset` | Позиция в исходном тексте (видно overlap) |

## Пути

| Путь | Содержимое | Git |
|------|------------|-----|
| `weeks/week-05/data/raw/` | 8 × `{id}.txt` | нет (gitignore) |
| `weeks/week-05/data/opossum_index.json` | индекс недели | нет (gitignore) |

Перед `/finish_day`: `main.py --clear` (удаляет индекс). Raw остаётся локально.

## Статус

- [x] Код готов
- [ ] Видео записано
- [ ] Ссылка в таблице курса
- [ ] Обновлён [submissions.md](../../../submissions.md)

## Артефакты

| Тип | Ссылка |
|-----|--------|
| Видео | |
| Код | `weeks/week-05/day-01/` |

## Заметки

Корпус: Unc' Billy Possum (Burgess), Ecology of the Opossum (Fitch), и др. — см. `sources.py`.
