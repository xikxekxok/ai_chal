# Неделя 6, день 3

## Сделано

- Локальный RAG поверх Ollama `qwen3:8b`: два режима на вопрос — cite (5.4 rerank + JSON-цитаты) и simple (5.2 top-10).
- Перевод RU→EN через Dockhost (вне локального скоупа).
- Демо: 2 вопроса из 5.4 (плоды в помёте, король медведя).

## Интересное

- Разделение провайдеров: `complete_cloud()` только для translate, `complete_local()` для ответов.
- Индекс week-05 читается из `weeks/week-05/data/opossum_index.json`.

## Проблемы

- qwen3:8b на simple-режиме сначала ответил по-английски — усилена фраза «Answer in Russian only» в user prompt.
- cite-режим на CPU ~100+ с на ответ; для видео лучше `--no-pause`.

## Вывод

- Видео: `python weeks/week-06/day-03/main.py --demo`
- Smoke: `--show-index`, `--check`
