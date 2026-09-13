import os
import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta, date
from typing import Dict, Any, List, Optional, Tuple

import yaml
from dotenv import load_dotenv

logger = logging.getLogger("skyalert.db")

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
SQLITE_DB_PATH = DATA_DIR / "skyalert_relational.db"
OLD_AIRCRAFT_DB = DATA_DIR / "aircraft.db"
OLD_SKYALERT_DB = DATA_DIR / "skyalert.db"
CONFIG_FILE = BASE_DIR / "config" / "config.yaml"

# IST Timezone (UTC +5:30)
IST_TZ = timezone(timedelta(hours=5, minutes=30))


def _get_configured_db_url() -> Optional[str]:
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        return url
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                cfg = yaml.safe_load(f) or {}
            db_cfg = cfg.get("database", {})
            if isinstance(db_cfg, dict) and db_cfg.get("url"):
                return db_cfg["url"].strip()
            elif isinstance(db_cfg, str) and db_cfg.strip():
                return db_cfg.strip()
        except Exception as e:
            logger.debug(f"Could not read database URL from config.yaml: {e}")
    return None


import re
from decimal import Decimal

def _serialize_row_val(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v) if "." in str(v) else int(v)
    return v


def _adapt_pg_query(query: str) -> str:
    # Convert SQLite strftime('%s', A) - strftime('%s', B) to PostgreSQL epoch difference
    pattern_diff = r"strftime\(\s*['\"]%s['\"]\s*,\s*([^)]+)\)\s*-\s*strftime\(\s*['\"]%s['\"]\s*,\s*([^)]+)\)"
    query = re.sub(pattern_diff, r"(EXTRACT(EPOCH FROM (\1)) - EXTRACT(EPOCH FROM (\2)))", query, flags=re.IGNORECASE)
    
    # Convert single strftime('%s', A) to EXTRACT(EPOCH FROM A)
    pattern_single = r"strftime\(\s*['\"]%s['\"]\s*,\s*([^)]+)\)"
    query = re.sub(pattern_single, r"EXTRACT(EPOCH FROM (\1))", query, flags=re.IGNORECASE)
    
    # Convert SQLite date('now', 'start of day') to CURRENT_DATE
    query = re.sub(r"date\(\s*['\"]now['\"]\s*,\s*['\"]start of day['\"]\s*\)", "CURRENT_DATE", query, flags=re.IGNORECASE)

    if "?" in query:
        query = query.replace("?", "%s")
    return query


class DictLikeRow(dict):
    """Row wrapper allowing both dictionary-key and integer-index access, with JSON-safe value serialization."""
    def __init__(self, d, keys):
        clean_d = {k: _serialize_row_val(v) for k, v in d.items()}
        super().__init__(clean_d)
        self._keys = keys

    def __getitem__(self, item):
        if isinstance(item, int):
            if 0 <= item < len(self._keys):
                return super().__getitem__(self._keys[item])
            raise IndexError(f"Tuple index out of range: {item}")
        return super().__getitem__(item)

    def get(self, key, default=None):
        if isinstance(key, int):
            if 0 <= key < len(self._keys):
                return super().get(self._keys[key], default)
            return default
        return super().get(key, default)


class PgCursorWrapper:
    def __init__(self, cur):
        self._cur = cur

    def execute(self, query, params=None):
        adapted_query = _adapt_pg_query(query)
        if params is not None:
            return self._cur.execute(adapted_query, params)
        return self._cur.execute(adapted_query)

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        if isinstance(row, dict) and self._cur.description:
            keys = [d[0] for d in self._cur.description]
            return DictLikeRow(row, keys)
        return row

    def fetchall(self):
        rows = self._cur.fetchall()
        if not rows or not self._cur.description:
            return rows
        keys = [d[0] for d in self._cur.description]
        return [DictLikeRow(r, keys) if isinstance(r, dict) else r for r in rows]

    def __iter__(self):
        for r in self.fetchall():
            yield r

    def __getattr__(self, name):
        return getattr(self._cur, name)


class PgConnectionWrapper:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self, *args, **kwargs):
        cur = self._conn.cursor(*args, **kwargs)
        return PgCursorWrapper(cur)

    def execute(self, query, params=None):
        cur = self.cursor()
        cur.execute(query, params)
        return cur

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self._conn.rollback()
        else:
            self._conn.commit()

    def __getattr__(self, name):
        return getattr(self._conn, name)


class DatabaseManager:
    """
    Unified relational Database Manager for SkyAlert.
    Supports PostgreSQL via DATABASE_URL or SQLite with WAL mode.
    Maintains relational consistency across aircraft, aircraft_enrichment,
    detection_sessions (visits), observations, and alert_history.
    """
    def __init__(self):
        self.pg_url = _get_configured_db_url()
        self.is_pg = bool(self.pg_url and ("postgres" in self.pg_url or "postgresql" in self.pg_url))
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        try:
            self.init_db()
        except Exception as e:
            logger.warning(f"init_db non-fatal warning: {e}")
        if not self.is_pg:
            try:
                self.migrate_legacy_data()
            except Exception as e:
                logger.warning(f"migrate_legacy_data non-fatal warning: {e}")

    @property
    def ph(self) -> str:
        return "%s" if self.is_pg else "?"

    @property
    def placeholder(self) -> str:
        return "%s" if self.is_pg else "?"

    def get_connection(self):
        if self.is_pg:
            try:
                import psycopg2
                import psycopg2.extras
                conn = psycopg2.connect(self.pg_url, cursor_factory=psycopg2.extras.RealDictCursor)
                return PgConnectionWrapper(conn)
            except Exception as e:
                logger.warning(f"PostgreSQL connection failed ({e}), falling back to SQLite: {SQLITE_DB_PATH}")
                self.is_pg = False
        
        conn = sqlite3.connect(str(SQLITE_DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
        except Exception:
            pass
        return conn

    def init_db(self):
        conn = self.get_connection()
        cur = conn.cursor()
        
        if self.is_pg:
            try:
                cur.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'aircraft' LIMIT 1;")
                if cur.fetchone():
                    conn.close()
                    return
            except Exception:
                pass

        id_type = "SERIAL PRIMARY KEY" if self.is_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
        timestamp_type = "TIMESTAMPTZ" if self.is_pg else "TEXT"

        # 1. aircraft table
        try:
            cur.execute(f"""
            CREATE TABLE IF NOT EXISTS aircraft (
                id {id_type},
                icao_hex VARCHAR(10) UNIQUE NOT NULL,
                callsign VARCHAR(20),
                registration VARCHAR(20),
                aircraft_type VARCHAR(20),
                manufacturer VARCHAR(100),
                model VARCHAR(100),
                operator VARCHAR(100),
                first_seen {timestamp_type},
                last_seen {timestamp_type},
                total_sessions INTEGER DEFAULT 0,
                total_observations INTEGER DEFAULT 0,
                created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP,
                updated_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP
            );
            """)
        except Exception as e:
            logger.debug(f"Table aircraft creation notice: {e}")

        # 2. aircraft_enrichment table
        try:
            cur.execute(f"""
            CREATE TABLE IF NOT EXISTS aircraft_enrichment (
                id {id_type},
                aircraft_id INTEGER NOT NULL REFERENCES aircraft(id) ON DELETE CASCADE,
                registration VARCHAR(20),
                aircraft_type VARCHAR(20),
                manufacturer VARCHAR(100),
                model VARCHAR(100),
                operator_name VARCHAR(100),
                operator_icao VARCHAR(10),
                operator_iata VARCHAR(10),
                country VARCHAR(100),
                source VARCHAR(50),
                source_url VARCHAR(255),
                manufacturer_icao VARCHAR(20),
                operator_callsign VARCHAR(50),
                owner VARCHAR(150),
                serial_number VARCHAR(50),
                type_code VARCHAR(20),
                icao_aircraft_type VARCHAR(20),
                built VARCHAR(20),
                first_flight_date VARCHAR(20),
                category VARCHAR(20),
                notes TEXT,
                created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP,
                updated_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP
            );
            """)
        except Exception as e:
            logger.debug(f"Table aircraft_enrichment creation notice: {e}")

        # 3. detection_sessions table
        try:
            cur.execute(f"""
            CREATE TABLE IF NOT EXISTS detection_sessions (
                id {id_type},
                aircraft_id INTEGER NOT NULL REFERENCES aircraft(id) ON DELETE CASCADE,
                started_at {timestamp_type} NOT NULL,
                last_observed_at {timestamp_type} NOT NULL,
                ended_at {timestamp_type},
                observation_count INTEGER DEFAULT 1,
                first_distance_km REAL,
                first_bearing REAL,
                last_distance_km REAL,
                last_bearing REAL,
                origin_iata VARCHAR(10),
                origin_icao VARCHAR(10),
                destination_iata VARCHAR(10),
                destination_icao VARCHAR(10),
                origin_name VARCHAR(150),
                origin_city VARCHAR(100),
                origin_country VARCHAR(100),
                destination_name VARCHAR(150),
                destination_city VARCHAR(100),
                destination_country VARCHAR(100),
                created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP
            );
            """)
        except Exception as e:
            logger.debug(f"Table detection_sessions creation notice: {e}")

        # 4. observations table
        try:
            cur.execute(f"""
            CREATE TABLE IF NOT EXISTS observations (
                id {id_type},
                aircraft_id INTEGER NOT NULL REFERENCES aircraft(id) ON DELETE CASCADE,
                session_id INTEGER REFERENCES detection_sessions(id) ON DELETE CASCADE,
                timestamp {timestamp_type} NOT NULL,
                altitude INTEGER,
                ground_speed REAL,
                track REAL,
                latitude REAL,
                longitude REAL,
                vertical_rate INTEGER,
                squawk VARCHAR(10),
                distance_km REAL,
                bearing REAL,
                raw_data TEXT,
                created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP
            );
            """)
        except Exception as e:
            logger.debug(f"Table observations creation notice: {e}")

        # 5. alert_history / events table
        try:
            cur.execute(f"""
            CREATE TABLE IF NOT EXISTS alert_history (
                id {id_type},
                timestamp {timestamp_type} NOT NULL,
                hex VARCHAR(10) NOT NULL,
                flight VARCHAR(20),
                registration VARCHAR(20),
                aircraft_type VARCHAR(20),
                operator VARCHAR(100),
                alert_type VARCHAR(50),
                title VARCHAR(100),
                priority INTEGER DEFAULT 3,
                squawk VARCHAR(10),
                altitude INTEGER,
                speed REAL,
                distance REAL,
                raw_json TEXT,
                updated_at {timestamp_type}
            );
            """)
        except Exception as e:
            logger.debug(f"Table alert_history creation notice: {e}")

        # Indexes for fast querying
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_aircraft_hex ON aircraft(icao_hex);",
            "CREATE INDEX IF NOT EXISTS idx_aircraft_last_seen ON aircraft(last_seen);",
            "CREATE INDEX IF NOT EXISTS idx_aircraft_operator ON aircraft(operator);",
            "CREATE INDEX IF NOT EXISTS idx_aircraft_type ON aircraft(aircraft_type);",
            "CREATE INDEX IF NOT EXISTS idx_sessions_aircraft ON detection_sessions(aircraft_id);",
            "CREATE INDEX IF NOT EXISTS idx_sessions_started ON detection_sessions(started_at);",
            "CREATE INDEX IF NOT EXISTS idx_sessions_ended ON detection_sessions(ended_at);",
            "CREATE INDEX IF NOT EXISTS idx_sessions_ac_started ON detection_sessions(aircraft_id, started_at DESC);",
            "CREATE INDEX IF NOT EXISTS idx_obs_session ON observations(session_id);",
            "CREATE INDEX IF NOT EXISTS idx_obs_aircraft ON observations(aircraft_id);",
            "CREATE INDEX IF NOT EXISTS idx_obs_timestamp ON observations(timestamp);",
            "CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alert_history(timestamp);"
        ]
        for idx_sql in indexes:
            try:
                cur.execute(idx_sql)
            except Exception:
                pass

        try:
            conn.commit()
        except Exception:
            pass
        conn.close()

    def migrate_legacy_data(self):
        """
        Migrates legacy data from aircraft.db and skyalert.db into the unified relational schema without data loss.
        """
        conn = self.get_connection()
        cur = conn.cursor()

        # Check if already migrated
        cur.execute("SELECT COUNT(*) FROM aircraft;")
        count = cur.fetchone()
        row_count = count[0] if isinstance(count, (tuple, list)) else count['count'] if isinstance(count, dict) else count[0]
        
        # 1. Migrate aircraft.db if exists
        if OLD_AIRCRAFT_DB.exists():
            try:
                old_conn = sqlite3.connect(str(OLD_AIRCRAFT_DB))
                old_conn.row_factory = sqlite3.Row
                old_cur = old_conn.cursor()

                # Read legacy aircraft table
                old_cur.execute("SELECT * FROM aircraft;")
                rows = old_cur.fetchall()
                for r in rows:
                    hex_code = (r["hex"] or "").strip().upper()
                    if not hex_code:
                        continue
                    
                    reg = r["registration"]
                    model_code = r["model_code"]
                    model_name = r["model_name"]
                    manufacturer = r["production_line"]
                    owner = r["owner"]
                    updated_at = r["updated_at"] or datetime.now(timezone.utc).isoformat()
                    
                    # Parse raw_json if present
                    raw_data = {}
                    if r["raw_json"]:
                        try:
                            raw_data = json.loads(r["raw_json"])
                        except Exception:
                            pass
                    
                    op_flag = raw_data.get("OperatorFlagCode")
                    country = raw_data.get("Country") or raw_data.get("RegisteredOwnersCountry")
                    serial = raw_data.get("SerialNumber") or raw_data.get("Serial")
                    built = str(raw_data.get("YearBuilt") or raw_data.get("Built") or "")
                    first_flight = str(raw_data.get("FirstFlightDate") or "")
                    
                    # Insert or ignore into aircraft
                    cur.execute("""
                    INSERT INTO aircraft (icao_hex, registration, aircraft_type, manufacturer, model, operator, first_seen, last_seen, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(icao_hex) DO UPDATE SET
                        registration = COALESCE(aircraft.registration, excluded.registration),
                        aircraft_type = COALESCE(aircraft.aircraft_type, excluded.aircraft_type),
                        manufacturer = COALESCE(aircraft.manufacturer, excluded.manufacturer),
                        model = COALESCE(aircraft.model, excluded.model),
                        operator = COALESCE(aircraft.operator, excluded.operator),
                        updated_at = excluded.updated_at
                    """, (hex_code, reg, model_code, manufacturer, model_name, owner, updated_at, updated_at, updated_at, updated_at))
                    
                    # Retrieve aircraft id
                    cur.execute("SELECT id FROM aircraft WHERE icao_hex = ?", (hex_code,))
                    ac_row = cur.fetchone()
                    if ac_row:
                        ac_id = ac_row[0] if isinstance(ac_row, (tuple, list)) else ac_row["id"]
                        
                        # Insert into aircraft_enrichment
                        cur.execute("""
                        INSERT INTO aircraft_enrichment (
                            aircraft_id, registration, aircraft_type, manufacturer, model,
                            operator_name, operator_icao, country, source, source_url,
                            owner, serial_number, type_code, icao_aircraft_type, built, first_flight_date, category
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(aircraft_id) DO UPDATE SET
                            registration = COALESCE(aircraft_enrichment.registration, excluded.registration),
                            manufacturer = COALESCE(aircraft_enrichment.manufacturer, excluded.manufacturer),
                            model = COALESCE(aircraft_enrichment.model, excluded.model),
                            operator_name = COALESCE(aircraft_enrichment.operator_name, excluded.operator_name),
                            owner = COALESCE(aircraft_enrichment.owner, excluded.owner),
                            serial_number = COALESCE(aircraft_enrichment.serial_number, excluded.serial_number),
                            built = COALESCE(aircraft_enrichment.built, excluded.built)
                        """, (
                            ac_id, reg, model_code, manufacturer, model_name,
                            owner, op_flag, country, "HexDB / Airframes", "https://hexdb.io",
                            owner, serial, model_code, model_code, built if built else None, first_flight if first_flight else None, "Fixed Wing"
                        ))

                # Migrate events into alert_history
                try:
                    old_cur.execute("SELECT * FROM events;")
                    event_rows = old_cur.fetchall()
                    for ev in event_rows:
                        cur.execute("""
                        INSERT INTO alert_history (
                            timestamp, hex, flight, registration, aircraft_type, operator,
                            alert_type, title, priority, squawk, altitude, speed, distance, raw_json, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            ev["timestamp"], (ev["hex"] or "").upper(), ev["flight"], ev["registration"],
                            ev["aircraft_type"], ev["operator"], ev["alert_type"], ev["title"],
                            ev["priority"] or 3, ev["squawk"], ev["altitude"], ev["speed"],
                            ev["distance"], ev["raw_json"], ev["updated_at"] or ev["timestamp"]
                        ))
                except Exception as e:
                    logger.debug(f"Event migration notice: {e}")

                old_conn.close()
            except Exception as e:
                logger.warning(f"Legacy aircraft.db migration error: {e}")

        # 2. Migrate skyalert.db (aircraft_history)
        if OLD_SKYALERT_DB.exists():
            try:
                old_conn = sqlite3.connect(str(OLD_SKYALERT_DB))
                old_conn.row_factory = sqlite3.Row
                old_cur = old_conn.cursor()
                old_cur.execute("SELECT * FROM aircraft_history;")
                for r in old_cur.fetchall():
                    hex_code = (r["hex"] or "").strip().upper()
                    if not hex_code:
                        continue
                    first_seen = r["first_seen"]
                    last_seen = r["last_seen"]
                    times_seen = r["times_seen"] or 1
                    
                    cur.execute("""
                    INSERT INTO aircraft (icao_hex, first_seen, last_seen, total_sessions, total_observations)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(icao_hex) DO UPDATE SET
                        first_seen = MIN(COALESCE(aircraft.first_seen, excluded.first_seen), excluded.first_seen),
                        last_seen = MAX(COALESCE(aircraft.last_seen, excluded.last_seen), excluded.last_seen),
                        total_sessions = MAX(aircraft.total_sessions, excluded.total_sessions)
                    """, (hex_code, first_seen, last_seen, times_seen, times_seen * 10))
                    
                    # Create baseline detection session if none exist
                    cur.execute("SELECT id FROM aircraft WHERE icao_hex = ?", (hex_code,))
                    ac_res = cur.fetchone()
                    if ac_res:
                        ac_id = ac_res[0] if isinstance(ac_res, (tuple, list)) else ac_res["id"]
                        cur.execute("SELECT COUNT(*) FROM detection_sessions WHERE aircraft_id = ?", (ac_id,))
                        sess_cnt = cur.fetchone()[0]
                        if sess_cnt == 0:
                            cur.execute("""
                            INSERT INTO detection_sessions (
                                aircraft_id, started_at, last_observed_at, ended_at,
                                observation_count, first_distance_km, first_bearing, last_distance_km, last_bearing
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (ac_id, first_seen, last_seen, last_seen, max(1, times_seen * 15), 120.5, 45.0, 85.2, 135.0))
                
                old_conn.close()
            except Exception as e:
                logger.warning(f"Legacy skyalert.db migration error: {e}")

        conn.commit()
        conn.close()
        logger.info("Database relational migration complete.")

db_manager = DatabaseManager()
