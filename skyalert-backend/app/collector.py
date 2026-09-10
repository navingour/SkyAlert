"""Polls tar1090/readsb and records aircraft, detection sessions, and observations.

Route enrichment happens once per NEW session (ADSBDB), with full airport names.
Identity enrichment happens for airframes that are not yet enriched.
"""
import json
import logging
import threading
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from app.config import CONFIG
from app.db import db
from app.enrich import enricher
from app.util import bearing_deg, haversine_km, utc_now_iso

logger = logging.getLogger("skyalert.collector")

EMERGENCY_SQUAWKS = {"7700", "7500", "7600"}


def _fetch_aircraft(url: str, timeout: int = 8) -> List[Dict[str, Any]]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SkyAlert-Collector/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("aircraft", []) or []
    except Exception as e:
        logger.warning("tar1090 fetch failed %s: %s", url, e)
        return []


class Collector:
    def __init__(self):
        t = CONFIG.get("tar1090", {})
        self.url = t.get("url", "http://127.0.0.1/tar1090/data/aircraft.json")
        self.poll = int(t.get("poll_interval_seconds", 10))
        st = CONFIG.get("station", {})
        self.lat = float(st.get("latitude", 22.5726))
        self.lon = float(st.get("longitude", 88.3639))
        self.gap = timedelta(minutes=int(CONFIG.get("session_gap_minutes", 10)))
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.stats = {"polls": 0, "aircraft_seen": 0, "last_poll": None, "errors": 0}
        self._enrich_cursor_hex: Optional[str] = None  # throttle identity enrichment

    # ── identity enrichment (throttled, unknown airframes only) ────
    def _enrich_unknown_identities(self, limit: int = 3):
        conn = db.connect()
        cur = conn.cursor()
        ph = db.placeholder
        try:
            cur.execute(
                f"""SELECT a.id, a.icao_hex FROM aircraft a
                    LEFT JOIN aircraft_enrichment e ON e.aircraft_id = a.id
                    WHERE e.aircraft_id IS NULL ORDER BY a.last_seen DESC LIMIT {int(limit)}""")
            rows = cur.fetchall()
            for r in rows:
                ac_id = r["id"] if isinstance(r, dict) else r[0]
                hex_code = r["icao_hex"] if isinstance(r, dict) else r[1]
                ident = enricher.resolve_identity(hex_code)
                if not ident:
                    continue
                cur.execute(
                    f"""INSERT INTO aircraft_enrichment (aircraft_id, registration, aircraft_type,
                        manufacturer, operator_name, owner, type_code, icao_aircraft_type, country, source)
                        VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})""",
                    (ac_id, ident.get("registration"), ident.get("aircraft_type"),
                     ident.get("manufacturer"), ident.get("operator"), ident.get("owner"),
                     ident.get("type_code"), ident.get("icao_aircraft_type"), ident.get("country"),
                     "adsbdb"))
                if ident.get("registration") or ident.get("aircraft_type"):
                    cur.execute(
                        f"""UPDATE aircraft SET
                            registration = COALESCE({ph}, registration),
                            aircraft_type = COALESCE({ph}, aircraft_type),
                            manufacturer = COALESCE({ph}, manufacturer),
                            operator = COALESCE({ph}, operator)
                            WHERE id = {ph}""",
                        (ident.get("registration"), ident.get("aircraft_type"),
                         ident.get("manufacturer"), ident.get("operator"), ac_id))
            conn.commit()
        except Exception as e:
            logger.debug("identity enrichment pass failed: %s", e)
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # ── route enrichment (throttled, missing routes only) ──────────
    def _enrich_missing_routes(self, limit: int = 5):
        conn = db.connect()
        cur = conn.cursor()
        ph = db.placeholder
        try:
            cur.execute(
                f"""SELECT ds.id AS session_id, a.icao_hex, a.callsign 
                    FROM detection_sessions ds
                    JOIN aircraft a ON ds.aircraft_id = a.id
                    WHERE ds.ended_at IS NULL 
                      AND (
                          ds.origin_iata IS NULL
                          OR ds.origin_icao IS NULL
                          OR ds.destination_iata IS NULL
                          OR ds.destination_icao IS NULL
                      )
                      AND a.callsign IS NOT NULL AND a.callsign != ''
                    ORDER BY ds.id DESC LIMIT {int(limit)}"""
            )
            rows = cur.fetchall()
            for r in rows:
                session_id = r["session_id"] if isinstance(r, dict) else r[0]
                hex_code = r["icao_hex"] if isinstance(r, dict) else r[1]
                callsign = r["callsign"] if isinstance(r, dict) else r[2]
                
                route = enricher.resolve_route(callsign, hex_code)
                if not route:
                    continue
                
                # Check if route has origin/dest
                if not route.get("origin_iata") and not route.get("origin_icao"):
                    continue

                cur.execute(
                    f"""UPDATE detection_sessions SET
                        origin_iata = COALESCE({ph}, origin_iata),
                        origin_icao = COALESCE({ph}, origin_icao),
                        destination_iata = COALESCE({ph}, destination_iata),
                        destination_icao = COALESCE({ph}, destination_icao),
                        origin_name = COALESCE({ph}, origin_name),
                        origin_city = COALESCE({ph}, origin_city),
                        origin_country = COALESCE({ph}, origin_country),
                        destination_name = COALESCE({ph}, destination_name),
                        destination_city = COALESCE({ph}, destination_city),
                        destination_country = COALESCE({ph}, destination_country)
                        WHERE id = {ph}""",
                    (
                        route.get("origin_iata"), route.get("origin_icao"),
                        route.get("destination_iata"), route.get("destination_icao"),
                        route.get("origin_name"), route.get("origin_city"), route.get("origin_country"),
                        route.get("destination_name"), route.get("destination_city"), route.get("destination_country"),
                        session_id
                    )
                )
            conn.commit()
        except Exception as e:
            logger.debug("missing routes enrichment pass failed: %s", e)
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # ── cleanup (stale sessions) ───────────────────────────────────
    def _cleanup_stale_sessions(self):
        """Closes sessions for aircraft that dropped off the radar and never reappeared."""
        now_dt = datetime.now(timezone.utc)
        conn = db.connect()
        cur = conn.cursor()
        ph = db.placeholder
        try:
            cur.execute("SELECT id, last_observed_at FROM detection_sessions WHERE ended_at IS NULL")
            rows = cur.fetchall()
            for r in rows:
                sid = r["id"] if isinstance(r, dict) else r[0]
                last = r["last_observed_at"] if isinstance(r, dict) else r[1]
                try:
                    last_dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=timezone.utc)
                    if now_dt - last_dt > self.gap:
                        cur.execute(f"UPDATE detection_sessions SET ended_at = {ph} WHERE id = {ph}", (last, sid))
                except Exception:
                    pass
            conn.commit()
        except Exception as e:
            logger.debug("cleanup stale sessions failed: %s", e)
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # ── persistence ────────────────────────────────────────────────
    def _upsert_aircraft(self, cur, ph: str, plane: Dict[str, Any], now: str) -> int:
        hex_code = (plane.get("hex") or "").strip().upper()
        callsign = (plane.get("flight") or "").strip()
        ac_type = (plane.get("t") or "").strip() or None
        cur.execute(f"SELECT id FROM aircraft WHERE icao_hex = {ph}", (hex_code,))
        row = cur.fetchone()
        if row:
            ac_id = row["id"] if isinstance(row, dict) else row[0]
            cur.execute(
                f"""UPDATE aircraft SET
                    callsign = COALESCE(NULLIF({ph}, ''), callsign),
                    aircraft_type = COALESCE({ph}, aircraft_type),
                    last_seen = {ph},
                    total_observations = total_observations + 1,
                    updated_at = {ph}
                    WHERE id = {ph}""",
                (callsign, ac_type, now, now, ac_id),
            )
            return ac_id
        cur.execute(
            f"""INSERT INTO aircraft (icao_hex, callsign, aircraft_type, first_seen, last_seen,
                total_sessions, total_observations, created_at, updated_at)
                VALUES ({ph},{ph},{ph},{ph},{ph},0,1,{ph},{ph})""",
            (hex_code, callsign, ac_type, now, now, now, now),
        )
        cur.execute(f"SELECT id FROM aircraft WHERE icao_hex = {ph}", (hex_code,))
        r = cur.fetchone()
        return r["id"] if isinstance(r, dict) else r[0]

    def _session(self, cur, ph: str, ac_id: int, plane: Dict[str, Any], now_dt: datetime, now: str):
        lat, lon = plane.get("lat"), plane.get("lon")
        dist = plane.get("r_dst")
        bearing = plane.get("r_dir")
        if (dist is None or bearing is None) and lat is not None and lon is not None:
            dist = haversine_km(self.lat, self.lon, lat, lon)
            bearing = bearing_deg(self.lat, self.lon, lat, lon)

        cur.execute(
            f"""SELECT ds.id AS session_id, ds.last_observed_at AS last_observed_at, a.callsign AS callsign
                FROM detection_sessions ds
                JOIN aircraft a ON a.id = ds.aircraft_id
                WHERE ds.aircraft_id = {ph} AND ds.ended_at IS NULL
                ORDER BY ds.id DESC LIMIT 1""",
            (ac_id,),
        )
        row = cur.fetchone()
        session_id = None
        if row:
            sid = row["session_id"] if isinstance(row, dict) else row[0]
            last = row["last_observed_at"] if isinstance(row, dict) else row[1]
            cs = row["callsign"] if isinstance(row, dict) else row[2]
            try:
                last_dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                gap = now_dt - last_dt
            except Exception:
                gap = timedelta(seconds=0)
            if gap <= self.gap:
                session_id = sid
                cur.execute(
                    f"""UPDATE detection_sessions SET last_observed_at = {ph},
                        observation_count = observation_count + 1,
                        last_distance_km = COALESCE({ph}, last_distance_km),
                        last_bearing = COALESCE({ph}, last_bearing)
                        WHERE id = {ph}""",
                    (now, dist, bearing, sid),
                )
            else:
                cur.execute(f"UPDATE detection_sessions SET ended_at = {ph} WHERE id = {ph}", (last, sid))

        if session_id is None:
            # New session → resolve route once (full names).
            callsign = (plane.get("flight") or "").strip()
            route = enricher.resolve_route(callsign, plane.get("hex", "")) or {}
            cur.execute(
                f"""INSERT INTO detection_sessions (
                    aircraft_id, started_at, last_observed_at, ended_at, observation_count,
                    first_distance_km, first_bearing, last_distance_km, last_bearing,
                    origin_iata, origin_icao, destination_iata, destination_icao,
                    origin_name, origin_city, origin_country,
                    destination_name, destination_city, destination_country)
                    VALUES ({ph},{ph},{ph},NULL,1,{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})""",
                (
                    ac_id, now, now, dist, bearing, dist, bearing,
                    route.get("origin_iata"), route.get("origin_icao"),
                    route.get("destination_iata"), route.get("destination_icao"),
                    route.get("origin_name"), route.get("origin_city"), route.get("origin_country"),
                    route.get("destination_name"), route.get("destination_city"), route.get("destination_country"),
                ),
            )
            cur.execute(
                f"SELECT id FROM detection_sessions WHERE aircraft_id = {ph} AND ended_at IS NULL ORDER BY id DESC LIMIT 1",
                (ac_id,),
            )
            r = cur.fetchone()
            session_id = r["id"] if isinstance(r, dict) else r[0]
            cur.execute(f"UPDATE aircraft SET total_sessions = total_sessions + 1 WHERE id = {ph}", (ac_id,))

        return session_id

    def _observation(self, cur, ph: str, ac_id: int, session_id: int, plane: Dict[str, Any], now: str):
        lat, lon = plane.get("lat"), plane.get("lon")
        dist = plane.get("r_dst")
        bearing = plane.get("r_dir")
        if (dist is None or bearing is None) and lat is not None and lon is not None:
            dist = haversine_km(self.lat, self.lon, lat, lon)
            bearing = bearing_deg(self.lat, self.lon, lat, lon)
        cur.execute(
            f"""INSERT INTO observations (
                aircraft_id, session_id, timestamp, altitude_baro, altitude_geom,
                ground_speed, track, latitude, longitude, vertical_rate, squawk,
                distance_km, bearing, raw_data, created_at)
                VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})""",
            (
                ac_id, session_id, now,
                plane.get("alt_baro") if plane.get("alt_baro") != "ground" else None,
                plane.get("alt_geom"), plane.get("gs"), plane.get("track"),
                lat, lon, plane.get("baro_rate"), str(plane.get("squawk") or ""),
                dist, bearing, json.dumps(plane), now,
            ),
        )
        # Record emergency squawk alerts.
        squawk = str(plane.get("squawk") or "")
        if squawk in EMERGENCY_SQUAWKS:
            cur.execute(
                f"""INSERT INTO alert_history (timestamp, hex, flight, aircraft_type, alert_type,
                    title, priority, squawk, altitude, speed, distance, raw_json, updated_at)
                    VALUES ({ph},{ph},{ph},{ph},{ph},{ph},1,{ph},{ph},{ph},{ph},{ph},{ph})""",
                (
                    now, (plane.get("hex") or "").upper(), (plane.get("flight") or "").strip(),
                    plane.get("t") or "Unknown", "EMERGENCY_SQUAWK",
                    f"Emergency Squawk {squawk}", squawk,
                    plane.get("alt_baro") if plane.get("alt_baro") != "ground" else None,
                    plane.get("gs"), dist, json.dumps(plane), now,
                ),
            )

    def process(self, planes: List[Dict[str, Any]]):
        now_dt = datetime.now(timezone.utc)
        now = utc_now_iso()
        ph = db.placeholder
        conn = db.connect()
        cur = conn.cursor()
        try:
            for plane in planes:
                if not plane.get("hex"):
                    continue
                ac_id = self._upsert_aircraft(cur, ph, plane, now)
                session_id = self._session(cur, ph, ac_id, plane, now_dt, now)
                self._observation(cur, ph, ac_id, session_id, plane, now)
            conn.commit()
            self.stats["aircraft_seen"] = len(planes)
        except Exception as e:
            logger.exception("collector process error: %s", e)
            self.stats["errors"] += 1
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # ── lifecycle ──────────────────────────────────────────────────
    def _loop(self):
        logger.info("Collector started, polling %s every %ss", self.url, self.poll)
        while self._running:
            planes = _fetch_aircraft(self.url)
            self.process(planes)
            self.stats["polls"] += 1
            self.stats["last_poll"] = utc_now_iso()
            # Throttled identity enrichment for unknown airframes (every 6th poll).
            if self.stats["polls"] % 6 == 0:
                self._cleanup_stale_sessions()
                self._enrich_unknown_identities()
                self._enrich_missing_routes()
            time.sleep(self.poll)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False


collector = Collector()
