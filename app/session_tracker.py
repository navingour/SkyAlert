import math
import json
import logging
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from app.db_manager import db_manager, IST_TZ
from app.config import load_config

logger = logging.getLogger("skyalert.tracker")

# Default station location in India (can be overridden in config.yaml)
DEFAULT_STATION_LAT = 22.5726
DEFAULT_STATION_LON = 88.3639
SESSION_GAP_MINUTES = 10


def lookup_flight_route(callsign: str, icao_hex: str) -> Dict[str, Optional[str]]:
    """
    Calls ADSBDB to resolve the flight route for a given callsign/hex.
    Returns a dict with origin_iata, origin_icao, destination_iata, destination_icao.
    All values are None if the lookup fails or the route is not found.
    Uses a short timeout to avoid blocking the collector loop.
    """
    empty = {"origin_iata": None, "origin_icao": None,
             "destination_iata": None, "destination_icao": None}
    cs = (callsign or "").strip().upper()
    hex_u = (icao_hex or "").strip().upper()
    try:
        # Prefer callsign lookup; fall back to aircraft hex lookup
        if cs and cs != "-":
            url = f"https://api.adsbdb.com/v0/callsign/{cs}"
        elif hex_u:
            url = f"https://api.adsbdb.com/v0/aircraft/{hex_u}"
        else:
            return empty

        req = urllib.request.Request(url, headers={"User-Agent": "SkyAlert-Collector/1.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                fr = data.get("response", {}).get("flightroute")
                if fr and fr.get("origin") and fr.get("destination"):
                    orig = fr["origin"]
                    dest = fr["destination"]
                    return {
                        "origin_iata": orig.get("iata_code") or None,
                        "origin_icao": orig.get("icao_code") or None,
                        "destination_iata": dest.get("iata_code") or None,
                        "destination_icao": dest.get("icao_code") or None,
                    }
    except Exception as e:
        logger.debug(f"Route lookup failed for {cs or hex_u}: {e}")
    return empty

def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate Great Circle distance between two points in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2.0) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 2)

def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate initial bearing (forward azimuth) from point 1 to point 2 in degrees (0-360)."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)
    y = math.sin(delta_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)
    bearing = math.degrees(math.atan2(y, x))
    return round((bearing + 360.0) % 360.0, 1)

class SessionTracker:
    def __init__(self):
        self.config = load_config()
        station_cfg = self.config.get("station", {})
        self.station_lat = station_cfg.get("latitude", DEFAULT_STATION_LAT)
        self.station_lon = station_cfg.get("longitude", DEFAULT_STATION_LON)
        self.session_gap = timedelta(minutes=station_cfg.get("session_gap_minutes", SESSION_GAP_MINUTES))

    def update_station_location(self, lat: float, lon: float):
        self.station_lat = lat
        self.station_lon = lon

    def process_aircraft_observation(self, plane: Dict[str, Any], observation_time: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Processes a single aircraft ADS-B observation:
        Updates or creates aircraft record, tracks continuous visits/sessions,
        and saves observation point.
        """
        now_dt = observation_time or datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()

        hex_code = (plane.get("hex") or "").strip().upper()
        if not hex_code:
            return {}

        callsign = (plane.get("flight") or plane.get("callsign") or "").strip()
        reg = plane.get("registration") or plane.get("r")
        ac_type = plane.get("aircraft_type") or plane.get("t")
        lat = plane.get("lat") or plane.get("latitude")
        lon = plane.get("lon") or plane.get("longitude")
        alt_baro = plane.get("alt_baro") or plane.get("altitude")
        alt_geom = plane.get("alt_geom")
        gs = plane.get("gs") or plane.get("ground_speed")
        track = plane.get("track") or plane.get("heading")
        vert_rate = plane.get("baro_rate") or plane.get("geom_rate") or plane.get("vertical_rate")
        squawk = str(plane.get("squawk") or "")
        
        # Calculate distance and bearing if coordinates present
        dist_km = plane.get("r_dst") or plane.get("distance_km")
        bearing_deg = plane.get("r_dir") or plane.get("bearing")

        if (dist_km is None or bearing_deg is None) and lat is not None and lon is not None:
            try:
                lat_f = float(lat)
                lon_f = float(lon)
                dist_km = haversine_distance_km(self.station_lat, self.station_lon, lat_f, lon_f)
                bearing_deg = calculate_bearing(self.station_lat, self.station_lon, lat_f, lon_f)
            except Exception:
                pass

        conn = db_manager.get_connection()
        cur = conn.cursor()

        # 1. Fetch or create aircraft in database
        cur.execute("SELECT id, operator, total_sessions, total_observations FROM aircraft WHERE icao_hex = ?", (hex_code,))
        ac_row = cur.fetchone()
        
        # Try to infer operator from callsign
        inferred_op = None
        if callsign and callsign != "-":
            import re
            from aircraft_enricher import OPERATOR_MAP
            match = re.match(r"^([A-Z]{3})", callsign.upper())
            if match and match.group(1) in OPERATOR_MAP:
                inferred_op = OPERATOR_MAP[match.group(1)][0]

        if ac_row:
            ac_id = ac_row[0] if isinstance(ac_row, (tuple, list)) else ac_row["id"]
            curr_op = ac_row[1] if isinstance(ac_row, (tuple, list)) else ac_row["operator"]
            
            op_update_sql = ""
            op_val = []
            if inferred_op and curr_op in ("Unknown Operator", "-", "", None):
                op_update_sql = "operator = ?,"
                op_val = [inferred_op]

            update_params = [callsign, reg, ac_type] + op_val + [now_iso, now_iso, ac_id]
            
            cur.execute(f"""
            UPDATE aircraft SET
                callsign = COALESCE(NULLIF(?, ''), callsign),
                registration = COALESCE(NULLIF(?, ''), registration),
                aircraft_type = COALESCE(NULLIF(?, ''), aircraft_type),
                {op_update_sql}
                last_seen = ?,
                total_observations = total_observations + 1,
                updated_at = ?
            WHERE id = ?
            """, tuple(update_params))
        else:
            final_op = inferred_op or 'Unknown Operator'
            cur.execute("""
            INSERT INTO aircraft (icao_hex, callsign, registration, aircraft_type, operator, first_seen, last_seen, total_sessions, total_observations, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?)
            """, (hex_code, callsign, reg, ac_type, final_op, now_iso, now_iso, now_iso, now_iso))
            cur.execute("SELECT id FROM aircraft WHERE icao_hex = ?", (hex_code,))
            ac_id = cur.fetchone()[0]

        # 2. Check for open / active detection session for this aircraft
        cur.execute("""
        SELECT id, started_at, last_observed_at, observation_count, first_distance_km, first_bearing
        FROM detection_sessions
        WHERE aircraft_id = ? AND ended_at IS NULL
        ORDER BY id DESC LIMIT 1
        """, (ac_id,))
        sess_row = cur.fetchone()

        session_id = None
        is_new_session = False

        if sess_row:
            s_id = sess_row[0] if isinstance(sess_row, (tuple, list)) else sess_row["id"]
            s_last = sess_row[2] if isinstance(sess_row, (tuple, list)) else sess_row["last_observed_at"]
            
            # Check gap between last observation and now
            try:
                if isinstance(s_last, str):
                    last_dt = datetime.fromisoformat(s_last.replace("Z", "+00:00"))
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=timezone.utc)
                else:
                    last_dt = s_last
                
                time_diff = now_dt - last_dt
            except Exception:
                time_diff = timedelta(seconds=0)

            if time_diff <= self.session_gap:
                # Same session continues
                session_id = s_id
                cur.execute("""
                UPDATE detection_sessions SET
                    last_observed_at = ?,
                    observation_count = observation_count + 1,
                    last_distance_km = COALESCE(?, last_distance_km),
                    last_bearing = COALESCE(?, last_bearing)
                WHERE id = ?
                """, (now_iso, dist_km, bearing_deg, session_id))
            else:
                # Close old session
                cur.execute("UPDATE detection_sessions SET ended_at = ? WHERE id = ?", (s_last, s_id))
                is_new_session = True

        if sess_row is None or is_new_session:
            # Lookup flight route from ADSBDB for this new session.
            # Done before the INSERT so the route is stored from the start.
            # Short timeout — if it fails, NULLs are stored (never invented).
            route = lookup_flight_route(callsign, hex_code)
            origin_iata = route["origin_iata"]
            origin_icao = route["origin_icao"]
            destination_iata = route["destination_iata"]
            destination_icao = route["destination_icao"]

            if origin_iata or origin_icao:
                logger.info(
                    "Route resolved for %s (%s): %s/%s -> %s/%s",
                    hex_code, callsign or "-",
                    origin_iata, origin_icao, destination_iata, destination_icao
                )

            # Start new session with route data
            cur.execute("""
            INSERT INTO detection_sessions (
                aircraft_id, started_at, last_observed_at, ended_at,
                observation_count, first_distance_km, first_bearing, last_distance_km, last_bearing,
                origin_iata, origin_icao, destination_iata, destination_icao
            ) VALUES (?, ?, ?, NULL, 1, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ac_id, now_iso, now_iso,
                dist_km, bearing_deg, dist_km, bearing_deg,
                origin_iata, origin_icao, destination_iata, destination_icao
            ))

            # Get new session id
            cur.execute("SELECT id FROM detection_sessions WHERE aircraft_id = ? AND ended_at IS NULL ORDER BY id DESC LIMIT 1", (ac_id,))
            session_id = cur.fetchone()[0]

            if is_new_session:
                cur.execute("UPDATE aircraft SET total_sessions = total_sessions + 1 WHERE id = ?", (ac_id,))

        # 3. Insert observation record
        cur.execute("""
        INSERT INTO observations (
            aircraft_id, session_id, timestamp, altitude_baro, altitude_geom,
            ground_speed, track, latitude, longitude, vertical_rate, squawk,
            distance_km, bearing, raw_data, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ac_id, session_id, now_iso, alt_baro, alt_geom,
            gs, track, lat, lon, vert_rate, squawk,
            dist_km, bearing_deg, json.dumps(plane), now_iso
        ))

        conn.commit()
        conn.close()

        return {
            "aircraft_id": ac_id,
            "session_id": session_id,
            "hex": hex_code,
            "distance_km": dist_km,
            "bearing": bearing_deg
        }

    def close_stale_sessions(self, timeout_minutes: int = 15):
        """Closes any open detection sessions whose last observation exceeds timeout."""
        cutoff_dt = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        cutoff_iso = cutoff_dt.isoformat()

        conn = db_manager.get_connection()
        cur = conn.cursor()
        cur.execute("""
        UPDATE detection_sessions
        SET ended_at = last_observed_at
        WHERE ended_at IS NULL AND last_observed_at < ?
        """, (cutoff_iso,))
        count = cur.rowcount
        conn.commit()
        conn.close()
        return count

session_tracker = SessionTracker()
