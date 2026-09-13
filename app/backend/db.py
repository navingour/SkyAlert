import os
import sqlite3
import logging
import yaml
from pathlib import Path
from datetime import datetime, timezone, date
from typing import Dict, Any, Optional
from dotenv import load_dotenv

logger = logging.getLogger("skyalert.backend.db")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

DB_FILE = BASE_DIR / "data" / "skyalert_relational.db"
CONFIG_FILE = BASE_DIR / "config" / "config.yaml"


def _get_configured_db_url() -> Optional[str]:
    # 1. Environment variable
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        return url
    # 2. config.yaml
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


def _parse_date(val: Any) -> Optional[date]:
    if not val:
        return None
    if isinstance(val, date):
        return val
    try:
        s = str(val).strip()[:10]
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


class DatabaseManager:
    def __init__(self, db_path: str = str(DB_FILE)):
        self.db_path = db_path
        self.pg_url = _get_configured_db_url()
        self.is_pg = bool(self.pg_url and ("postgres" in self.pg_url or "postgresql" in self.pg_url))
        self._ensure_db_dir()
        if self.is_pg:
            logger.info("DatabaseManager initialized with PostgreSQL backend")
        else:
            logger.info("DatabaseManager initialized with SQLite backend: %s", self.db_path)

    @property
    def ph(self) -> str:
        return "%s" if self.is_pg else "?"

    def _ensure_db_dir(self):
        if not self.is_pg:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self):
        if self.is_pg:
            try:
                import psycopg2
                import psycopg2.extras
                conn = psycopg2.connect(self.pg_url, cursor_factory=psycopg2.extras.RealDictCursor)
                return conn
            except Exception as e:
                logger.warning(f"PostgreSQL connection failed ({e}), falling back to SQLite: {self.db_path}")
                self.is_pg = False
        
        conn = sqlite3.connect(self.db_path, timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
        except Exception:
            pass
        return conn

    def upsert_aircraft(self, hex_code: str, callsign: str = None, reg: str = None, ac_type: str = None) -> int:
        now_dt = datetime.now(timezone.utc)
        now_val = now_dt if self.is_pg else now_dt.isoformat()
        ph = self.ph
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            if self.is_pg:
                cur.execute(f"""
                    INSERT INTO aircraft (icao_hex, callsign, registration, aircraft_type, first_seen, last_seen, total_sessions, total_observations, created_at, updated_at)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, 1, 1, {ph}, {ph})
                    ON CONFLICT (icao_hex) DO UPDATE SET
                        callsign = COALESCE(NULLIF(EXCLUDED.callsign, ''), aircraft.callsign),
                        registration = COALESCE(NULLIF(EXCLUDED.registration, ''), aircraft.registration),
                        aircraft_type = COALESCE(NULLIF(EXCLUDED.aircraft_type, ''), aircraft.aircraft_type),
                        last_seen = EXCLUDED.last_seen,
                        total_observations = aircraft.total_observations + 1,
                        updated_at = EXCLUDED.updated_at
                    RETURNING id;
                """, (hex_code, callsign, reg, ac_type, now_val, now_val, now_val, now_val))
                row = cur.fetchone()
                ac_id = row["id"] if isinstance(row, dict) else row[0]
            else:
                cur.execute("SELECT id FROM aircraft WHERE icao_hex = ?", (hex_code,))
                row = cur.fetchone()
                if row:
                    ac_id = row["id"]
                    cur.execute("""
                        UPDATE aircraft SET
                            callsign = COALESCE(NULLIF(?, ''), callsign),
                            registration = COALESCE(NULLIF(?, ''), registration),
                            aircraft_type = COALESCE(NULLIF(?, ''), aircraft_type),
                            last_seen = ?,
                            total_observations = total_observations + 1,
                            updated_at = ?
                        WHERE id = ?
                    """, (callsign, reg, ac_type, now_val, now_val, ac_id))
                else:
                    cur.execute("""
                        INSERT INTO aircraft (icao_hex, callsign, registration, aircraft_type, first_seen, last_seen, total_sessions, total_observations, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, 1, 1, ?, ?)
                    """, (hex_code, callsign, reg, ac_type, now_val, now_val, now_val, now_val))
                    ac_id = cur.lastrowid
            conn.commit()
            return ac_id
        finally:
            conn.close()

    def get_active_session(self, ac_id: int) -> Optional[int]:
        ph = self.ph
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(f"""
                SELECT id FROM detection_sessions 
                WHERE aircraft_id = {ph} AND ended_at IS NULL 
                ORDER BY id DESC LIMIT 1
            """, (ac_id,))
            row = cur.fetchone()
            if not row:
                return None
            return row["id"] if isinstance(row, dict) else row[0]
        finally:
            conn.close()

    def start_session(self, ac_id: int, dist_km: float, bearing: float) -> int:
        now_dt = datetime.now(timezone.utc)
        now_val = now_dt if self.is_pg else now_dt.isoformat()
        ph = self.ph
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            if self.is_pg:
                cur.execute(f"""
                    INSERT INTO detection_sessions (
                        aircraft_id, started_at, last_observed_at, ended_at,
                        observation_count, first_distance_km, first_bearing, last_distance_km, last_bearing
                    ) VALUES ({ph}, {ph}, {ph}, NULL, 1, {ph}, {ph}, {ph}, {ph})
                    RETURNING id;
                """, (ac_id, now_val, now_val, dist_km, bearing, dist_km, bearing))
                row = cur.fetchone()
                session_id = row["id"] if isinstance(row, dict) else row[0]
            else:
                cur.execute("""
                    INSERT INTO detection_sessions (
                        aircraft_id, started_at, last_observed_at, ended_at,
                        observation_count, first_distance_km, first_bearing, last_distance_km, last_bearing
                    ) VALUES (?, ?, ?, NULL, 1, ?, ?, ?, ?)
                """, (ac_id, now_val, now_val, dist_km, bearing, dist_km, bearing))
                session_id = cur.lastrowid
            
            # Increment total_sessions in aircraft
            cur.execute(f"UPDATE aircraft SET total_sessions = total_sessions + 1 WHERE id = {ph}", (ac_id,))
            conn.commit()
            return session_id
        finally:
            conn.close()

    def update_session(self, session_id: int, dist_km: float, bearing: float):
        now_dt = datetime.now(timezone.utc)
        now_val = now_dt if self.is_pg else now_dt.isoformat()
        ph = self.ph
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(f"""
                UPDATE detection_sessions SET
                    last_observed_at = {ph},
                    observation_count = observation_count + 1,
                    last_distance_km = COALESCE({ph}, last_distance_km),
                    last_bearing = COALESCE({ph}, last_bearing)
                WHERE id = {ph}
            """, (now_val, dist_km, bearing, session_id))
            conn.commit()
        finally:
            conn.close()

    def close_session(self, session_id: int):
        ph = self.ph
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(f"""
                UPDATE detection_sessions 
                SET ended_at = last_observed_at 
                WHERE id = {ph}
            """, (session_id,))
            conn.commit()
        finally:
            conn.close()

    def insert_observation(self, ac_id: int, session_id: int, plane: Dict[str, Any], dist_km: float, bearing: float):
        now_dt = datetime.now(timezone.utc)
        now_val = now_dt if self.is_pg else now_dt.isoformat()
        ph = self.ph
        conn = self.get_connection()

        def _safe_int(v):
            if v is None or v == "ground" or v == "None": return None
            try: return int(v)
            except Exception: return None

        def _safe_float(v):
            if v is None or v == "ground" or v == "None": return None
            try: return float(v)
            except Exception: return None

        alt_b = _safe_int(plane.get("alt_baro"))
        alt_g = _safe_int(plane.get("alt_geom"))
        gs = _safe_float(plane.get("gs"))
        track = _safe_float(plane.get("track"))
        lat = _safe_float(plane.get("lat"))
        lon = _safe_float(plane.get("lon"))
        baro_rate = _safe_int(plane.get("baro_rate") or plane.get("geom_rate"))
        oat = _safe_float(plane.get("oat"))
        tat = _safe_float(plane.get("tat"))
        ws = _safe_float(plane.get("ws"))
        wd = _safe_float(plane.get("wd"))

        try:
            cur = conn.cursor()
            if self.is_pg:
                # PostgreSQL schema on Debian uses 'observed_at' and 'barometric_rate'
                cur.execute(f"""
                    INSERT INTO observations (
                        aircraft_id, session_id, observed_at, altitude_baro, altitude_geom,
                        ground_speed, track, latitude, longitude, barometric_rate, squawk,
                        distance_km, bearing, oat, tat, wind_speed, wind_direction, created_at
                    ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                """, (
                    ac_id, session_id, now_val,
                    alt_b, alt_g,
                    gs, track,
                    lat, lon,
                    baro_rate,
                    str(plane.get("squawk") or ""),
                    dist_km, bearing,
                    oat, tat, ws, wd,
                    now_val
                ))
            else:
                cur.execute("""
                    INSERT INTO observations (
                        aircraft_id, session_id, timestamp, altitude_baro, altitude_geom,
                        ground_speed, track, latitude, longitude, vertical_rate, squawk,
                        distance_km, bearing, oat, tat, wind_speed, wind_direction, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ac_id, session_id, now_val,
                    alt_b, alt_g,
                    gs, track,
                    lat, lon,
                    baro_rate,
                    str(plane.get("squawk") or ""),
                    dist_km, bearing,
                    oat, tat, ws, wd,
                    now_val
                ))
            conn.commit()
        finally:
            conn.close()

    def update_session_route(self, session_id: int, route_data: Dict[str, Any]):
        ph = self.ph
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(f"""
                UPDATE detection_sessions SET
                    origin_iata = {ph}, origin_icao = {ph},
                    destination_iata = {ph}, destination_icao = {ph}
                WHERE id = {ph}
            """, (
                route_data.get("origin_iata"), route_data.get("origin_icao"),
                route_data.get("destination_iata"), route_data.get("destination_icao"),
                session_id
            ))
            conn.commit()
        finally:
            conn.close()

    def upsert_enrichment(self, ac_id: int, enrich_data: Dict[str, Any]):
        now_dt = datetime.now(timezone.utc)
        now_val = now_dt if self.is_pg else now_dt.isoformat()
        first_flight = _parse_date(enrich_data.get("first_flight_date")) if self.is_pg else (enrich_data.get("first_flight_date") or None)
        ph = self.ph
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            if self.is_pg:
                cur.execute(f"""
                    INSERT INTO aircraft_enrichment (
                        aircraft_id, registration, aircraft_type, manufacturer, model,
                        operator_name, operator_icao, operator_iata, country, source, source_url,
                        manufacturer_icao, operator_callsign, owner, serial_number, type_code,
                        icao_aircraft_type, built, first_flight_date, category, created_at, updated_at
                    ) VALUES (
                        {ph}, {ph}, {ph}, {ph}, {ph},
                        {ph}, {ph}, {ph}, {ph}, {ph}, {ph},
                        {ph}, {ph}, {ph}, {ph}, {ph},
                        {ph}, {ph}, {ph}, {ph}, {ph}, {ph}
                    )
                    ON CONFLICT (aircraft_id) DO UPDATE SET
                        registration = COALESCE(NULLIF(EXCLUDED.registration, ''), aircraft_enrichment.registration),
                        aircraft_type = COALESCE(NULLIF(EXCLUDED.aircraft_type, ''), aircraft_enrichment.aircraft_type),
                        manufacturer = COALESCE(NULLIF(EXCLUDED.manufacturer, ''), aircraft_enrichment.manufacturer),
                        model = COALESCE(NULLIF(EXCLUDED.model, ''), aircraft_enrichment.model),
                        operator_name = COALESCE(NULLIF(EXCLUDED.operator_name, ''), aircraft_enrichment.operator_name),
                        operator_icao = COALESCE(NULLIF(EXCLUDED.operator_icao, ''), aircraft_enrichment.operator_icao),
                        operator_iata = COALESCE(NULLIF(EXCLUDED.operator_iata, ''), aircraft_enrichment.operator_iata),
                        country = COALESCE(NULLIF(EXCLUDED.country, ''), aircraft_enrichment.country),
                        source = COALESCE(NULLIF(EXCLUDED.source, ''), aircraft_enrichment.source),
                        source_url = COALESCE(NULLIF(EXCLUDED.source_url, ''), aircraft_enrichment.source_url),
                        manufacturer_icao = COALESCE(NULLIF(EXCLUDED.manufacturer_icao, ''), aircraft_enrichment.manufacturer_icao),
                        operator_callsign = COALESCE(NULLIF(EXCLUDED.operator_callsign, ''), aircraft_enrichment.operator_callsign),
                        owner = COALESCE(NULLIF(EXCLUDED.owner, ''), aircraft_enrichment.owner),
                        serial_number = COALESCE(NULLIF(EXCLUDED.serial_number, ''), aircraft_enrichment.serial_number),
                        type_code = COALESCE(NULLIF(EXCLUDED.type_code, ''), aircraft_enrichment.type_code),
                        icao_aircraft_type = COALESCE(NULLIF(EXCLUDED.icao_aircraft_type, ''), aircraft_enrichment.icao_aircraft_type),
                        built = COALESCE(NULLIF(EXCLUDED.built, ''), aircraft_enrichment.built),
                        first_flight_date = COALESCE(EXCLUDED.first_flight_date, aircraft_enrichment.first_flight_date),
                        category = COALESCE(NULLIF(EXCLUDED.category, ''), aircraft_enrichment.category),
                        updated_at = EXCLUDED.updated_at;
                """, (
                    ac_id,
                    enrich_data.get("registration"), enrich_data.get("aircraft_type"), enrich_data.get("manufacturer"), enrich_data.get("model"),
                    enrich_data.get("operator_name"), enrich_data.get("operator_icao"), enrich_data.get("operator_iata"), enrich_data.get("country"),
                    enrich_data.get("source"), enrich_data.get("source_url"), enrich_data.get("manufacturer_icao"), enrich_data.get("operator_callsign"),
                    enrich_data.get("owner"), enrich_data.get("serial_number"), enrich_data.get("type_code"), enrich_data.get("icao_aircraft_type"),
                    enrich_data.get("built"), first_flight, enrich_data.get("category"),
                    now_val, now_val
                ))
            else:
                cur.execute("SELECT id FROM aircraft_enrichment WHERE aircraft_id = ?", (ac_id,))
                if cur.fetchone():
                    cur.execute("""
                        UPDATE aircraft_enrichment SET
                            registration = ?, aircraft_type = ?, manufacturer = ?, model = ?,
                            operator_name = ?, operator_icao = ?, operator_iata = ?, country = ?,
                            source = ?, source_url = ?, manufacturer_icao = ?, operator_callsign = ?,
                            owner = ?, serial_number = ?, type_code = ?, icao_aircraft_type = ?,
                            built = ?, first_flight_date = ?, category = ?, updated_at = ?
                        WHERE aircraft_id = ?
                    """, (
                        enrich_data.get("registration"), enrich_data.get("aircraft_type"), enrich_data.get("manufacturer"), enrich_data.get("model"),
                        enrich_data.get("operator_name"), enrich_data.get("operator_icao"), enrich_data.get("operator_iata"), enrich_data.get("country"),
                        enrich_data.get("source"), enrich_data.get("source_url"), enrich_data.get("manufacturer_icao"), enrich_data.get("operator_callsign"),
                        enrich_data.get("owner"), enrich_data.get("serial_number"), enrich_data.get("type_code"), enrich_data.get("icao_aircraft_type"),
                        enrich_data.get("built"), first_flight, enrich_data.get("category"), now_val,
                        ac_id
                    ))
                else:
                    cur.execute("""
                        INSERT INTO aircraft_enrichment (
                            aircraft_id, registration, aircraft_type, manufacturer, model,
                            operator_name, operator_icao, operator_iata, country, source, source_url,
                            manufacturer_icao, operator_callsign, owner, serial_number, type_code,
                            icao_aircraft_type, built, first_flight_date, category, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        ac_id,
                        enrich_data.get("registration"), enrich_data.get("aircraft_type"), enrich_data.get("manufacturer"), enrich_data.get("model"),
                        enrich_data.get("operator_name"), enrich_data.get("operator_icao"), enrich_data.get("operator_iata"), enrich_data.get("country"),
                        enrich_data.get("source"), enrich_data.get("source_url"), enrich_data.get("manufacturer_icao"), enrich_data.get("operator_callsign"),
                        enrich_data.get("owner"), enrich_data.get("serial_number"), enrich_data.get("type_code"), enrich_data.get("icao_aircraft_type"),
                        enrich_data.get("built"), first_flight, enrich_data.get("category"),
                        now_val, now_val
                    ))
            conn.commit()
        finally:
            conn.close()


db_manager = DatabaseManager()
