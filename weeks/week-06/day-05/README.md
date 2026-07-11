# Неделя 6, день 5 — локальная LLM как приватный HTTP-сервис

## Задание

Развернуть локальную LLM как сервис с HTTP API и чатом. Проверить доступ по сети, стабильность при нескольких запросах, базовые ограничения (rate limit / max context).

**Наш подход:** одно Python-приложение (FastAPI) — SSE-стрим к локальной Ollama `qwen3:4b` (thinking + answer) + веб-чат на **Alpine.js** (светлая тема, без npm). Бекенд stateless; история в `localStorage`. Деплой на VPS одним bash-скриптом.

## Результат

На видео (VPS):

1. `./weeks/week-06/day-05/run.sh` — сервис на `http://<VPS_IP>:8080/`.
2. Чат в браузере: thinking и ответ стримятся; refresh — история с collapsible thinking.
3. `curl http://<VPS_IP>:8080/api/health` — доступ по сети.
4. Несколько запросов подряд — стабильность (`--stress` или `--stress-direct`).
5. Rate limit / обрезка контекста — `429` / `trimmed: true`.

## Подготовка (VPS)

```bash
git clone <repo-url> ai_chall && cd ai_chall
chmod +x weeks/week-06/day-05/run.sh

# Ollama: https://ollama.com (если ещё нет)
# Открыть порт 8080 в firewall (ufw / security group)
./weeks/week-06/day-05/run.sh
```

Скрипт: venv + deps, `ollama serve` (если нужно), `ollama pull qwen3:4b`, запуск сервера на `0.0.0.0:8080`.

Опционально в `.env`:

```bash
HOST=0.0.0.0
PORT=8080
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=qwen3:4b
CHAT_RATE_LIMIT=10
CHAT_MAX_MESSAGES=40
CHAT_MAX_CHARS=12000
CHAT_MAX_TOKENS=2048
CHAT_NUM_CTX=4096
```

## Запуск локально

```bash
source .venv/bin/activate
pip install -r weeks/week-06/day-05/requirements.txt

ollama serve
ollama pull qwen3:4b

python weeks/week-06/day-05/main.py --check   # smoke без генерации
python weeks/week-06/day-05/main.py --serve   # http://localhost:8080/
```

## API

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/` | Alpine.js чат (SSE) |
| GET | `/api/health` | Ollama + модель + лимиты |
| POST | `/api/chat/stream` | SSE: `thinking` → `content` → `done` |
| POST | `/api/chat` | Non-stream JSON (curl / `--stress`) |

SSE-события: `thinking`, `content`, `done`, `error`.

Ошибки: `429` rate limit, `502` Ollama недоступен.

## Проверки для видео

```bash
python weeks/week-06/day-05/main.py --check
python weeks/week-06/day-05/main.py --stress
python weeks/week-06/day-05/main.py --stress-direct
curl -s http://localhost:8080/api/health | python3 -m json.tool
```

## Статус

- [ ] Код готов
- [ ] Видео записано
- [ ] Ссылка в таблице курса
- [ ] Обновлён [submissions.md](../../../submissions.md)

## Артефакты

| Тип | Ссылка |
|-----|--------|
| Видео | |
| Код | `weeks/week-06/day-05/` |

## Заметки

- Ollama слушает только localhost; наружу — только веб-приложение.
- qwen3 reasoning: native `/api/chat` с `think=true`, `stream=true` (как day-04).
- `CHAT_MAX_TOKENS=2048` — запас под thinking + answer.
- Без TLS и auth — для приватного VPS / LAN.
