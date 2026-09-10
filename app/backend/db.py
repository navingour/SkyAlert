import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional

logger = logging.getLogger("skyalert.backend.db")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_FILE = BASE_DIR / "data" / "skyalert_relational.db"

class DatabaseManager:
    def __init__(self, db_path: str = str(DB_FILE)):
        self.db_path = db_path
        self._ensure_db_dir()

    def _ensure_db_dir(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def upsert_aircraft(self, hex_code: str, callsign: str = None, reg: str = None, ac_type: str = None) -> int:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.get_connection() as conn:
            cur = conn.cursor()
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
                """, (callsign, reg, ac_type, now_iso, now_iso, ac_id))
            else:
                cur.execute("""
                    INSERT INTO aircraft (icao_hex, callsign, registration, aircraft_type, first_seen, last_seen, total_sessions, total_observations, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 1, 1, ?, ?)
                """, (hex_code, callsign, reg, ac_type, now_iso, now_iso, now_iso, now_iso))
                ac_id = cur.lastrowid
            conn.commit()
            return ac_id

    def get_active_session(self, ac_id: int) -> Optional[int]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id FROM detection_sessions 
                WHERE aircraft_id = ? AND ended_at IS NULL 
                ORDER BY id DESC LIMIT 1
            """, (ac_id,))
            row = cur.fetchone()
            return row["id"] if row else None

    def start_session(self, ac_id: int, dist_km: float, bearing: float) -> int:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO detection_sessions (
                    aircraft_id, started_at, last_observed_at, ended_at,
                    observation_count, first_distance_km, first_bearing, last_distance_km, last_bearing
                ) VALUES (?, ?, ?, NULL, 1, ?, ?, ?, ?)
            """, (ac_id, now_iso, now_iso, dist_km, bearing, dist_km, bearing))
            session_id = cur.lastrowid
            
            # Increment total_sessions in aircraft
            cur.execute("UPDATE aircraft SET total_sessions = total_sessions + 1 WHERE id = ?", (ac_id,))
            conn.commit()
            return session_id

    def update_session(self, session_id: int, dist_km: float, bearing: float):
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE detection_sessions SET
                    last_observed_at = ?,
                    observation_count = observation_count + 1,
                    last_distance_km = COALESCE(?, last_distance_km),
                    last_bearing = COALESCE(?, last_bearing)
                WHERE id = ?
            """, (now_iso, dist_km, bearing, session_id))
            conn.commit()

    def close_session(self, session_id: int):
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE detection_sessions 
                SET ended_at = last_observed_at 
                WHERE id = ?
            """, (session_id,))
            conn.commit()

    def insert_observation(self, ac_id: int, session_id: int, plane: Dict[str, Any], dist_km: float, bearing: float):
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO observations (
                    aircraft_id, session_id, timestamp, altitude_baro, altitude_geom,
                    ground_speed, track, latitude, longitude, vertical_rate, squawk,
                    distance_km, bearing, raw_data, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ac_id, session_id, now_iso, 
                plane.get("alt_baro"), plane.get("alt_geom"),
                plane.get("gs"), plane.get("track"), 
                plane.get("lat"), plane.get("lon"), 
                plane.get("baro_rate") or plane.get("geom_rate"), 
                str(plane.get("squawk") or ""),
                dist_km, bearing, 
                None, # Not storing full JSON to save space, or we can use json.dumps(plane)
                now_iso
            ))
            conn.commit()

    def update_session_route(self, session_id: int, route_data: Dict[str, Any]):
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE detection_sessions SET
                    origin_iata = ?, origin_icao = ?,
                    destination_iata = ?, destination_icao = ?
                WHERE id = ?
            """, (
                route_data.get("origin_iata"), route_data.get("origin_icao"),
                route_data.get("destination_iata"), route_data.get("destination_icao"),
                session_id
            ))
            conn.commit()

    def upsert_enrichment(self, ac_id: int, enrich_data: Dict[str, Any]):
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.get_connection() as conn:
            cur = conn.cursor()
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
                    enrich_data.get("built"), enrich_data.get("first_flight_date"), enrich_data.get("category"), now_iso,
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
                    enrich_data.get("built"), enrich_data.get("first_flight_date"), enrich_data.get("category"),
                    now_iso, now_iso
                ))
            conn.commit()

db_manager = DatabaseManager()
