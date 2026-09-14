<div align="center">

# ✈️ SkyAlert

### Self-Hosted ADS-B Tactical Aviation Intelligence & Fixed Station Platform

[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Database](https://img.shields.io/badge/Database-SQLite%20%7C%20PostgreSQL-336791?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![ADS-B Ready](https://img.shields.io/badge/ADS--B-Feed%20Ready-FF6B00?style=for-the-badge&logo=radar&logoColor=white)](#-receiver-compatibility)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

<p align="center">
  <b>Transform any ADS-B receiver into an enterprise-grade tactical air intelligence center.</b><br>
  Real-time tracking • Proximity geofencing • Instant Telegram photo alerts • Rare airframe radar • Zero-bloat database.
</p>

</div>

---

## 🌟 Key Highlights

- **⚡ Zero-Config Unified Architecture**: Start the entire platform (Web Dashboard + ADS-B Collector) with a single command (`python3 main.py` or `./start.sh`).
- **🛰️ Live Airspace & Tactical Radar**: High-refresh live cards, Leaflet.js radar map, closest point of approach (CPA), Mach, true airspeed (TAS), and vertical climb/descent vectors.
- **💬 Interactive Telegram Automation Hub**: Configure bot tokens directly in the UI, verify connection with live `getMe` API checks, send rich aircraft photo alert cards, and monitor custom aircraft targets with vicinity distance radius triggers.
- **🚁 Rare Aircraft & Helicopter Intelligence**: Dedicated classification radar for helicopters (Bell, Eurocopter, AW139, Mi-17, HAL), military tactical transports/fighters, heavy airframes (A380, B747, C-17, Beluga), and one-time visitors.
- **📉 Smart Telemetry Sampling**: Preserves 100% of flight visits, CPA distance, and bearings while throttling raw observation pings to 30-second trajectory intervals — **slashing database storage by 95%+**.
- **🔍 Offline-First Auto-Enrichment**: Bundled with a 625,000+ aircraft database (`data/reference/aircraft.csv`) for instant offline lookup of tail numbers, models, and registered operators.
- **🔄 Dual Relational Database Engine**: Native auto-bootstrapping SQLite WAL engine for standalone use, with seamless enterprise PostgreSQL support via `DATABASE_URL`.
- **🧰 Standalone Migration Tool**: Built-in CLI tool (`scripts/migrate_database.py`) to effortlessly migrate legacy databases into the unified relational schema.

---

## 📸 Platform Capabilities

```
┌────────────────────────────────────────────────────────────────────────┐
│                        SKYALERT MASTER PLATFORM                        │
├────────────────────────────────────────────────────────────────────────┤
│  [🛰️ Live Airspace]   [🗺️ Radar Map]   [🚁 Rare Aircraft]   [💬 Telegram] │
│                                                                        │
│  • Tactical Live Cards with Flight, Reg, Type, Alt, GS, CPA & Bearing  │
│  • Squawk 7700 / 7600 / 7500 Emergency Alert Matrix                    │
│  • Vicinity Proximity Geofencing (< 25km, 50km, 100km radius alerts)   │
│  • Upper-Air Weather Analytics (OAT / TAT thermal profiles)            │
│  • Signal Horizon & RSSI Reception Polar Coverage                      │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start (Native Install)

### 1. Clone & Setup
```bash
git clone https://github.com/navingour/SkyAlert-Full.git
cd SkyAlert-Full
```

### 2. Create Virtual Environment & Install Dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Launch SkyAlert
```bash
chmod +x start.sh stop.sh
./start.sh
```

> **Note:** If `config/config.yaml` is not present, SkyAlert will automatically bootstrap one from `config/config.example.yaml` on first launch!

Open your browser at **`http://localhost:8080`** (or `http://YOUR_SERVER_IP:8080`).

---

## ⚙️ Configuration Guide

All settings are managed via `config/config.yaml` or directly inside the **Web Settings / Telegram UI**.

```yaml
# config/config.yaml

general:
  poll_interval: 5               # Receiver polling rate in seconds

# Receiver feed endpoint (tar1090 / readsb / dump1090-fa)
tar1090:
  url: "http://192.168.0.132/tar1090/data/aircraft.json"

# Station reference coordinates (for distance, bearing, and proximity alerts)
station:
  latitude: 22.5726
  longitude: 88.3639
  name: "Primary Ground Station"

# Smart sampling (prevents database bloat)
collector:
  session_timeout_minutes: 10
  telemetry:
    enabled: true
    sample_interval_sec: 30     # Trajectory breadcrumb interval

# Telegram Alerting
telegram:
  enabled: true
  bot_token: "YOUR_TELEGRAM_BOT_TOKEN"
  chat_id: "YOUR_TELEGRAM_CHAT_ID"
  photo_enabled: true

# Alert scenarios
alerts:
  squawk: true                  # Emergency 7700, 7600, 7500
  military: true                # Military airframes & callsigns
  helicopters: true             # Rotorcraft & helicopters
  rare_aircraft: true           # A380, B747, C-17, low-visit passes
  watchlist: true               # Tracked aircraft in station vicinity
```

### Database Options:
- **SQLite (Default / Zero-Config)**: Leave `DATABASE_URL` empty or use `sqlite:///data/skyalert_relational.db`.
- **PostgreSQL**: Set `DATABASE_URL` in `.env` or in `config.yaml`:
  ```bash
  DATABASE_URL=postgresql://user:password@localhost:5432/skyalert
  ```

---

## 📡 Receiver Compatibility

SkyAlert seamlessly ingests data from any ADS-B receiver stack outputting standard JSON:

| Receiver Stack | Default Feed Endpoint |
|---|---|
| **tar1090** | `http://<ip>/tar1090/data/aircraft.json` |
| **readsb** | `http://<ip>/readsb/data/aircraft.json` or `/run/readsb/aircraft.json` |
| **dump1090-fa (PiAware)** | `http://<ip>/dump1090-fa/data/aircraft.json` |
| **Ultrafeeder (sdr-enthusiasts)** | `http://<ip>:8080/data/aircraft.json` |
| **Flightradar24 / RadarBox** | Any local or network `aircraft.json` endpoint |

---

## 💬 Telegram Proximity & Threat Alerts

SkyAlert includes an in-app Telegram Hub:
1. **Live Token Verification**: Test bot tokens against the Telegram API directly from the Web UI.
2. **Rich Photo Alert Cards**: Messages include registration, operator, altitude, ground speed, distance from station, squawk code, and aircraft photo attachments.
3. **Custom Target Tracking with Geofence Radius**: Track specific operators, callsign prefixes (e.g. `IAF`, `RCH`), registrations, or ICAO hex codes only when they enter a specific distance (e.g., `< 50 km`) from your station.

---

## 🧰 Database Migration Utility

If you have legacy database files (`aircraft.db` or `skyalert.db`) from earlier tools, migrate them with zero data loss using the standalone CLI:

```bash
# Migrate to local SQLite database:
python3 scripts/migrate_database.py --source "data/legacy_aircraft.db" --target "sqlite:///data/skyalert_relational.db"

# Or migrate to PostgreSQL:
python3 scripts/migrate_database.py --source "data/legacy_aircraft.db" --target "postgresql://user:pass@localhost:5432/skyalert"
```

---

## 🐧 Running as a Systemd Service (Linux / Raspberry Pi)

To keep SkyAlert running 24/7 and automatically start on boot:

```bash
sudo nano /etc/systemd/system/skyalert.service
```

Paste the configuration (replace `/path/to/SkyAlert-Full` and `YOUR_USERNAME`):

```ini
[Unit]
Description=SkyAlert Tactical Aviation Intelligence Platform
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/path/to/SkyAlert-Full
ExecStart=/path/to/SkyAlert-Full/.venv/bin/python3 /path/to/SkyAlert-Full/main.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now skyalert
```

View live logs:
```bash
journalctl -u skyalert -f
```

---

## 📁 Repository Structure

```
SkyAlert-Full/
├── app/
│   ├── collector/              # Unified ADS-B async poller & session manager
│   ├── aircraft_enricher.py    # Offline-first CSV lookup & metadata enricher
│   ├── analytics_service.py    # Multi-timeframe SQL KPIs & chart aggregation
│   ├── db_manager.py           # Universal PostgreSQL / SQLite relational manager
│   ├── notifier.py             # HTML alert card builder
│   ├── rules.py                # Alert rule engine & vicinity target evaluator
│   └── telegram.py             # Asynchronous Telegram notification client
├── config/
│   ├── config.example.yaml     # Master configuration blueprint
│   └── config.yaml             # User configuration (git-ignored)
├── data/
│   ├── reference/              # Local 625,000+ airframe CSV database
│   └── skyalert_relational.db  # Zero-config SQLite database (git-ignored)
├── scripts/
│   └── migrate_database.py     # Standalone database migration CLI
├── web/
│   ├── routers/                # FastAPI API, Dashboard, WebSocket & Settings routers
│   ├── static/                 # CSS styling, Leaflet maps, and JS engine
│   └── templates/              # Modern responsive HTML dashboard templates
├── main.py                     # Master application entry point
├── requirements.txt            # Python dependencies
├── start.sh                    # One-click start script
└── stop.sh                     # Graceful stop script
```

---

<div align="center">
<sub>SkyAlert is open-source software released under the <a href="LICENSE">MIT License</a>.</sub>
</div>
