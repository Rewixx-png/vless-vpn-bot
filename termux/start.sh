#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT_DIR/.termux/run"
LOG_DIR="$ROOT_DIR/.termux/logs"
REDIS_DIR="$ROOT_DIR/.termux/redis"
PY_BIN="$ROOT_DIR/.venv/bin/python"

mkdir -p "$RUN_DIR" "$LOG_DIR" "$REDIS_DIR"

if [ ! -x "$PY_BIN" ]; then
    echo "Python venv not found. Run: bash termux/setup.sh"
    exit 1
fi

if [ ! -f "$ROOT_DIR/.env" ]; then
    echo "Missing .env file. Copy .env.termux.example to .env and fill values."
    exit 1
fi

cd "$ROOT_DIR"

is_running() {
    local pid_file="$1"
    [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null
}

start_bg() {
    local name="$1"
    local pid_file="$2"
    local log_file="$3"
    shift 3

    if is_running "$pid_file"; then
        echo "$name already running (pid $(cat "$pid_file"))"
        return
    fi

    nohup "$@" >> "$log_file" 2>&1 &
    echo $! > "$pid_file"
    echo "started $name (pid $(cat "$pid_file"))"
}

if command -v redis-server >/dev/null 2>&1; then
    if is_running "$RUN_DIR/redis.pid"; then
        echo "redis already running (pid $(cat "$RUN_DIR/redis.pid"))"
    else
        redis-server \
            --daemonize yes \
            --port "${REDIS_PORT:-6379}" \
            --dir "$REDIS_DIR" \
            --pidfile "$RUN_DIR/redis.pid" \
            --logfile "$LOG_DIR/redis.log"
        echo "started redis (pid $(cat "$RUN_DIR/redis.pid"))"
    fi
else
    echo "redis-server not found; install redis package in Termux"
fi

start_bg "checker" "$RUN_DIR/checker.pid" "$LOG_DIR/checker.log" \
    "$PY_BIN" "$ROOT_DIR/utils/checker/service.py"

start_bg "worker" "$RUN_DIR/worker.pid" "$LOG_DIR/worker.log" \
    "$PY_BIN" -m celery -A celery_app worker -Q high_priority,low_priority -n worker_termux@%h -c 1 --prefetch-multiplier=1 --loglevel=INFO

start_bg "beat" "$RUN_DIR/beat.pid" "$LOG_DIR/beat.log" \
    "$PY_BIN" -m celery -A celery_app beat --schedule "$ROOT_DIR/.termux/celerybeat-schedule" --loglevel=INFO

start_bg "bot" "$RUN_DIR/bot.pid" "$LOG_DIR/bot.log" \
    "$PY_BIN" "$ROOT_DIR/bot.py"

echo "all services requested; check status: bash termux/status.sh"
