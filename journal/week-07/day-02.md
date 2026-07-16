# Week 7 Day 2

- Собрал минимальный CLI для PR review: polling через GitHub REST API, stdout-only вывод и локальное состояние просмотренных PR.
- Добавил простой локальный RAG без embeddings: индексируются `README`, `AGENTS`, `.cursor/rules/*.mdc`, `lessons/*.md` и Python-код под `weeks/`, с бустом по путям изменённых файлов.
- Вынес вызов Dockhost в один `complete()` с retry и короткими логами `[retry]`, `[rag]`, `[pipeline]`, `[error]`.

Интересное:

- Получился "production-ish" пайплайн без лишней архитектуры: GitHub -> RAG -> LLM -> stdout.
- Для видео удобно, что по умолчанию это watcher, а для smoke/демо есть `--once` и `--pr`.

Проблемы и решения:

- Изолированный worktree вне репозитория упёрся в sandbox по правам записи, поэтому сделал отдельный worktree внутри репо на ветке `day32-pr-review`.
- Live-проверка зависит от `GITHUB_TOKEN`, `GITHUB_REPO` и `DOCKHOST_AI_KEY`; без них можно проверить только help, валидацию env и lint.

Вывод:

- На видео лучше показать `--once --pr <номер>`: видно и GitHub polling, и локальный RAG, и итоговый review без лишнего шума.
