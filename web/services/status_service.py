import subprocess
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import requests

from app.db_manager import db_manager
from app.analytics_service import format_ist_datetime

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class StatusService:
    def engine_status(self):
        try:
            if Path("/usr/bin/systemctl").exists() or Path("/bin/systemctl").exists():
                result = subprocess.run(
                    ["systemctl", "is-active", "skyalert.service"],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if result.stdout.strip() == "active":
                    return True
            r = subprocess.run(["pgrep", "-f", "app.backend.main"], capture_output=True, text=True)
            return bool(r.stdout.strip())
        except Exception:
            return True

    def receiver_status(self, url):
        try:
            r = requests.get(url, timeout=2)
            return r.status_code == 200
        except Exception:
            return False

    def aircraft_seen(self):
        try:
            conn = db_manager.get_connection()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM alert_history;")
            res = cur.fetchone()
            count = res[0] if isinstance(res, (tuple, list)) else res["count"]
            conn.close()
            return count
        except Exception:
            return 0

    def aircraft_database_size(self):
        try:
            conn = db_manager.get_connection()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM aircraft;")
            res = cur.fetchone()
            count = res[0] if isinstance(res, (tuple, list)) else res["count"]
            conn.close()
            return count
        except Exception:
            return 0

    def recent_alerts(self, limit=10):
        try:
            conn = db_manager.get_connection()
            cur = conn.cursor()
            cur.execute("""
            SELECT id, timestamp, updated_at, title, flight, registration,
                   aircraft_type, operator, hex
            FROM alert_history
            ORDER BY id DESC
            LIMIT ?
            """, (limit,))
            rows = cur.fetchall()
            alerts = []
            for r in rows:
                alerts.append({
                    "id": r["id"],
                    "timestamp": format_ist_datetime(r["updated_at"] or r["timestamp"]),
                    "title": r["title"] or "ALERT",
                    "flight": r["flight"] or "",
                    "registration": r["registration"] or r["hex"],
                    "aircraft_type": r["aircraft_type"] or "Unknown",
                    "operator": r["operator"] or "Unknown",
                    "hex": r["hex"]
                })
            conn.close()
            return alerts
        except Exception:
            return []

    def format_timestamp(self, timestamp):
        return format_ist_datetime(timestamp)

status_service = StatusService()
