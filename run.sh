#!/usr/bin/env bash
# AGY-GW Startup Script

set -e
cd "$(dirname "$0")"

export PORT=8789
export HOST=0.0.0.0
export AGY_BIN=$(which agy)

echo "Starting Antigravity Gateway on $HOST:$PORT..."
exec python3 main.py
