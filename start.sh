#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────
# SkyAlert Startup Script
# Starts both the ADS-B backend engine AND the web dashboard together.
# ─────────────────────────────────────────────────────────────────────────

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

# Check config exists
if [ ! -f "config/config.yaml" ]; then
    echo ""
    echo "  ⚠️  ERROR: config/config.yaml not found!"
    echo "  Please copy the example config and fill in your settings:"
    echo ""
    echo "    cp config/config.example.yaml config/config.yaml"
    echo "    nano config/config.yaml"
    echo ""
    exit 1
fi

# Check data directory exists
mkdir -p data logs

echo ""
echo "  ✈  SkyAlert Station Control - Starting..."
echo "  ────────────────────────────────────────────"
echo ""

# Start the backend engine in the background
echo "  [1/2] Starting ADS-B backend engine..."
python3 -m app.backend.main &
BACKEND_PID=$!
echo "        Backend PID: $BACKEND_PID"

sleep 2

# Ensure port 8080 is clear
OLD_PORT_PID=$(lsof -ti:8080 2>/dev/null)
if [ -n "$OLD_PORT_PID" ]; then
    echo "  ⚠️  Port 8080 is in use (PID: $OLD_PORT_PID). Clearing it..."
    kill -9 $OLD_PORT_PID 2>/dev/null || true
    sleep 1
fi

# Start the web dashboard
echo "  [2/2] Starting web dashboard on port 8080..."
echo ""
exec python3 -m uvicorn web.main:app --host 0.0.0.0 --port 8080

# Cleanup on exit
trap "kill $BACKEND_PID 2>/dev/null" EXIT
