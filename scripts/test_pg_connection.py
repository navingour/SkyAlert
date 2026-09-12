#!/usr/bin/env python3
"""Diagnostic script to test SkyAlert PostgreSQL connection and inspect tables."""
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.db_manager import db_manager, _get_configured_db_url

def test_connection():
    url = _get_configured_db_url()
    print("=" * 60)
    print("SkyAlert Database Diagnostics")
    print("=" * 60)
    print(f"Configured Database URL: {url}")
    print(f"Is PostgreSQL Mode: {db_manager.is_pg}")
    print("-" * 60)

    try:
        conn = db_manager.get_connection()
        cur = conn.cursor()
        print(" Connected to database successfully!")
        
        tables = ["aircraft", "aircraft_enrichment", "detection_sessions", "observations", "alert_history"]
        print("\nTable Statistics:")
        for t in tables:
            try:
                if db_manager.is_pg:
                    cur.execute("SELECT reltuples::bigint FROM pg_class WHERE relname = %s;", (t,))
                    res = cur.fetchone()
                    count = res["reltuples"] if isinstance(res, dict) and "reltuples" in res else res[0] if res else 0
                    print(f"  • {t.ljust(22)}: ~{count:,} rows")
                else:
                    cur.execute(f"SELECT COUNT(*) FROM {t};")
                    res = cur.fetchone()
                    count = res[0] if isinstance(res, (tuple, list)) else res.get("count", list(res.values())[0]) if isinstance(res, dict) else res[0]
                    print(f"  • {t.ljust(22)}: {count:,} rows")
            except Exception as e:
                print(f"  • {t.ljust(22)}: Error reading table ({e})")

        conn.close()
        print("\nAll database checks completed.")
    except Exception as e:
        print(f"\n Connection Error: {e}")
        print("\nPlease ensure:")
        print("  1. The Debian server's PostgreSQL service is running.")
        print("  2. /etc/postgresql/17/main/pg_hba.conf allows remote connection from this machine.")
        print("  3. Your username and password in .env or config/config.yaml are correct.")

if __name__ == "__main__":
    test_connection()
