#!/usr/bin/env bash
# Week 6 day 5 — bootstrap на VPS: venv, Ollama, qwen3:4b, «Анекдоты про опоссумов».
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
cd "$ROOT"

DAY="weeks/week-06/day-05"
RUN_DIR="${ROOT}/${DAY}/.run"
PORT="${PORT:-8080}"
HOST="${HOST:-0.0.0.0}"
OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"
OLLAMA_CHAT_MODEL="${OLLAMA_CHAT_MODEL:-qwen3:4b}"
OLLAMA_THINK="${OLLAMA_THINK:-false}"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

PID_FILE="${RUN_DIR}/server.pid"
LOG_FILE="${RUN_DIR}/server.log"

usage() {
  cat <<EOF
Usage: $(basename "$0") [start|stop|restart|status|logs|check]

  start     Bootstrap + сервер в фоне (по умолчанию)
  stop      Остановить сервер
  restart   stop + start
  status    PID и health
  logs      Хвост лога (follow в TTY)
  check     Только bootstrap и main.py --check, без serve

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

bootstrap() {
  ensure_curl
  setup_venv
  ensure_ollama_binary
  start_ollama_server
  ensure_model
  export HOST PORT OLLAMA_BASE_URL OLLAMA_CHAT_MODEL OLLAMA_THINK
  python "${DAY}/main.py" --check
}

server_pid() {
  if [[ -f "$PID_FILE" ]]; then
    cat "$PID_FILE"
  fi
}

is_running() {
  local pid
  pid="$(server_pid || true)"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

start_app() {
  if is_running; then
    log "уже запущен pid=$(server_pid) → http://${HOST}:${PORT}/"
    return 0
  fi

  bootstrap
  mkdir -p "$RUN_DIR"

  log "старт сервера в фоне → http://${HOST}:${PORT}/"
  nohup env \
    HOST="$HOST" \
    PORT="$PORT" \
    OLLAMA_BASE_URL="$OLLAMA_BASE_URL" \
    OLLAMA_CHAT_MODEL="$OLLAMA_CHAT_MODEL" \
    OLLAMA_THINK="$OLLAMA_THINK" \
    python "${DAY}/main.py" --serve >>"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"

  for _ in $(seq 1 15); do
    if curl -sf "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then
      log "OK pid=$(server_pid) log=${LOG_FILE}"
      return 0
    fi
    if ! is_running; then
      echo "[error] процесс упал при старте, см. ${LOG_FILE}" >&2
      rm -f "$PID_FILE"
      tail -n 30 "$LOG_FILE" >&2 || true
      exit 1
    fi
    sleep 1
  done

  log "процесс pid=$(server_pid) жив, health ещё не ответил — см. ${LOG_FILE}"
}

stop_app() {
  local pid
  if ! is_running; then
    rm -f "$PID_FILE"
    log "сервер не запущен"
    return 0
  fi
  pid="$(server_pid)"
  log "останавливаю pid=${pid}…"
  kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 10); do
    if ! kill -0 "$pid" 2>/dev/null; then
      rm -f "$PID_FILE"
      log "остановлен"
      return 0
    fi
    sleep 1
  done
  log "SIGTERM не помог — kill -9"
  kill -9 "$pid" 2>/dev/null || true
  rm -f "$PID_FILE"
  log "остановлен принудительно"
}

status_app() {
  if is_running; then
    log "running pid=$(server_pid) url=http://${HOST}:${PORT}/ log=${LOG_FILE}"
    if curl -sf "http://127.0.0.1:${PORT}/api/health" | python3 -m json.tool 2>/dev/null; then
      return 0
    fi
    log "health: не отвечает (процесс жив)"
    return 1
  fi
  rm -f "$PID_FILE"
  log "not running"
  return 1
}

logs_app() {
  if [[ ! -f "$LOG_FILE" ]]; then
    echo "[error] лог не найден: ${LOG_FILE}" >&2
    exit 1
  fi
  if [[ -t 1 ]]; then
    tail -f "$LOG_FILE"
  else
    tail -n 80 "$LOG_FILE"
  fi
}

CMD="${1:-start}"
case "$CMD" in
  start|"") CMD=start ;;
  stop|restart|status|logs|check|--check) ;;
  -h|--help) usage; exit 0 ;;
  *) echo "unknown command: $CMD" >&2; usage; exit 1 ;;
esac

case "$CMD" in
  start) start_app ;;
  stop) stop_app ;;
  restart) stop_app; start_app ;;
  status) status_app ;;
  logs) logs_app ;;
  check|--check)
    bootstrap
    log "check OK"
    ;;
esac
