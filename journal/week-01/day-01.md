# Неделя 1, день 1 — первый запрос к LLM

**Задание:** минимальный код → API LLM → ответ в консоль.

## Что сделали

- CLI `weeks/week-01/day-01/main.py`: OpenAI SDK + `base_url` Dockhost (`https://inference.dockhost.io/v1`), модель `deepseek/deepseek-v3.2`.
- Ключ в `.env` (`DOCKHOST_AI_KEY`), шаблон в `.env.example`.
- Запуск **из корня репозитория**: `python weeks/week-01/day-01/main.py` (`.env` ищется в корне).

## Интересное

- Dockhost — **OpenAI-compatible**: тот же `chat.completions`, что и у OpenAI; достаточно сменить `base_url` и ключ.
- Можно использовать и `OPENAI_API_KEY` / `OPENAI_BASE_URL` — SDK их понимает из коробки.

## Проблемы

- **pip в sandbox Cursor:** установка пакетов падала с «Неизвестное имя или служба» (DNS). Решение: установка/запрос с полными правами окружения (`all`), у себя локально обычно хватает обычного `pip install`.
- **Ключ в чате:** API-ключ попал в переписку — в git не коммитим; при утечке лучше перевыпустить в Dockhost.

## Вывод

Для сдачи на видео: `source .venv`, `pip install -r weeks/week-01/day-01/requirements.txt`, один-два запуска `main.py` с разным промптом в аргументах.
