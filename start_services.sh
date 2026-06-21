#!/usr/bin/env bash

set -euo pipefail

if command -v pm2 >/dev/null 2>&1; then
    pm2 flush
    pm2 start ecosystem.config.js
    pm2 save
    pm2 list
    exit 0
fi

echo "pm2 not found, using Termux launcher"
if [ -x "./termux/start.sh" ]; then
    ./termux/start.sh
else
    echo "Missing executable script: ./termux/start.sh"
    echo "Run: chmod +x termux/*.sh"
    exit 1
fi
