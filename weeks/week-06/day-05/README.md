# Неделя 6, день 5 — «Анекдоты про опоссумов»

## Задание

Развернуть локальную LLM как HTTP-сервис и построить **генератор анекдотов**: пользователь выбирает от 1 до 10 тем, локальная Ollama генерирует один анекдот, вплетая все выбранные темы.

**Наш подход:** FastAPI + SSE-стрим к локальной Ollama `qwen3:4b` (thinking + answer) + веб-UI на **Alpine.js** (тёмная тема, без npm). Бекенд stateless; в UI ничего не сохраняется — после обновления страницы всё пусто. Деплой на VPS одним bash-скриптом.

## Результат

На видео (VPS):

1. `./weeks/week-06/day-05/run.sh` — сервис на `http://<VPS_IP>:8080/`.
2. Браузер: выбор 2–3 тем → «Сгенерировать» → стримятся размышление и текст анекдота.
3. Обновление страницы — пустой экран (нет localStorage).
4. `curl http://<VPS_IP>:8080/api/health` — доступ по сети.
5. Несколько запросов подряд — стабильность (`--stress` или `--stress-direct`).
6. Rate limit / обрезка контекста — `429` / `trimmed: true`.

## Подготовка (VPS)

```bash
git clone <repo-url> ai_chall && cd ai_chall
chmod +x weeks/week-06/day-05/run.sh

# Открыть порт 8080 в firewall (ufw / security group)
# Нужен sudo на Debian/Ubuntu — скрипт сам ставит curl, python3-venv, Ollama
./weeks/week-06/day-05/run.sh
```

Скрипт можно запускать из корня репо или из `weeks/week-06/day-05/` — он сам найдёт корень, создаст `.venv`, при необходимости установит Ollama (`install.sh`), подтянет `qwen3:4b` и запустит сервер на `0.0.0.0:8080`.

Опционально в `.env`:

```bash
HOST=0.0.0.0
PORT=8080
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=qwen3:4b
CHAT_RATE_LIMIT=10
CHAT_MAX_MESSAGES=40
CHAT_MAX_CHARS=12000
CHAT_NUM_CTX=4096
OLLAMA_TEMPERATURE=1.0
# OLLAMA_MAX_PREDICT=0        # 0 = не задавать (рекомендуется для qwen3+think)
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
| GET | `/` | Alpine.js UI (SSE) |
| GET | `/api/health` | Ollama + модель + лимиты |
| GET | `/api/themes` | Список из 10 захардкоженных тем |
| POST | `/api/chat/stream` | SSE: `thinking` → `content` → `done` |
| POST | `/api/chat` | Non-stream JSON (curl / `--stress`) |

SSE-события: `thinking`, `content`, `done`, `error`.

Ошибки: `429` rate limit, `502` Ollama недоступен.

## Агент

Системный промпт в `app/config.py` (`DEFAULT_SYSTEM_PROMPT`): автор коротких анекдотов про опоссумов. Темы — `OPPOSSUM_JOKE_THEMES` (10 штук). Переопределение промпта: `CHAT_SYSTEM_PROMPT` в `.env`.

**Провайдер:** только локальная Ollama в UI (`provider: "local"`). Thinking stream через native `/api/chat` с `think=true`.

## Проверки для видео

```bash
python weeks/week-06/day-05/main.py --check
python weeks/week-06/day-05/main.py --stress
python weeks/week-06/day-05/main.py --stress-direct
curl -s http://localhost:8080/api/health | python3 -m json.tool
curl -s http://localhost:8080/api/themes | python3 -m json.tool
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
- **`num_predict` не задаём** для локали (как day-04): иначе qwen3 съедает budget на thinking, content пустой.
- `CHAT_NUM_CTX=4096` — короткий system prompt, без истории чата.
- Без TLS и auth — для приватного VPS / LAN.
