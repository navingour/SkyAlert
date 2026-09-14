#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────
# SkyAlert Service Installer (Auto-detects Linux systemd or macOS launchd)
# Enables SkyAlert to run as a background service and start automatically on boot.
# ─────────────────────────────────────────────────────────────────────────

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." >/dev/null 2>&1 && pwd )"
cd "$DIR"

OS="$(uname -s)"
CURRENT_USER="$(whoami)"

echo "========================================================="
echo "  🚀 SkyAlert Background Service Installer"
echo "  Detected OS: $OS"
echo "  Installation Directory: $DIR"
echo "  Service User: $CURRENT_USER"
echo "========================================================="

if [ "$OS" = "Linux" ]; then
    SERVICE_FILE="/etc/systemd/system/skyalert.service"
    
    echo "  📄 Generating systemd service unit at $SERVICE_FILE..."
    
    sudo bash -c "cat <<EOF > $SERVICE_FILE
[Unit]
Description=SkyAlert ADS-B Tracking & Alerting Platform
After=network.target network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=$DIR/start.sh
ExecStop=$DIR/stop.sh
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF"

    echo "  🔄 Reloading systemd daemon..."
    sudo systemctl daemon-reload
    
    echo "  ⚡ Enabling skyalert.service on system boot..."
    sudo systemctl enable skyalert.service
    
    echo "  ▶️  Starting skyalert.service..."
    sudo systemctl restart skyalert.service

    echo ""
    echo "========================================================="
    echo "  ✅ SkyAlert service installed and started successfully!"
    echo "========================================================="
    echo "  Useful Commands:"
    echo "    - Check status:  sudo systemctl status skyalert"
    echo "    - View live logs: sudo journalctl -u skyalert -f"
    echo "    - Restart:       sudo systemctl restart skyalert"
    echo "    - Stop:          sudo systemctl stop skyalert"
    echo "========================================================="

elif [ "$OS" = "Darwin" ]; then
    PLIST_DIR="$HOME/Library/LaunchAgents"
    PLIST_FILE="$PLIST_DIR/com.skyalert.app.plist"
    mkdir -p "$PLIST_DIR" "$DIR/logs"

    # Find python3 in venv or system
    PY_BIN="$DIR/.venv/bin/python3"
    if [ ! -f "$PY_BIN" ]; then
        PY_BIN="$DIR/venv/bin/python3"
    fi
    if [ ! -f "$PY_BIN" ]; then
        PY_BIN="$(which python3)"
    fi

    echo "  📄 Generating launchd agent at $PLIST_FILE..."
    cat <<EOF > "$PLIST_FILE"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.skyalert.app</string>
    <key>ProgramArguments</key>
    <array>
        <string>$DIR/start.sh</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$DIR/logs/skyalert.log</string>
    <key>StandardErrorPath</key>
    <string>$DIR/logs/skyalert.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.local/bin</string>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
</dict>
</plist>
EOF

    echo "  ⚡ Registering and starting launchd agent..."
    launchctl unload "$PLIST_FILE" 2>/dev/null || true
    launchctl load -w "$PLIST_FILE"

    echo ""
    echo "========================================================="
    echo "  ✅ SkyAlert background service installed and running!"
    echo "========================================================="
    echo "  Useful Commands:"
    echo "    - View live logs: tail -f $DIR/logs/skyalert.log"
    echo "    - Stop service:   launchctl unload $PLIST_FILE"
    echo "    - Start service:  launchctl load -w $PLIST_FILE"
    echo "    - Restart:        launchctl unload $PLIST_FILE && launchctl load -w $PLIST_FILE"
    echo "========================================================="
else
    echo "❌ Unsupported OS: $OS"
    exit 1
fi
