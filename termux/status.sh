#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT_DIR/.termux/run"

show_status() {
    local name="$1"
    local pid_file="$2"

    if [ -f "$pid_file" ]; then
        local pid
        pid="$(cat "$pid_file")"
        if kill -0 "$pid" 2>/dev/null; then
            echo "$name: running (pid $pid)"
        else
            echo "$name: stale pid file ($pid)"
        fi
    else
        echo "$name: stopped"
    fi
}

show_status "redis" "$RUN_DIR/redis.pid"
show_status "checker" "$RUN_DIR/checker.pid"
show_status "worker" "$RUN_DIR/worker.pid"
show_status "beat" "$RUN_DIR/beat.pid"
show_status "bot" "$RUN_DIR/bot.pid"

if command -v redis-cli >/dev/null 2>&1; then
    if redis-cli -p "${REDIS_PORT:-6379}" ping >/dev/null 2>&1; then
        echo "redis ping: PONG"
    else
        echo "redis ping: failed"
    fi
fi
