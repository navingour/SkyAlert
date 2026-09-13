#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────
# SkyAlert Stop Script
# Stops any running backend or web dashboard processes on port 8080.
# ─────────────────────────────────────────────────────────────────────────

echo "Stopping SkyAlert services..."

# Kill any process listening on port 8080
PIDS=$(lsof -ti:8080 2>/dev/null)
if [ -n "$PIDS" ]; then
    echo "Stopping web server on port 8080 (PID: $PIDS)..."
    kill $PIDS 2>/dev/null || true
    sleep 1
    kill -9 $PIDS 2>/dev/null || true
fi

# Kill any running app.backend.main processes
PIDS_BACKEND=$(pgrep -f "python.*app.backend.main" 2>/dev/null)
if [ -n "$PIDS_BACKEND" ]; then
    echo "Stopping backend collector engine (PID: $PIDS_BACKEND)..."
    kill $PIDS_BACKEND 2>/dev/null || true
fi

echo "SkyAlert stopped."
