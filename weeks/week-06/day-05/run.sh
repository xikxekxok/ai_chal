#!/usr/bin/env bash
# Week 6 day 5 — bootstrap на VPS: venv, Ollama, qwen3:4b, «Анекдоты про опоссумов».
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
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

  Без флагов — поднять генератор на http://${HOST}:${PORT}/
  --check   Только проверки (Ollama, модель, venv), без serve.

Скрипт сам ставит недостающее (apt: curl, python3-venv; Ollama — install.sh).
Нужен sudo на Debian/Ubuntu VPS.

Переменные: HOST, PORT, OLLAMA_BASE_URL, OLLAMA_CHAT_MODEL, OLLAMA_THINK.
EOF
}

log() { echo "[run.sh] $*"; }

has_cmd() { command -v "$1" >/dev/null 2>&1; }

apt_install() {
  local pkgs=("$@")
  if ! has_cmd apt-get; then
    echo "[error] apt-get не найден; установите вручную: ${pkgs[*]}" >&2
    exit 1
  fi
  if has_cmd sudo; then
    sudo apt-get update -qq
    sudo apt-get install -y "${pkgs[@]}"
  else
    apt-get update -qq
    apt-get install -y "${pkgs[@]}"
  fi
}

ensure_curl() {
  if has_cmd curl; then
    return
  fi
  log "curl не найден — ставлю…"
  apt_install curl
}

ensure_python3() {
  if has_cmd python3; then
    return
  fi
  log "python3 не найден — ставлю…"
  apt_install python3 python3-venv python3-pip
}

setup_venv() {
  ensure_python3
  if [[ ! -f .venv/bin/activate ]]; then
    if [[ -d .venv ]]; then
      log "битый .venv — пересоздаю…"
      rm -rf .venv
    else
      log "создаю .venv…"
    fi
    if ! python3 -m venv .venv 2>/dev/null; then
      log "python3-venv не хватает — ставлю…"
      apt_install python3-venv
      python3 -m venv .venv
    fi
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -q -r "${DAY}/requirements.txt"
}

ollama_bin() {
  if has_cmd ollama; then
    command -v ollama
    return
  fi
  if [[ -x /usr/local/bin/ollama ]]; then
    echo /usr/local/bin/ollama
    return
  fi
  return 1
}

install_ollama() {
  ensure_curl
  log "Ollama не найден — ставлю через https://ollama.com/install.sh …"
  if has_cmd sudo; then
    curl -fsSL https://ollama.com/install.sh | sudo sh
  else
    curl -fsSL https://ollama.com/install.sh | sh
  fi
  export PATH="/usr/local/bin:${PATH}"
}

ensure_ollama_binary() {
  if ollama_bin >/dev/null; then
    return
  fi
  install_ollama
  if ! ollama_bin >/dev/null; then
    echo "[error] Ollama установлен, но бинарник не найден в PATH." >&2
    exit 1
  fi
}

ollama_cmd() {
  ollama_bin
}

ollama_ready() {
  curl -sf "${OLLAMA_BASE_URL}/api/tags" >/dev/null 2>&1
}

start_ollama_server() {
  local bin
  bin="$(ollama_cmd)"

  if ollama_ready; then
    log "Ollama уже отвечает на ${OLLAMA_BASE_URL}"
    return
  fi

  if has_cmd systemctl && systemctl list-unit-files 2>/dev/null | grep -q '^ollama\.service'; then
    log "запускаю systemd ollama…"
    if has_cmd sudo; then
      sudo systemctl start ollama || true
    else
      systemctl start ollama || true
    fi
  else
    log "запускаю ${bin} serve в фоне…"
    nohup "${bin}" serve >/tmp/ollama-serve.log 2>&1 &
  fi

  for _ in $(seq 1 60); do
    if ollama_ready; then
      log "Ollama готов"
      return
    fi
    sleep 1
  done
  echo "[error] Ollama не поднялся за 60 с. См. /tmp/ollama-serve.log или journalctl -u ollama" >&2
  exit 1
}

ensure_model() {
  local bin
  bin="$(ollama_cmd)"
  if curl -sf "${OLLAMA_BASE_URL}/api/tags" | grep -q "\"${OLLAMA_CHAT_MODEL}\""; then
    log "модель ${OLLAMA_CHAT_MODEL} уже есть"
    return
  fi
  log "pull ${OLLAMA_CHAT_MODEL}…"
  "${bin}" pull "${OLLAMA_CHAT_MODEL}"
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

ensure_curl
setup_venv
ensure_ollama_binary
start_ollama_server
ensure_model

export HOST PORT OLLAMA_BASE_URL OLLAMA_CHAT_MODEL OLLAMA_THINK

python "${DAY}/main.py" --check

if [[ "$MODE" == "check" ]]; then
  log "check OK"
  exit 0
fi

log "старт сервера: http://${HOST}:${PORT}/"
exec python "${DAY}/main.py" --serve
