#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────
# SkyAlert Service Uninstaller
# Removes SkyAlert from background autostart
# ─────────────────────────────────────────────────────────────────────────

set -e

OS="$(uname -s)"

if [ "$OS" = "Linux" ]; then
    echo "Stopping and disabling skyalert.service..."
    sudo systemctl stop skyalert.service 2>/dev/null || true
    sudo systemctl disable skyalert.service 2>/dev/null || true
    sudo rm -f /etc/systemd/system/skyalert.service
    sudo systemctl daemon-reload
    echo "✅ Linux systemd service removed."
elif [ "$OS" = "Darwin" ]; then
    PLIST_FILE="$HOME/Library/LaunchAgents/com.skyalert.app.plist"
    echo "Stopping and removing macOS launchd agent..."
    launchctl unload "$PLIST_FILE" 2>/dev/null || true
    rm -f "$PLIST_FILE"
    echo "✅ macOS launchd service removed."
fi
