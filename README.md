<div align="center">

<img src="web/static/img/logo.png" alt="SkyAlert Logo" width="120" />

# SkyAlert

### Self-Hosted ADS-B Tactical Aviation Intelligence & Fixed Station Platform

[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/Database-SQLite%20%7C%20PostgreSQL-336791?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![ADS-B Ready](https://img.shields.io/badge/ADS--B-Feed%20Ready-FF6B00?style=for-the-badge)](https://www.dump1090.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

**Transform any ADS-B receiver into an enterprise-grade tactical air intelligence centre.**

Real-time tracking · Proximity alerts · Instant Telegram notifications · Rare airframe radar · Zero-bloat relational database

</div>

---

![SkyAlert Live Airspace Dashboard](docs/screenshots/dashboard_live.jpg)

---

## ✨ What Is SkyAlert?

SkyAlert is a fully **self-hosted**, open-source aviation intelligence platform built for ADS-B fixed station operators. It connects to your existing ADS-B receiver (tar1090, readsb, dump1090-fa, PiAware), builds a relational database of every aircraft that flies over your station, and delivers instant Telegram alerts when something interesting appears — military aircraft, government/VIP transports, emergency squawks, rare heavies, or custom-tracked targets.

Everything runs on your own hardware, on your own network. No subscriptions. No cloud dependencies.

---

## 🌟 Key Features

| Feature | Description |
|---|---|
| ⚡ **Zero-Config Launch** | Single command startup — the entire platform (web dashboard + ADS-B collector) runs from `./start.sh` |
| 🛰️ **Live Airspace & Tactical Radar** | High-refresh live cards with callsign, registration, type, altitude, ground speed, Mach, TAS, vertical rate, CPA & bearing |
| 🗺️ **Leaflet Radar Map** | Interactive range-ring map (50–250 km), real-time aircraft position markers, station coverage display |
| 💬 **Telegram Automation Hub** | Configure and verify your bot from the web UI. Rich photo alert cards with **direct Flightradar24, Plane Finder & ADS-B Exchange deep links** |
| 🚁 **Rare Aircraft Intelligence** | Dedicated radar for helicopters, military transports, A380/B747/C-17 heavies, and one-time visitors — filterable by scenario |
| 📊 **Global Analytics** | 24-hour traffic charts, operator fleet rankings, aircraft type distribution, detection session metrics |
| 🔍 **625,000+ Offline Enrichment** | Bundled airframe CSV database for instant offline lookup of registrations, models, and operators |
| 📉 **Smart Telemetry Sampling** | Preserves 100% of flight visits while throttling raw observations to 30-second trajectory intervals — **95%+ storage reduction** |
| 🔄 **Dual Database Engine** | Zero-config SQLite WAL for standalone use; seamless enterprise PostgreSQL via `DATABASE_URL` |
| 🧰 **Migration CLI** | Standalone tool to migrate legacy `aircraft.db` files into the unified relational schema |
| ⚡ **Auto Background Service** | One-command installer for Linux `systemd` and macOS `launchd` — starts automatically on every reboot |

---

## 📸 Screenshots

### 🛰️ Live Airspace & Radar Map
![Live Airspace with Radar Map](docs/screenshots/dashboard_live.jpg)
*Real-time aircraft cards alongside the Leaflet radar map with 250 km range rings. Every card shows callsign, registration, ICAO type, altitude, speed, distance from station, and bearing.*

---

### ✈️ Aircraft Intelligence Database
![Aircraft Database](docs/screenshots/aircraft_database.jpg)
*Complete paginated database of every aircraft ever detected — 3,200+ records, searchable by ICAO hex, callsign, registration, operator, or type. Click any hex code to open the full intelligence profile.*

---

### 🚁 Rare Aircraft Intelligence
![Rare Aircraft Dashboard](docs/screenshots/rare_aircraft.jpg)
*Smart rarity classification with filterable scenario tabs: Very Rare, Helicopter, Military, 1-Time Visitor, Heavy Jet, and custom Watchlist. Each card shows airline, country, last visit date, and visit count.*

---

### 📊 Global Analytics
![Analytics Dashboard](docs/screenshots/analytics.jpg)
*24-hour traffic chart, lifetime session counters, top operator rankings, aircraft type breakdowns, and enrichment ratios — all computed from your local database.*

---

### 💬 Telegram Aircraft Alerts
![Telegram Alert Notification](docs/screenshots/telegram_alert.jpg)
*Rich HTML alert cards delivered instantly to your Telegram. Each message includes flight details, altitude, speed, distance from station, squawk code, and clickable **Flightradar24 · Plane Finder · ADS-B Exchange** deep links that open directly in the app.*

---

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- An ADS-B receiver running **tar1090**, **readsb**, **dump1090-fa**, or **Ultrafeeder** on your local network
- (Optional) PostgreSQL for enterprise-scale persistence

### 1. Clone the Repository

```bash
git clone https://github.com/navingour/SkyAlert.git
cd SkyAlert
```

### 2. Create Virtual Environment & Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate        # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure Your Receiver

```bash
cp config/config.example.yaml config/config.yaml
nano config/config.yaml          # Or use any text editor
```

Set your receiver URL and station coordinates:

```yaml
tar1090:
  url: "http://YOUR_RECEIVER_IP/tar1090/data/aircraft.json"

station:
  latitude: 22.5726
  longitude: 88.3639
  name: "My Ground Station"
```

> **Tip:** If you skip this step, SkyAlert will auto-bootstrap `config.yaml` from the example template on first launch.

### 4. Launch SkyAlert

```bash
chmod +x start.sh stop.sh
./start.sh
```

Open your browser at **`http://localhost:8080`**

---

## ⚡ Run as a Background Service (Auto-Start on Reboot)

Run the automated service installer — it auto-detects your OS:

```bash
./scripts/install_service.sh
```

| OS | Method | What It Creates |
|---|---|---|
| **Linux / Raspberry Pi / Debian** | `systemd` | `/etc/systemd/system/skyalert.service` |
| **macOS** | `launchd` | `~/Library/LaunchAgents/com.skyalert.app.plist` |

### Service Management

**Linux:**
```bash
sudo systemctl status skyalert        # Check status
sudo journalctl -u skyalert -f        # Live log stream
sudo systemctl restart skyalert       # Restart
sudo systemctl stop skyalert          # Stop
```

**macOS:**
```bash
tail -f logs/skyalert.log             # Live logs
./scripts/uninstall_service.sh        # Remove service
```

---

## ⚙️ Configuration Reference

All settings live in `config/config.yaml`:

```yaml
general:
  poll_interval: 5                    # ADS-B receiver polling rate (seconds)

database:
  # SQLite (default, zero-config):
  url: "sqlite:///data/skyalert_relational.db"
  # PostgreSQL (enterprise):
  # url: "postgresql://user:password@localhost:5432/skyalert"

tar1090:
  url: "http://192.168.0.132/tar1090/data/aircraft.json"

station:
  latitude: 22.5726
  longitude: 88.3639
  name: "Primary Ground Station"

collector:
  session_timeout_minutes: 10         # Inactivity gap before closing a visit
  telemetry:
    enabled: true
    sample_interval_sec: 30           # Trajectory breadcrumb interval

telegram:
  enabled: true
  bot_token: "YOUR_BOT_TOKEN"
  chat_id: "YOUR_CHAT_ID"
  photo_enabled: true                 # Attach aircraft photos to alerts
  silent: false

alerts:
  squawk: true                        # Emergency squawks (7700/7600/7500)
  military: true                      # Military airframes & callsigns
  government: true                    # VIP / government charters
  police: true                        # Law enforcement aircraft
  helicopters: true                   # Rotorcraft (Bell, Eurocopter, AW139...)
  rare_aircraft: true                 # A380, B747, C-17, one-time visitors
  watchlist: true                     # Custom tracked targets

watchlist:
  operators:
    - "Indian Air Force"
    - "NASA"
  flights:
    - "RCH"
    - "IAF"
  registrations: []
  hex: []
```

### Database Options

| Mode | URL Format | Use Case |
|---|---|---|
| **SQLite** (default) | `sqlite:///data/skyalert_relational.db` | Raspberry Pi, single machine |
| **PostgreSQL** | `postgresql://user:pass@host:5432/skyalert` | Multi-node, enterprise, long-term |

---

## 📡 Receiver Compatibility

SkyAlert ingests data from any ADS-B receiver outputting standard `aircraft.json`:

| Receiver Stack | Feed URL |
|---|---|
| **tar1090** | `http://<ip>/tar1090/data/aircraft.json` |
| **readsb** | `http://<ip>/readsb/data/aircraft.json` |
| **dump1090-fa (PiAware)** | `http://<ip>/dump1090-fa/data/aircraft.json` |
| **Ultrafeeder (sdr-enthusiasts)** | `http://<ip>:8080/data/aircraft.json` |
| **Any custom ADS-B stack** | Any accessible `aircraft.json` URL |

---

## 💬 Telegram Alert System

SkyAlert includes a full Telegram automation hub built into the Web UI:

1. **Live Token Verification** — Test your bot token against the Telegram API directly from the Settings panel, no command line needed.
2. **Rich HTML Alert Cards** — Every alert includes: flight, registration, aircraft model, operator, altitude, ground speed, squawk, distance from station, and timestamps in IST.
3. **Aircraft Photo Attachments** — Where available, aircraft photos are fetched and attached directly to the Telegram message.
4. **One-Click Live Tracking Links** — Each alert includes clickable **Flightradar24**, **Plane Finder**, and **ADS-B Exchange** links that open the specific flight directly in the respective app.
5. **Custom Target Tracking** — Monitor specific operators, callsign prefixes, registrations, or ICAO hex codes, with optional proximity radius constraints (e.g., alert only when within 50 km).

### Alert Scenarios

| Trigger | Badge | Description |
|---|---|---|
| Squawk 7700 | 🆘 | General Emergency declared |
| Squawk 7600 | 📡 | Radio Failure |
| Squawk 7500 | 🚨 | Hijack — highest priority |
| Military | 🪖 | IAF, fighters, tactical transports, AWACS |
| Government / VIP | 👑 | Head-of-state flights, government charters |
| Police / Law Enforcement | 🚔 | Police aviation callsigns and patterns |
| Helicopter | 🚁 | Bell, Eurocopter, AW139, Mi-17, HAL |
| Rare Aircraft | ⭐ | A380, An-124, B747, C-17, Beluga, one-time visitors |
| Custom Watchlist | 👁 | User-defined targets with vicinity radius |

---

## 🗄️ Database Migration

If you have legacy database files from earlier tools, migrate with zero data loss:

```bash
# Migrate to SQLite
python3 scripts/migrate_database.py \
  --source "data/legacy_aircraft.db" \
  --target "sqlite:///data/skyalert_relational.db"

# Migrate to PostgreSQL
python3 scripts/migrate_database.py \
  --source "data/legacy_aircraft.db" \
  --target "postgresql://user:pass@localhost:5432/skyalert"
```

---

## 📁 Repository Structure

```
SkyAlert/
├── app/
│   ├── collector/              # Unified async ADS-B poller & session manager
│   ├── aircraft_enricher.py   # Offline-first CSV lookup & metadata enricher
│   ├── analytics_service.py   # Multi-timeframe SQL KPI & chart aggregation
│   ├── db_manager.py          # Universal PostgreSQL / SQLite relational engine
│   ├── notifier.py            # HTML alert card builder with tracker links
│   ├── rules.py               # Alert rule engine & vicinity target evaluator
│   └── telegram.py            # Telegram notification client
├── config/
│   ├── config.example.yaml    # Master configuration blueprint
│   └── config.yaml            # Your configuration (git-ignored)
├── data/
│   └── reference/             # 625,000+ aircraft airframe CSV database
├── docs/
│   └── screenshots/           # README screenshots
├── scripts/
│   ├── install_service.sh     # Auto-detects OS, installs systemd/launchd service
│   ├── uninstall_service.sh   # Removes background service
│   └── migrate_database.py   # Legacy database migration CLI
├── systemd/
│   └── skyalert.service       # Systemd unit file template
├── web/
│   ├── routers/               # FastAPI endpoints (API, dashboard, settings)
│   ├── static/                # CSS, JavaScript, Leaflet maps
│   └── templates/             # Jinja2 HTML dashboard templates
├── main.py                    # Application entry point
├── requirements.txt           # Python dependencies
├── start.sh                   # One-click start script
└── stop.sh                    # Graceful stop script
```

---

## 🔧 Advanced: Environment Variables

You can override the database URL without editing `config.yaml`:

```bash
export DATABASE_URL="postgresql://user:password@localhost:5432/skyalert"
./start.sh
```

Or place it in a `.env` file (auto-loaded on startup):

```bash
# .env
DATABASE_URL=postgresql://user:password@localhost:5432/skyalert
```

---

## 🛠️ Development

```bash
# Start in development mode (with auto-reload)
source .venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8080

# Run tests
python3 test_telegram.py      # Test Telegram connectivity
python3 test_alert_lookup.py  # Test aircraft alert lookup
```

---

## 📋 Requirements

```
fastapi
uvicorn[standard]
psycopg2-binary
pyyaml
requests
httpx
jinja2
python-multipart
```

Install all at once:

```bash
pip install -r requirements.txt
```

---

## 🤝 Contributing

Contributions are welcome! Feel free to open issues or pull requests for:

- Additional alert scenarios or rule engines
- New analytics views or chart types
- Receiver compatibility improvements
- UI/UX enhancements
- Bug fixes and performance improvements

---

## 📄 License

SkyAlert is open-source software released under the [MIT License](LICENSE).

---

<div align="center">

**Built for ADS-B enthusiasts, aviation hobbyists, and fixed-station operators.**

*Star ⭐ the repo if SkyAlert is useful to you!*

</div>
