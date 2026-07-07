# Неделя 6, день 1

- День 26: Ollama + `qwen3:8b`, скрипт `run.sh` вместо Python.
- `--check` — smoke без генерации; `--demo` — 3 запроса (CLI + HTTP).
- Модель ~5 GB, pull ~2 мин.
- **Проблема:** qwen3 с thinking по умолчанию — `ollama run` в скрипте зависал; фикс `--think=false` + `OLLAMA_THINK=false`.

**Вывод для видео:** `./weeks/week-06/day-01/run.sh --demo` из корня репо.
