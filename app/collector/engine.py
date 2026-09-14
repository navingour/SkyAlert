import asyncio
import math
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Set, Tuple
from datetime import datetime, timezone, timedelta

import httpx
import yaml

from app.db_manager import db_manager
from app.rules import RuleEngine
from app.telegram import TelegramNotifier
from app.notifier import Notifier
from app.aircraft_enricher import aircraft_enricher
from app.alert_lookup import AlertLookup

logger = logging.getLogger("skyalert.collector")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_FILE = BASE_DIR / "config" / "config.yaml"


def load_config() -> Dict[str, Any]:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Error reading config.yaml: {e}")
    return {}


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


class ActiveSession:
    """Represents an active in-memory flight pass / visit."""
    def __init__(self, session_id: int, aircraft_id: int, hex_code: str, now_dt: datetime, dist_km: Optional[float], bearing: Optional[float], alt: Optional[int], spd: Optional[float]):
        self.session_id = session_id
        self.aircraft_id = aircraft_id
        self.hex_code = hex_code
        self.first_seen = now_dt
        self.last_seen = now_dt
        self.last_sample_time = now_dt
        self.first_dist_km = dist_km
        self.first_bearing = bearing
        self.last_dist_km = dist_km
        self.last_bearing = bearing
        self.min_dist_km = dist_km
        self.min_alt = alt
        self.max_alt = alt
        self.max_spd = spd
        self.last_alt = alt
        self.last_spd = spd
        self.observation_count = 1
        self.alerted_rule_keys: Set[str] = set()
        self.dirty = True

    def update(self, now_dt: datetime, dist_km: Optional[float], bearing: Optional[float], alt: Optional[int], spd: Optional[float]):
        self.last_seen = now_dt
        self.observation_count += 1
        self.dirty = True

        if dist_km is not None:
            self.last_dist_km = dist_km
            if self.min_dist_km is None or dist_km < self.min_dist_km:
                self.min_dist_km = dist_km

        if bearing is not None:
            self.last_bearing = bearing

        if alt is not None:
            if self.min_alt is None or alt < self.min_alt:
                self.min_alt = alt
            if self.max_alt is None or alt > self.max_alt:
                self.max_alt = alt
            self.last_alt = alt

        if spd is not None:
            if self.max_spd is None or spd > self.max_spd:
                self.max_spd = spd
            self.last_spd = spd


class UnifiedCollector:
    """
    Unified High-Performance Collector Engine for SkyAlert.
    
    Features:
    1. Single async polling loop for readsb/dump1090/tar1090.
    2. Smart Session Manager: tracks first/last seen, closest point of approach (CPA), duration, bearings.
    3. Smart Observation Throttling: Prevents DB bloat (saves trajectory samples at 30s intervals or on key maneuvers).
    4. Offline First Auto-Enrichment: 33MB local CSV lookup + operator database.
    5. Integrated Rule Engine & Telegram Dispatcher: Alerts on squawks, military, VIP, helicopters, rare, vicinity targets.
    6. Automatic Database Bootstrapping (PostgreSQL or SQLite).
    """

    def __init__(self):
        self.config = load_config()
        self.url = self.config.get("tar1090", {}).get("url") or "http://localhost/tar1090/data/aircraft.json"
        self.poll_interval = int(self.config.get("general", {}).get("poll_interval", 5))
        
        station_cfg = self.config.get("station", {}) or self.config.get("geofence", {})
        self.station_lat = float(station_cfg.get("latitude", 22.5726))
        self.station_lon = float(station_cfg.get("longitude", 88.3639))

        collector_cfg = self.config.get("collector", {})
        self.session_timeout = timedelta(minutes=int(collector_cfg.get("session_timeout_minutes", 10)))
        
        telemetry_cfg = collector_cfg.get("telemetry", {})
        self.telemetry_enabled = telemetry_cfg.get("enabled", True)
        self.sample_interval_sec = int(telemetry_cfg.get("sample_interval_sec", 30))

        # Core Engines
        self.alert_lookup = AlertLookup()
        self.rule_engine = RuleEngine(self.config)
        
        tg_cfg = self.config.get("telegram", {})
        self.telegram = None
        if tg_cfg.get("enabled"):
            self.telegram = TelegramNotifier(
                token=tg_cfg.get("bot_token", ""),
                chat_id=str(tg_cfg.get("chat_id", "")),
                photo_enabled=tg_cfg.get("photo_enabled", True)
            )
        self.notifier = Notifier(self.telegram)

        # In-Memory Active Sessions State
        self.active_sessions: Dict[str, ActiveSession] = {}
        self.client: Optional[httpx.AsyncClient] = None
        self.is_running = False
        self.last_cleanup_time = datetime.now(timezone.utc)

        # Global per-aircraft alert cooldown: (hex, rule_key) -> last_notified datetime
        # Prevents duplicate Telegram messages across session boundaries (45-min window)
        self.ALERT_COOLDOWN_SECONDS = 45 * 60  # 45 minutes
        self._alert_cooldown: Dict[Tuple[str, str], datetime] = {}

    async def start(self):
        """Starts the unified collector background loop."""
        self.is_running = True
        self.client = httpx.AsyncClient(timeout=10.0)
        
        logger.info("=" * 65)
        logger.info("  ✈  SkyAlert Unified Collector Engine Started")
        logger.info(f"  📡 Receiver Feed Endpoint: {self.url}")
        logger.info(f"  📍 Station Location: ({self.station_lat:.4f}, {self.station_lon:.4f})")
        logger.info(f"  ⏱  Poll Interval: {self.poll_interval}s | Session Gap: {self.session_timeout}")
        logger.info(f"  📉 Smart Telemetry Sample Interval: {self.sample_interval_sec}s")
        logger.info("=" * 65)

        # Send Telegram startup announcement if configured
        if self.telegram and self.telegram.token and self.telegram.chat_id:
            try:
                msg = (
                    "<b>🛫 SkyAlert Station Started</b>\n\n"
                    "<i>Collector engine online · Live airspace monitoring active.</i>"
                )
                asyncio.create_task(asyncio.to_thread(self.telegram.send, msg))
            except Exception as e:
                logger.debug(f"Telegram start notification notice: {e}")

        while self.is_running:
            try:
                await self.poll_cycle()
            except asyncio.CancelledError:
                logger.info("Collector received cancellation signal.")
                break
            except Exception as e:
                logger.error(f"Error in collector poll cycle: {e}")

            await asyncio.sleep(self.poll_interval)

    async def poll_cycle(self):
        """Single polling cycle."""
        try:
            resp = await self.client.get(self.url)
            if resp.status_code != 200:
                logger.warning(f"Receiver HTTP error ({resp.status_code}) from {self.url}")
                return
            data = resp.json()
            aircraft_list = data.get("aircraft", [])
        except Exception as e:
            logger.debug(f"Receiver connection notice ({self.url}): {e}")
            return

        now_dt = datetime.now(timezone.utc)

        for plane in aircraft_list:
            try:
                self.process_aircraft_plane(plane, now_dt)
            except Exception as e:
                logger.debug(f"Error processing aircraft {plane.get('hex')}: {e}")

        # Periodic cleanup of expired sessions
        if (now_dt - self.last_cleanup_time).total_seconds() > 30:
            self.cleanup_expired_sessions(now_dt)
            self.last_cleanup_time = now_dt

    def process_aircraft_plane(self, plane: Dict[str, Any], now_dt: datetime):
        """Processes a single aircraft observation from the receiver JSON."""
        hex_code = (plane.get("hex") or "").strip().upper()
        if not hex_code or len(hex_code) < 3:
            return

        callsign = (plane.get("flight") or plane.get("callsign") or "").strip()
        reg = plane.get("registration") or plane.get("r")
        ac_type = plane.get("aircraft_type") or plane.get("t")
        lat = plane.get("lat") or plane.get("latitude")
        lon = plane.get("lon") or plane.get("longitude")
        alt = plane.get("alt_baro") or plane.get("alt_geom")
        spd = plane.get("gs")
        track = plane.get("track")
        squawk = plane.get("squawk")

        # Compute or extract distance & bearing from station
        dist_km = plane.get("r_dst")
        bearing_deg = plane.get("r_dir")
        if (dist_km is None or bearing_deg is None) and lat is not None and lon is not None:
            try:
                dist_km = haversine_distance_km(self.station_lat, self.station_lon, float(lat), float(lon))
                bearing_deg = calculate_bearing(self.station_lat, self.station_lon, float(lat), float(lon))
            except Exception:
                pass

        plane["r_dst"] = dist_km
        plane["r_dir"] = bearing_deg

        # 1. Database Aircraft Upsert
        ac_id = db_manager.upsert_aircraft(hex_code, callsign, reg, ac_type)
        plane["_aircraft_id"] = ac_id

        # 2. Session Lifecycle Management
        active = self.active_sessions.get(hex_code)
        is_new_session = False

        if active:
            if (now_dt - active.last_seen) > self.session_timeout:
                # Expired -> close session and start a new one
                self.close_session_in_db(active)
                is_new_session = True
            else:
                active.update(now_dt, dist_km, bearing_deg, alt, spd)
        else:
            is_new_session = True

        if is_new_session:
            # Insert new detection session in DB
            session_id = self.start_session_in_db(ac_id, now_dt, dist_km, bearing_deg)
            active = ActiveSession(session_id, ac_id, hex_code, now_dt, dist_km, bearing_deg, alt, spd)
            self.active_sessions[hex_code] = active

            # Trigger auto-enrichment on new pass
            self.trigger_enrichment(ac_id, hex_code, callsign, session_id)

        # 3. Smart Observation Sampling (Throttling)
        should_sample = False
        time_since_sample = (now_dt - active.last_sample_time).total_seconds()
        
        if is_new_session:
            should_sample = True
        elif time_since_sample >= self.sample_interval_sec:
            should_sample = True
        elif squawk in ("7500", "7600", "7700"):
            should_sample = True
        elif active.last_alt is not None and alt is not None and abs(alt - active.last_alt) >= 1000:
            should_sample = True

        if should_sample and self.telemetry_enabled:
            active.last_sample_time = now_dt
            self.record_sampled_observation(ac_id, active.session_id, now_dt, plane, dist_km, bearing_deg)

        # 4. Rule Engine & Telegram Alerts Evaluation
        special = self.alert_lookup.get(hex_code) or {}
        plane["special"] = special
        alerts = self.rule_engine.evaluate(plane, special)

        now_for_cooldown = datetime.now(timezone.utc)
        for alert in alerts:
            rule_key = alert.get("title", "ALERT")
            cooldown_key = (hex_code, rule_key)
            last_notified = self._alert_cooldown.get(cooldown_key)

            # Check global 45-minute cooldown (cross-session deduplication)
            in_cooldown = (
                last_notified is not None
                and (now_for_cooldown - last_notified).total_seconds() < self.ALERT_COOLDOWN_SECONDS
            )

            if rule_key not in active.alerted_rule_keys:
                active.alerted_rule_keys.add(rule_key)
                try:
                    # Always record to alert_history DB (for the log dashboard)
                    db_manager.record_alert(alert, plane)
                except Exception as dbe:
                    logger.debug(f"Error saving alert history for {hex_code}: {dbe}")

                if not in_cooldown:
                    # Update cooldown timestamp before dispatching
                    self._alert_cooldown[cooldown_key] = now_for_cooldown
                    try:
                        # Dispatch to Telegram / Notifiers
                        self.notifier.send(alert, plane)
                    except Exception as e:
                        logger.error(f"Error dispatching alert {rule_key} for {hex_code}: {e}")
                else:
                    remaining = int(self.ALERT_COOLDOWN_SECONDS - (now_for_cooldown - last_notified).total_seconds()) // 60
                    logger.debug(f"Alert cooldown active for {hex_code} [{rule_key}] — suppressed, {remaining}m remaining")

    def start_session_in_db(self, ac_id: int, now_dt: datetime, dist_km: Optional[float], bearing: Optional[float]) -> int:
        """Inserts a new session record into detection_sessions, or reuses active unclosed session."""
        conn = db_manager.get_connection()
        ph = db_manager.ph
        now_val = now_dt if db_manager.is_pg else now_dt.isoformat()
        try:
            cur = conn.cursor()
            # 1. Check if an active session already exists in DB
            cur.execute(f"SELECT id FROM detection_sessions WHERE aircraft_id = {ph} AND ended_at IS NULL ORDER BY id DESC LIMIT 1", (ac_id,))
            existing = cur.fetchone()
            if existing:
                sess_id = existing["id"] if isinstance(existing, dict) else existing[0]
                cur.execute(f"UPDATE detection_sessions SET last_observed_at = {ph} WHERE id = {ph}", (now_val, sess_id))
                conn.commit()
                return sess_id

            # 2. Insert new session
            if db_manager.is_pg:
                cur.execute(f"""
                    INSERT INTO detection_sessions (aircraft_id, started_at, last_observed_at, observation_count, first_distance_km, first_bearing, last_distance_km, last_bearing, min_distance_km)
                    VALUES ({ph}, {ph}, {ph}, 1, {ph}, {ph}, {ph}, {ph}, {ph})
                    RETURNING id;
                """, (ac_id, now_val, now_val, dist_km, bearing, dist_km, bearing, dist_km))
                row = cur.fetchone()
                session_id = row["id"] if isinstance(row, dict) else row[0]
            else:
                cur.execute(f"""
                    INSERT INTO detection_sessions (aircraft_id, started_at, last_observed_at, observation_count, first_distance_km, first_bearing, last_distance_km, last_bearing, min_distance_km)
                    VALUES ({ph}, {ph}, {ph}, 1, {ph}, {ph}, {ph}, {ph}, {ph});
                """, (ac_id, now_val, now_val, dist_km, bearing, dist_km, bearing, dist_km))
                session_id = cur.lastrowid
            
            # Increment total_sessions on aircraft
            cur.execute(f"UPDATE aircraft SET total_sessions = COALESCE(total_sessions, 0) + 1, last_seen = {ph} WHERE id = {ph};", (now_val, ac_id))
            conn.commit()
            return session_id
        except Exception as e:
            logger.error(f"Error starting session in DB: {e}")
            return 0
        finally:
            conn.close()

    def close_session_in_db(self, active: ActiveSession):
        """Finalizes a session with ended_at, min_distance_km, duration, bearings, and observation counts."""
        conn = db_manager.get_connection()
        ph = db_manager.ph
        ended_val = active.last_seen if db_manager.is_pg else active.last_seen.isoformat()
        try:
            cur = conn.cursor()
            cur.execute(f"""
                UPDATE detection_sessions
                SET ended_at = {ph},
                    last_observed_at = {ph},
                    observation_count = {ph},
                    last_distance_km = {ph},
                    last_bearing = {ph},
                    min_distance_km = {ph}
                WHERE id = {ph};
            """, (ended_val, ended_val, active.observation_count, active.last_dist_km, active.last_bearing, active.min_dist_km, active.session_id))
            conn.commit()
        except Exception as e:
            logger.debug(f"Error closing session {active.session_id}: {e}")
        finally:
            conn.close()

    def record_sampled_observation(self, ac_id: int, session_id: int, now_dt: datetime, plane: Dict[str, Any], dist_km: Optional[float], bearing: Optional[float]):
        """Inserts a throttled trajectory sample breadcrumb into observations."""
        conn = db_manager.get_connection()
        ph = db_manager.ph
        now_val = now_dt if db_manager.is_pg else now_dt.isoformat()
        
        alt = plane.get("alt_baro") or plane.get("alt_geom")
        spd = plane.get("gs")
        track = plane.get("track")
        lat = plane.get("lat") or plane.get("latitude")
        lon = plane.get("lon") or plane.get("longitude")
        vert = plane.get("baro_rate")
        squawk = str(plane.get("squawk", ""))

        try:
            cur = conn.cursor()
            cur.execute(f"""
                INSERT INTO observations (aircraft_id, session_id, timestamp, altitude, ground_speed, track, latitude, longitude, vertical_rate, squawk, distance_km, bearing)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph});
            """, (ac_id, session_id, now_val, alt, spd, track, lat, lon, vert, squawk, dist_km, bearing))
            
            # Update observation count on session
            cur.execute(f"UPDATE detection_sessions SET last_observed_at = {ph}, observation_count = COALESCE(observation_count, 0) + 1 WHERE id = {ph};", (now_val, session_id))
            conn.commit()
        except Exception as e:
            logger.debug(f"Error recording sampled observation: {e}")
        finally:
            conn.close()

    def trigger_enrichment(self, ac_id: int, hex_code: str, callsign: str, session_id: int):
        """Asynchronously enriches aircraft via offline 33MB CSV + fallback online services."""
        asyncio.create_task(self._async_enrich(ac_id, hex_code, callsign, session_id))

    async def _async_enrich(self, ac_id: int, hex_code: str, callsign: str, session_id: int):
        try:
            # 1. Offline & Local Enricher
            enrich_data = aircraft_enricher.enrich(hex_code, callsign)
            if enrich_data:
                db_manager.upsert_enrichment(ac_id, enrich_data)
        except Exception as e:
            logger.debug(f"Enrichment task error for {hex_code}: {e}")

    def cleanup_expired_sessions(self, now_dt: datetime):
        """Sweeps in-memory sessions and closes any that have exceeded the timeout gap."""
        expired_hexes = []
        for hex_code, active in self.active_sessions.items():
            if (now_dt - active.last_seen) > self.session_timeout:
                self.close_session_in_db(active)
                expired_hexes.append(hex_code)

        for h in expired_hexes:
            del self.active_sessions[h]

        if expired_hexes:
            logger.debug(f"Closed and purged {len(expired_hexes)} expired active sessions.")

    async def close(self):
        """Gracefully closes all active sessions and network connections."""
        self.is_running = False
        now_dt = datetime.now(timezone.utc)
        for active in self.active_sessions.values():
            self.close_session_in_db(active)
        self.active_sessions.clear()

        if self.client:
            await self.client.aclose()
        logger.info("SkyAlert Unified Collector closed gracefully.")


# Global instance
collector_engine = UnifiedCollector()
