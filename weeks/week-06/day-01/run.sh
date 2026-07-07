#!/usr/bin/env bash
# Week 6 day 1 — локальная LLM (Ollama): проверка CLI и HTTP API.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"
OLLAMA_CHAT_MODEL="${OLLAMA_CHAT_MODEL:-qwen3:8b}"
PREVIEW_LEN="${PREVIEW_LEN:-200}"
# qwen3 по умолчанию «думает» — для демо отключаем (иначе минуты на простой запрос).
OLLAMA_THINK="${OLLAMA_THINK:-false}"

usage() {
  cat <<EOF
Usage: $(basename "$0") [--check | --demo]

  --check   Проверить Ollama и модель без генерации (smoke-test).
  --demo    Три запроса разной сложности: CLI + HTTP API (по умолчанию).

Переменные: OLLAMA_BASE_URL, OLLAMA_CHAT_MODEL, OLLAMA_THINK (см. .env.example).
EOF
}

preview() {
  local text="$1"
  local len=${#text}
  if (( len <= PREVIEW_LEN )); then
    printf '%s' "$text"
  else
    printf '%s… (%d chars)' "${text:0:PREVIEW_LEN}" "$len"
  fi
}

strip_ansi() {
  sed 's/\x1b\[[0-9;?]*[a-zA-Z]//g' | tr -d '\r'
}

check_ollama() {
  if ! command -v ollama >/dev/null 2>&1; then
    echo "[error] ollama не найден в PATH. Установите: https://ollama.com" >&2
    return 1
  fi
  echo "[check] ollama: $(ollama --version 2>&1 | head -1)"

  if ! curl -sf "${OLLAMA_BASE_URL}/api/tags" >/dev/null; then
    echo "[error] Ollama недоступен на ${OLLAMA_BASE_URL}. Запустите: ollama serve" >&2
    return 1
  fi
  echo "[check] server: ${OLLAMA_BASE_URL} OK"

  if ! curl -sf "${OLLAMA_BASE_URL}/api/tags" | grep -q "\"${OLLAMA_CHAT_MODEL}\""; then
    echo "[check] модель ${OLLAMA_CHAT_MODEL} не найдена — pull…"
    ollama pull "${OLLAMA_CHAT_MODEL}"
  fi
  echo "[check] model: ${OLLAMA_CHAT_MODEL} OK"
}

chat_cli() {
  local label="$1"
  local prompt="$2"
  echo ""
  echo "=== ${label} [cli] ==="
  echo "prompt: ${prompt}"
  local start end elapsed raw reply
  start=$(date +%s%N)
  # TERM=dumb — без braille-спиннера ollama run (⠙⠹⠸…), иначе в reply мусор.
  raw=$(TERM=dumb script -qefc \
    "ollama run ${OLLAMA_CHAT_MODEL} --think=${OLLAMA_THINK} --hidethinking --nowordwrap $(printf '%q' "$prompt")" \
    /dev/null 2>&1 || true)
  end=$(date +%s%N)
  elapsed=$(( (end - start) / 1000000 ))
  reply=$(printf '%s\n' "$raw" | strip_ansi | tr -d '\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
  echo "latency: ${elapsed} ms"
  echo "reply: $(preview "$reply")"
}

chat_http() {
  local label="$1"
  local prompt="$2"
  echo ""
  echo "=== ${label} [http] ==="
  echo "prompt: ${prompt}"
  local payload start end elapsed response reply
  payload=$(OLLAMA_MODEL="$OLLAMA_CHAT_MODEL" OLLAMA_PROMPT="$prompt" OLLAMA_THINK="$OLLAMA_THINK" python3 - <<'PY'
import json, os
print(json.dumps({
    "model": os.environ["OLLAMA_MODEL"],
    "messages": [{"role": "user", "content": os.environ["OLLAMA_PROMPT"]}],
    "stream": False,
    "think": os.environ["OLLAMA_THINK"].lower() == "true",
}))
PY
)
  start=$(date +%s%N)
  response=$(curl -sf "${OLLAMA_BASE_URL}/v1/chat/completions" \
    -H 'Content-Type: application/json' \
    -d "$payload")
  end=$(date +%s%N)
  elapsed=$(( (end - start) / 1000000 ))
  reply=$(OLLAMA_RESPONSE="$response" python3 - <<'PY'
import json, os
data = json.loads(os.environ["OLLAMA_RESPONSE"])
print(data["choices"][0]["message"]["content"])
PY
)
  echo "latency: ${elapsed} ms"
  echo "reply: $(preview "$reply")"
}

run_demo() {
  check_ollama
  echo ""
  echo "=== Week 6 day 1: local LLM demo (${OLLAMA_CHAT_MODEL}, think=${OLLAMA_THINK}) ==="

  # 1. простой факт — CLI
  chat_cli "1/3 simple" "What is 15 + 27? Reply with only the number."

  # 2. объяснение — HTTP OpenAI-compatible
  chat_http "2/3 medium" "Explain LLM quantization in one short sentence."

  # 3. рассуждение — HTTP
  chat_http "3/3 reasoning" \
    "A farmer has 17 sheep. All but 9 die. How many sheep are left? Think briefly, then give the final number only on the last line."

  echo ""
  echo "[done] local LLM отвечает через CLI и HTTP API."
}

MODE="demo"
case "${1:---demo}" in
  --check) MODE="check" ;;
  --demo|"") MODE="demo" ;;
  -h|--help) usage; exit 0 ;;
  *) echo "unknown option: $1" >&2; usage; exit 1 ;;
esac

if [[ "$MODE" == "check" ]]; then
  check_ollama
  echo "[done] check OK"
else
  run_demo
fi
