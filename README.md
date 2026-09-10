# SkyAlert — Station Control & Intelligence Platform

> A self-hosted, real-time ADS-B aircraft intelligence platform. Tracks, enriches, and visualises every aircraft that enters your receiver's range — with Telegram alerts, a live radar dashboard, fleet analytics, and a full historical database.

---

## ✨ Features

- **Live Airspace** — Real-time aircraft cards with speed, altitude, route & operator
- **Radar Map** — Live Leaflet.js radar map with aircraft markers
- **Emergency Squawk Detection** — Cards light up red for 7500/7600/7700 + Telegram alert
- **Aircraft Database** — Full enriched profile (registration, operator, manufacturer, history)
- **Detection Sessions** — Every visit logged with telemetry (altitude, speed, distance, bearing)
- **Operators & Types** — Analytics cards for every airline & aircraft type seen
- **Fleet Analytics** — Operator fleet intelligence
- **Global Analytics** — 24-hour traffic chart, top operators, top types
- **Weather Analytics** — Upper-air OAT/TAT thermal profiles from live aircraft data
- **Receiver Analytics** — Signal horizon map, RSSI vs distance curve
- **Formation Detection** — Detects aircraft flying in proximity
- **Rare Aircraft** — Flags aircraft seen fewer than N times
- **Alert History** — Full log of every triggered alert
- **Telegram Notifications** — Startup message, source health, emergency alerts

---

## 🖥️ Requirements

- Python **3.9+**
- A running **ADS-B receiver** with [tar1090](https://github.com/wiedehopf/tar1090) (or compatible `aircraft.json` feed)
- Linux (Debian/Ubuntu recommended) or macOS

---

## 🚀 Quick Start (Fresh Install)

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/SkyAlert-Full.git
cd SkyAlert-Full

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your config from the template
cp config/config.example.yaml config/config.yaml
nano config/config.yaml        # Set your receiver URL, Telegram token, etc.

# 5. Create required directories
mkdir -p data logs

# 6. Start SkyAlert
chmod +x start.sh
./start.sh
```

Open your browser at: **http://localhost:8080**

---

## 🔄 Upgrading an Existing Installation (Existing Database)

> **Important:** SkyAlert is designed to be fully backwards-compatible with existing databases.
> All schema changes use `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE ... ADD COLUMN` wrapped in try/except — **your existing data will never be deleted or altered.**

```bash
# 1. Go to your SkyAlert directory
cd /path/to/SkyAlert-Full

# 2. Pull the latest code
git pull origin main

# 3. Activate your virtual environment
source .venv/bin/activate

# 4. Install any new dependencies
pip install -r requirements.txt

# 5. DO NOT touch the data/ directory — your database stays exactly as-is.

# 6. Restart the app
./start.sh
```

The app will automatically detect your existing `data/skyalert_relational.db` and `data/aircraft.db` and continue using them without any modification.

---

## 📁 Project Structure

```
SkyAlert-Full/
├── app/                    # Core backend logic
│   ├── backend/            # ADS-B poller / collector
│   ├── core/               # Async engine
│   ├── aircraft_enricher.py
│   ├── db_manager.py       # Unified database manager
│   ├── event_database.py   # Alert history database
│   ├── notifier.py         # Telegram notification builder
│   ├── rules.py            # Alert rule engine
│   ├── session_tracker.py  # Detection session tracker
│   └── telegram.py         # Telegram sender
├── config/
│   ├── config.example.yaml # ← Copy this to config.yaml
│   └── config.yaml         # ← Your local config (git-ignored)
├── data/                   # Database files (git-ignored)
│   └── skyalert_relational.db
├── logs/                   # Log files (git-ignored)
├── web/                    # FastAPI web dashboard
│   ├── routers/            # API endpoints
│   ├── static/             # CSS, JS, images
│   └── templates/          # Jinja2 HTML templates
├── requirements.txt
├── start.sh                # ← Run this to start everything
└── start-web.sh            # Web-only start (for development)
```

---

## ⚙️ Configuration

All configuration lives in `config/config.yaml` (excluded from git). See [`config/config.example.yaml`](config/config.example.yaml) for the full reference with documentation for every option.

**Key settings:**

| Key | Description |
|-----|-------------|
| `tar1090.url` | Your ADS-B receiver's `aircraft.json` URL |
| `telegram.enabled` | Enable/disable Telegram alerts |
| `telegram.bot_token` | Your Telegram bot token |
| `telegram.chat_id` | Your Telegram chat ID |
| `alerts.squawk` | Enable emergency squawk alerts (7500/7600/7700) |

---

## 🐧 Running as a Systemd Service (Debian/Ubuntu)

To run SkyAlert automatically on boot:

```bash
sudo nano /etc/systemd/system/skyalert.service
```

Paste:

```ini
[Unit]
Description=SkyAlert Station Control
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/path/to/SkyAlert-Full
ExecStart=/path/to/SkyAlert-Full/.venv/bin/python3 -m app.backend.main
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

For the **web dashboard** as a separate service:

```ini
[Unit]
Description=SkyAlert Web Dashboard
After=network.target skyalert.service

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/path/to/SkyAlert-Full
ExecStart=/path/to/SkyAlert-Full/.venv/bin/uvicorn web.main:app --host 0.0.0.0 --port 8080
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable skyalert skyalert-web
sudo systemctl start skyalert skyalert-web
```

---

## 📄 License

MIT
