#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v pkg >/dev/null 2>&1; then
    echo "This script is intended to run inside Termux."
    exit 1
fi

pkg update -y
pkg install -y python git redis ffmpeg clang make libjpeg-turbo libpng zlib openssl

python -m venv "$ROOT_DIR/.venv"
source "$ROOT_DIR/.venv/bin/activate"

python -m pip install --upgrade pip setuptools wheel
pip install -r "$ROOT_DIR/requirements-termux.txt"

mkdir -p "$ROOT_DIR/storage" "$ROOT_DIR/.termux/logs" "$ROOT_DIR/.termux/run" "$ROOT_DIR/.termux/redis"

if [ ! -f "$ROOT_DIR/.env" ] && [ -f "$ROOT_DIR/.env.termux.example" ]; then
    cp "$ROOT_DIR/.env.termux.example" "$ROOT_DIR/.env"
    echo "Created .env from .env.termux.example"
fi

if ! command -v xray >/dev/null 2>&1; then
    echo "xray binary not found in PATH."
    echo "Install xray for full checker functionality, then set XRAY_BIN in .env if needed."
fi

echo "Setup complete. Edit .env and run: bash termux/start.sh"
