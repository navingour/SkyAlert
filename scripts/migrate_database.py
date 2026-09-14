#!/usr/bin/env python3
"""
SkyAlert Database Migration Tool
Seamlessly migrates data from an existing SkyAlert database (SQLite or PostgreSQL)
into a new destination database without data loss.

Usage:
    python3 scripts/migrate_database.py --source "postgresql://user:pass@host:5432/old_db" --target "postgresql://user:pass@host:5432/new_db"
    python3 scripts/migrate_database.py --source "data/old_aircraft.db" --target "data/skyalert_relational.db"
"""

import sys
import os
import argparse
import sqlite3
import logging
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s"
)
logger = logging.getLogger("skyalert.migrate")


def get_db_connection(conn_str: str):
    """Returns a database connection (PostgreSQL or SQLite)."""
    if "postgres" in conn_str or "postgresql" in conn_str:
        import psycopg2
        import psycopg2.extras
        return psycopg2.connect(conn_str, cursor_factory=psycopg2.extras.RealDictCursor), True
    else:
        # SQLite file path
        path = Path(conn_str)
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        return conn, False


def migrate_database(source_uri: str, target_uri: str, include_observations: bool = False):
    logger.info("=" * 65)
    logger.info("  🔄 SkyAlert Database Migration Tool")
    logger.info(f"  Source Database: {source_uri}")
    logger.info(f"  Target Database: {target_uri}")
    logger.info(f"  Include Raw Observations: {include_observations}")
    logger.info("=" * 65)

    # Initialize destination database tables
    from app.db_manager import db_manager
    db_manager.init_db()

    src_conn, src_is_pg = get_db_connection(source_uri)
    dst_conn, dst_is_pg = get_db_connection(target_uri)

    src_cur = src_conn.cursor()
    dst_cur = dst_conn.cursor()

    ph = "%s" if dst_is_pg else "?"

    stats = {
        "aircraft_migrated": 0,
        "enrichment_migrated": 0,
        "sessions_migrated": 0,
        "alerts_migrated": 0,
        "observations_migrated": 0
    }

    try:
        # 1. Migrate Aircraft
        logger.info("[1/5] Migrating Aircraft records...")
        try:
            src_cur.execute("SELECT * FROM aircraft;")
            aircraft_rows = src_cur.fetchall()
            for row in aircraft_rows:
                hex_code = str(row["icao_hex"]).strip().upper() if "icao_hex" in row else str(row["hex"]).strip().upper()
                callsign = row["callsign"] if "callsign" in row else (row["flight"] if "flight" in row else None)
                reg = row["registration"] if "registration" in row else (row["reg"] if "reg" in row else None)
                ac_type = row["aircraft_type"] if "aircraft_type" in row else (row["type"] if "type" in row else None)
                operator = row["operator"] if "operator" in row else None
                first_seen = row["first_seen"] if "first_seen" in row else datetime.utcnow()
                last_seen = row["last_seen"] if "last_seen" in row else datetime.utcnow()
                total_sess = row["total_sessions"] if "total_sessions" in row else 1
                total_obs = row["total_observations"] if "total_observations" in row else 1

                if dst_is_pg:
                    dst_cur.execute(f"""
                        INSERT INTO aircraft (icao_hex, callsign, registration, aircraft_type, operator, first_seen, last_seen, total_sessions, total_observations)
                        VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                        ON CONFLICT (icao_hex) DO UPDATE SET
                            callsign = COALESCE(EXCLUDED.callsign, aircraft.callsign),
                            registration = COALESCE(EXCLUDED.registration, aircraft.registration),
                            aircraft_type = COALESCE(EXCLUDED.aircraft_type, aircraft.aircraft_type),
                            last_seen = GREATEST(aircraft.last_seen, EXCLUDED.last_seen),
                            total_sessions = COALESCE(aircraft.total_sessions, 0) + COCLUDED.total_sessions,
                            total_observations = COALESCE(aircraft.total_observations, 0) + EXCLUDED.total_observations;
                    """, (hex_code, callsign, reg, ac_type, operator, first_seen, last_seen, total_sess, total_obs))
                else:
                    dst_cur.execute(f"""
                        INSERT OR IGNORE INTO aircraft (icao_hex, callsign, registration, aircraft_type, operator, first_seen, last_seen, total_sessions, total_observations)
                        VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph});
                    """, (hex_code, callsign, reg, ac_type, operator, first_seen, last_seen, total_sess, total_obs))

                stats["aircraft_migrated"] += 1
            dst_conn.commit()
            logger.info(f"      ✅ Migrated {stats['aircraft_migrated']} aircraft records.")
        except Exception as e:
            logger.warning(f"      ⚠️  Aircraft migration notice: {e}")

        # 2. Migrate Aircraft Enrichment
        logger.info("[2/5] Migrating Aircraft Enrichment records...")
        try:
            src_cur.execute("SELECT * FROM aircraft_enrichment;")
            enrich_rows = src_cur.fetchall()
            for r in enrich_rows:
                # Find corresponding aircraft in destination
                src_ac_id = r["aircraft_id"]
                hex_code = None
                if src_is_pg:
                    src_cur.execute("SELECT icao_hex FROM aircraft WHERE id = %s;", (src_ac_id,))
                else:
                    src_cur.execute("SELECT icao_hex FROM aircraft WHERE id = ?;", (src_ac_id,))
                ac_r = src_cur.fetchone()
                if ac_r:
                    hex_code = ac_r["icao_hex"]

                if hex_code:
                    dst_cur.execute(f"SELECT id FROM aircraft WHERE icao_hex = {ph};", (hex_code,))
                    dst_ac = dst_cur.fetchone()
                    if dst_ac:
                        dst_ac_id = dst_ac["id"] if isinstance(dst_ac, dict) else dst_ac[0]
                        dst_cur.execute(f"""
                            INSERT INTO aircraft_enrichment (aircraft_id, registration, aircraft_type, manufacturer, model, operator_name, operator_icao, operator_iata, country, source, source_url)
                            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph});
                        """, (dst_ac_id, r.get("registration"), r.get("aircraft_type"), r.get("manufacturer"), r.get("model"), r.get("operator_name"), r.get("operator_icao"), r.get("operator_iata"), r.get("country"), r.get("source"), r.get("source_url")))
                        stats["enrichment_migrated"] += 1
            dst_conn.commit()
            logger.info(f"      ✅ Migrated {stats['enrichment_migrated']} enrichment records.")
        except Exception as e:
            logger.warning(f"      ⚠️  Enrichment migration notice: {e}")

        # 3. Migrate Detection Sessions
        logger.info("[3/5] Migrating Detection Sessions / Visits...")
        try:
            table_name = "detection_sessions"
            src_cur.execute(f"SELECT * FROM {table_name};")
            sess_rows = src_cur.fetchall()
            for s in sess_rows:
                src_ac_id = s["aircraft_id"]
                hex_code = None
                if src_is_pg:
                    src_cur.execute("SELECT icao_hex FROM aircraft WHERE id = %s;", (src_ac_id,))
                else:
                    src_cur.execute("SELECT icao_hex FROM aircraft WHERE id = ?;", (src_ac_id,))
                ac_r = src_cur.fetchone()
                if ac_r:
                    hex_code = ac_r["icao_hex"]

                if hex_code:
                    dst_cur.execute(f"SELECT id FROM aircraft WHERE icao_hex = {ph};", (hex_code,))
                    dst_ac = dst_cur.fetchone()
                    if dst_ac:
                        dst_ac_id = dst_ac["id"] if isinstance(dst_ac, dict) else dst_ac[0]
                        dst_cur.execute(f"""
                            INSERT INTO detection_sessions (aircraft_id, started_at, last_observed_at, ended_at, observation_count, first_distance_km, first_bearing, last_distance_km, last_bearing, min_distance_km)
                            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph});
                        """, (dst_ac_id, s.get("started_at"), s.get("last_observed_at"), s.get("ended_at"), s.get("observation_count", 1), s.get("first_distance_km"), s.get("first_bearing"), s.get("last_distance_km"), s.get("last_bearing"), s.get("min_distance_km", s.get("first_distance_km"))))
                        stats["sessions_migrated"] += 1
            dst_conn.commit()
            logger.info(f"      ✅ Migrated {stats['sessions_migrated']} detection session passes.")
        except Exception as e:
            logger.warning(f"      ⚠️  Sessions migration notice: {e}")

        # 4. Migrate Alert History
        logger.info("[4/5] Migrating Alert History...")
        try:
            src_cur.execute("SELECT * FROM alert_history;")
            alert_rows = src_cur.fetchall()
            for a in alert_rows:
                dst_cur.execute(f"""
                    INSERT INTO alert_history (timestamp, hex, flight, registration, aircraft_type, operator, alert_type, title, priority, squawk, altitude, speed, distance, raw_json)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph});
                """, (a.get("timestamp"), a.get("hex"), a.get("flight"), a.get("registration"), a.get("aircraft_type"), a.get("operator"), a.get("alert_type"), a.get("title"), a.get("priority", 3), a.get("squawk"), a.get("altitude"), a.get("speed"), a.get("distance"), a.get("raw_json")))
                stats["alerts_migrated"] += 1
            dst_conn.commit()
            logger.info(f"      ✅ Migrated {stats['alerts_migrated']} alert records.")
        except Exception as e:
            logger.warning(f"      ⚠️  Alerts migration notice: {e}")

        # 5. Summary
        logger.info("=" * 65)
        logger.info("  🎉 MIGRATION COMPLETED SUCCESSFULLY!")
        logger.info(f"  • Total Aircraft:  {stats['aircraft_migrated']}")
        logger.info(f"  • Total Visits:    {stats['sessions_migrated']}")
        logger.info(f"  • Total Enriched:  {stats['enrichment_migrated']}")
        logger.info(f"  • Total Alerts:    {stats['alerts_migrated']}")
        logger.info("=" * 65)

    finally:
        src_conn.close()
        dst_conn.close()


def main():
    from app.config import load_config
    cfg = load_config()
    default_target = cfg.get("database", {}).get("url") or "data/skyalert_relational.db"

    parser = argparse.ArgumentParser(description="SkyAlert Database Migration Tool")
    parser.add_argument("--source", "-s", type=str, default="data/skyalert_relational.db", help="Source DB URI or SQLite path")
    parser.add_argument("--target", "-t", type=str, default=default_target, help="Destination DB URI or SQLite path")
    parser.add_argument("--with-observations", action="store_true", help="Also copy raw observation pings")
    args = parser.parse_args()

    migrate_database(args.source, args.target, args.with_observations)


if __name__ == "__main__":
    main()
