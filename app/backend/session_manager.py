import math
import logging
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from app.backend.db import db_manager
from app.backend.enricher import enricher_service

logger = logging.getLogger("skyalert.backend.session")

def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2.0) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 2)

def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)
    y = math.sin(delta_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)
    bearing = math.degrees(math.atan2(y, x))
    return round((bearing + 360.0) % 360.0, 1)

class SessionManager:
    def __init__(self, station_lat: float, station_lon: float, session_gap_minutes: int = 10):
        self.station_lat = station_lat
        self.station_lon = station_lon
        self.session_gap = timedelta(minutes=session_gap_minutes)
        self.last_seen_cache: Dict[str, datetime] = {}
        self.background_tasks = set()

    def _fire_enrichment(self, ac_id: int, hex_code: str, callsign: str, session_id: Optional[int]):
        task = asyncio.create_task(enricher_service.enrich_aircraft(ac_id, hex_code, callsign, session_id))
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)

    def process_observation(self, plane: Dict[str, Any]):
        hex_code = (plane.get("hex") or "").strip().upper()
        if not hex_code:
            return

        callsign = (plane.get("flight") or plane.get("callsign") or "").strip()
        reg = plane.get("registration") or plane.get("r")
        ac_type = plane.get("aircraft_type") or plane.get("t")
        lat = plane.get("lat") or plane.get("latitude")
        lon = plane.get("lon") or plane.get("longitude")
        
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

        ac_id = db_manager.upsert_aircraft(hex_code, callsign, reg, ac_type)
        session_id = db_manager.get_active_session(ac_id)

        now_dt = datetime.now(timezone.utc)
        is_new_session = False

        if session_id:
            last_dt = self.last_seen_cache.get(hex_code)
            if not last_dt:
                # Fallback to current time if cache missed, though ideally we'd query DB
                last_dt = now_dt

            if now_dt - last_dt > self.session_gap:
                db_manager.close_session(session_id)
                is_new_session = True
            else:
                db_manager.update_session(session_id, dist_km, bearing_deg)
        else:
            is_new_session = True

        if is_new_session:
            session_id = db_manager.start_session(ac_id, dist_km, bearing_deg)
            # Fire enrichment for route and aircraft details whenever a new session starts
            self._fire_enrichment(ac_id, hex_code, callsign, session_id)

        self.last_seen_cache[hex_code] = now_dt
        db_manager.insert_observation(ac_id, session_id, plane, dist_km, bearing_deg)

session_manager = SessionManager(22.5726, 88.3639) # Defaults, overwritten in main
