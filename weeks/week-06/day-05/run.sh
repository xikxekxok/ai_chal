#!/usr/bin/env bash
# Week 6 day 5 — bootstrap на VPS: venv, Ollama, qwen3:4b, веб-сервис.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

DAY="weeks/week-06/day-05"
PORT="${PORT:-8080}"
HOST="${HOST:-0.0.0.0}"
OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"
OLLAMA_CHAT_MODEL="${OLLAMA_CHAT_MODEL:-qwen3:4b}"
OLLAMA_THINK="${OLLAMA_THINK:-false}"

usage() {
  cat <<EOF
Usage: $(basename "$0") [--check]

  Без флагов — поднять чат-сервис на http://${HOST}:${PORT}/
  --check   Только проверки (Ollama, модель, venv), без serve.

Переменные: HOST, PORT, OLLAMA_BASE_URL, OLLAMA_CHAT_MODEL, OLLAMA_THINK.
EOF
}

log() { echo "[run.sh] $*"; }

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[error] $1 не найден в PATH." >&2
    exit 1
  fi
}

setup_venv() {
  if [[ ! -d .venv ]]; then
    log "создаю .venv…"
    python3 -m venv .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -q -r "${DAY}/requirements.txt"
}

ollama_ready() {
  curl -sf "${OLLAMA_BASE_URL}/api/tags" >/dev/null 2>&1
}

ensure_ollama() {
  require_cmd ollama
  if ollama_ready; then
    log "Ollama уже отвечает на ${OLLAMA_BASE_URL}"
    return
  fi
  log "запускаю ollama serve в фоне…"
  nohup ollama serve >/tmp/ollama-serve.log 2>&1 &
  for _ in $(seq 1 30); do
    if ollama_ready; then
      log "Ollama готов"
      return
    fi
    sleep 1
  done
  echo "[error] Ollama не поднялся за 30 с. См. /tmp/ollama-serve.log" >&2
  exit 1
}

ensure_model() {
  if curl -sf "${OLLAMA_BASE_URL}/api/tags" | grep -q "\"${OLLAMA_CHAT_MODEL}\""; then
    log "модель ${OLLAMA_CHAT_MODEL} уже есть"
    return
  fi
  log "pull ${OLLAMA_CHAT_MODEL}…"
  ollama pull "${OLLAMA_CHAT_MODEL}"
}

MODE="serve"
case "${1:-}" in
  --check) MODE="check" ;;
  -h|--help) usage; exit 0 ;;
  "") ;;
  *) echo "unknown option: $1" >&2; usage; exit 1 ;;
esac

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

require_cmd python3
setup_venv
ensure_ollama
ensure_model

export HOST PORT OLLAMA_BASE_URL OLLAMA_CHAT_MODEL OLLAMA_THINK

python "${DAY}/main.py" --check

if [[ "$MODE" == "check" ]]; then
  log "check OK"
  exit 0
fi

log "старт сервера: http://${HOST}:${PORT}/"
exec python "${DAY}/main.py" --serve
