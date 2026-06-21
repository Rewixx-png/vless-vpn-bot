#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT_DIR/.termux/run"

stop_pidfile() {
    local name="$1"
    local pid_file="$2"

    if [ ! -f "$pid_file" ]; then
        echo "$name not running (no pid file)"
        return
    fi

    local pid
    pid="$(cat "$pid_file")"

    if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
        sleep 0.5
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null || true
        fi
        echo "stopped $name (pid $pid)"
    else
        echo "$name pid file exists, process not active"
    fi

    rm -f "$pid_file"
}

stop_pidfile "bot" "$RUN_DIR/bot.pid"
stop_pidfile "beat" "$RUN_DIR/beat.pid"
stop_pidfile "worker" "$RUN_DIR/worker.pid"
stop_pidfile "checker" "$RUN_DIR/checker.pid"

if command -v redis-cli >/dev/null 2>&1; then
    redis-cli -p "${REDIS_PORT:-6379}" shutdown nosave >/dev/null 2>&1 || true
fi
stop_pidfile "redis" "$RUN_DIR/redis.pid"

echo "done"
