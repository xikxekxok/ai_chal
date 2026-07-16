# Неделя 7, день 2

CLI-ревьюер для GitHub Pull Requests: опрашивает репозиторий через GitHub REST API, собирает локальный контекст по коду и документации, а затем печатает review в stdout через Dockhost LLM.

## Что показывает на видео

- Запуск одной команды `python weeks/week-07/day-02/main.py --once --pr <номер>`
- Получение PR через GitHub REST API
- Локальный RAG по текущему репозиторию без embeddings и Ollama
- Краткий review в stdout с тремя секциями:
  - `## Потенциальные баги`
  - `## Архитектурные проблемы`
  - `## Рекомендации`

## Особенности решения

- По умолчанию работает как watcher/poller
- Опционально поддерживает `--once` и `--pr`
- Ничего не пишет в GitHub, только читает API и печатает результат в stdout
- Сохраняет состояние просмотренных PR в `weeks/week-07/day-02/data/seen_prs.json`
- Кэширует локальный индекс RAG в `weeks/week-07/day-02/data/rag_index.json`

## Установка

Из корня репозитория:

```bash
source .venv/bin/activate
pip install -r weeks/week-07/day-02/requirements.txt
cp .env.example .env
```

Заполните в `.env`:

```bash
DOCKHOST_AI_KEY=...
GITHUB_TOKEN=...
```

Опционально:

```bash
GITHUB_REPO=xikxekxok/ai_chal  # default in code if unset
OPENAI_BASE_URL=https://inference.dockhost.io/v1
DOCKHOST_MODEL=deepseek/deepseek-v3.2
```

## Запуск

Один проход по конкретному PR:

```bash
python weeks/week-07/day-02/main.py --once --pr 123
```

Один проход по всем открытым PR:

```bash
python weeks/week-07/day-02/main.py --once
```

Watcher с polling:

```bash
python weeks/week-07/day-02/main.py
```

Watcher с другим интервалом:

```bash
python weeks/week-07/day-02/main.py --interval 60
```

## Как устроено

1. `main.py` загружает `.env`, опрашивает GitHub и отслеживает, менялся ли `head_sha` или `updated_at`.
2. `rag.py` строит простой локальный индекс по `README`, `AGENTS`, `.cursor/rules/*.mdc`, `lessons/*.md`, `weeks/**/*.py`.
3. Для changed files retrieval дополнительно бустит совпадающие пути.
4. `review.py` собирает prompt по PR, diff и локальному контексту.
5. `llm.py` делает единственный `complete()` с retry для Dockhost.

## Ограничения

- Требуются `GITHUB_TOKEN` и `DOCKHOST_AI_KEY`
- Для очень больших PR GitHub может не вернуть полный patch для отдельных файлов
- RAG здесь намеренно простой: без embeddings, только лексический поиск по локальному индексу
