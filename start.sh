#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────
# SkyAlert Master Startup Script
# Boots the Unified ADS-B Collector & Web Intelligence Platform
# ─────────────────────────────────────────────────────────────────────────

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# Activate virtual environment if present
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

# Auto-create config from example if missing
if [ ! -f "config/config.yaml" ]; then
    if [ -f "config/config.example.yaml" ]; then
        echo "  ℹ️  Creating initial config/config.yaml from example template..."
        cp config/config.example.yaml config/config.yaml
    fi
fi

mkdir -p data logs data/cache

# Ensure port 8080 is clear
OLD_PORT_PID=$(lsof -ti:8080 2>/dev/null)
if [ -n "$OLD_PORT_PID" ]; then
    kill -9 $OLD_PORT_PID 2>/dev/null || true
    sleep 1
fi

exec python3 main.py "$@"

