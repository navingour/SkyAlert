"""Standalone SkyAlert backend service.

Serves the API surface the existing frontend remote client consumes, plus a
minimal HTML compatibility layer (/skyalert/, /skyalert/aircraft/{id}) so the
current frontend keeps working without modification. The collector runs as a
background thread inside this single process.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app import service
from app.collector import collector
from app.db import db
from app.util import format_ist_datetime


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("skyalert.api")

app = FastAPI(
    title="SkyAlert Standalone Backend",
    version="1.0",
)


@app.on_event("startup")
def _startup():
    collector.start()
    logger.info("SkyAlert backend started (collector running)")


@app.on_event("shutdown")
def _shutdown():
    collector.stop()


# ─────────────────────────────────────────────────────────────
# JSON API
# ─────────────────────────────────────────────────────────────


@app.get("/api/dashboard")
def api_dashboard():
    return JSONResponse(service.dashboard())


@app.get("/api/live-aircraft")
def api_live_aircraft():
    """Live aircraft feed including current detection-session route."""

    conn = db.connect()
    cur = conn.cursor()

    try:
        # Latest observation for every currently active detection session.
        #
        # IMPORTANT:
        # Route information belongs to detection_sessions, so the active
        # session route is selected here and returned to the frontend.
        cur.execute(
            """
            SELECT
                a.id AS aircraft_id,
                a.icao_hex,
                a.callsign,
                a.registration,
                a.aircraft_type,
                a.manufacturer,
                a.model,
                a.operator,
                a.first_seen,
                a.last_seen,
                a.total_sessions,
                a.total_observations,

                e.registration AS e_reg,
                e.manufacturer AS e_mfr,
                e.model AS e_model,
                e.operator_name AS e_op,
                e.operator_icao,
                e.operator_iata,
                e.country,
                e.owner,
                e.serial_number,
                e.type_code,
                e.icao_aircraft_type,
                e.built,
                e.first_flight_date,
                e.category,

                s.id AS session_id,

                -- CURRENT SESSION ROUTE
                s.origin_iata,
                s.origin_icao,
                s.destination_iata,
                s.destination_icao,

                o.latitude,
                o.longitude,
                o.altitude_baro,
                o.altitude_geom,
                o.ground_speed,
                o.track,
                o.vertical_rate,
                o.squawk,
                o.distance_km,
                o.bearing,
                o.timestamp

            FROM detection_sessions s

            JOIN aircraft a
                ON a.id = s.aircraft_id

            LEFT JOIN aircraft_enrichment e
                ON e.aircraft_id = a.id

            LEFT JOIN observations o
                ON o.session_id = s.id
                AND o.id = (
                    SELECT MAX(id)
                    FROM observations
                    WHERE session_id = s.id
                )

            WHERE s.ended_at IS NULL
            """
        )

        aircraft = []

        for r in cur.fetchall():

            # Normalise to a plain dict regardless of driver
            # (sqlite3.Row / RealDictRow).
            try:
                row = dict(r)
            except Exception:
                row = r

            def g(key, index):
                if isinstance(row, dict):
                    return row.get(key)
                return r[index]

            # ─────────────────────────────────────────────
            # Route
            # ─────────────────────────────────────────────

            origin_iata = g("origin_iata", 27)
            origin_icao = g("origin_icao", 28)

            destination_iata = g("destination_iata", 29)
            destination_icao = g("destination_icao", 30)

            # Prefer IATA because it is what the frontend normally displays.
            # Fall back to ICAO when IATA is unavailable.
            origin = origin_iata or origin_icao
            destination = destination_iata or destination_icao

            if origin and destination:
                route = f"{origin} → {destination}"
            else:
                route = None

            # ─────────────────────────────────────────────
            # Live position/data
            # ─────────────────────────────────────────────

            live = {
                "hex": g("icao_hex", 1),
                "flight": g("callsign", 2),

                "lat": g("latitude", 31),
                "lon": g("longitude", 32),

                "alt_baro": g("altitude_baro", 33),
                "alt_geom": g("altitude_geom", 34),

                "gs": g("ground_speed", 35),
                "track": g("track", 36),

                "baro_rate": g("vertical_rate", 37),
                "squawk": g("squawk", 38),

                "r_dst": g("distance_km", 39),
                "r_dir": g("bearing", 40),

                "timestamp": g("timestamp", 41),

                # ─────────────────────────────────────
                # ROUTE
                # ─────────────────────────────────────

                "origin_iata": origin_iata,
                "origin_icao": origin_icao,

                "destination_iata": destination_iata,
                "destination_icao": destination_icao,

                "route": route,
            }

            # ─────────────────────────────────────────────
            # Aircraft identity
            # ─────────────────────────────────────────────

            identity = {
                "aircraft_id": g("aircraft_id", 0),
                "icao_hex": g("icao_hex", 1),

                "callsign": g("callsign", 2) or "-",

                "registration": (
                    g("e_reg", 12)
                    or g("registration", 3)
                ),

                "aircraft_type": g("aircraft_type", 4),

                "manufacturer": (
                    g("e_mfr", 13)
                    or g("manufacturer", 5)
                ),

                "model": (
                    g("e_model", 14)
                    or g("model", 6)
                ),

                "operator": (
                    g("e_op", 15)
                    or g("operator", 7)
                ),

                "operator_icao": g("operator_icao", 16),
                "operator_iata": g("operator_iata", 17),

                "country": g("country", 18),
                "owner": g("owner", 19),

                "serial_number": g("serial_number", 20),
                "type_code": g("type_code", 21),

                "icao_aircraft_type": g("icao_aircraft_type", 22),

                "built": g("built", 23),
                "first_flight_date": g("first_flight_date", 24),

                "category": g("category", 25),

                "first_seen": g("first_seen", 8),
                "last_seen": g("last_seen", 9),

                "total_sessions": (
                    g("total_sessions", 10) or 0
                ),

                "total_observations": (
                    g("total_observations", 11) or 0
                ),

                # Current session route is also exposed in identity
                # so the frontend can consume it from either object.
                "origin_iata": origin_iata,
                "origin_icao": origin_icao,

                "destination_iata": destination_iata,
                "destination_icao": destination_icao,

                "route": route,
            }

            aircraft.append(
                {
                    "live": live,
                    "identity": identity,
                }
            )

        return JSONResponse(
            {
                "aircraft": aircraft,
                "now": format_ist_datetime(
                    datetime.now(timezone.utc)
                ),
            }
        )

    except Exception as e:
        logger.exception(
            "live-aircraft error: %s",
            e,
        )

        return JSONResponse(
            {
                "aircraft": [],
            }
        )

    finally:
        conn.close()


@app.get("/api/rare-aircraft")
def api_rare(
    max_visits: int = Query(
        5,
        ge=1,
        le=100,
    )
):
    return JSONResponse(
        {
            "rare_aircraft": service.rare_aircraft(
                max_visits
            )
        }
    )


@app.get("/api/status")
def api_status():
    return JSONResponse(
        {
            "status": "ok",
            "collector": collector.stats,
        }
    )


# ─────────────────────────────────────────────────────────────
# HTML compatibility surface
# ─────────────────────────────────────────────────────────────


def _esc(v):
    s = "" if v is None else str(v)

    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


@app.get(
    "/skyalert/",
    response_class=HTMLResponse,
)
def html_list(
    search: str = "",
    status: str = "all",
):
    items = service.list_aircraft(
        search=search,
        status=status,
    )

    rows = []

    for a in items:
        rows.append(
            "<tr>"
            f"<td><a href=\"/skyalert/aircraft/{a['id']}\">"
            f"{_esc(a['icao_hex'])}"
            "</a></td>"

            f"<td>{_esc(a['callsign'])}</td>"

            f"<td>{_esc(a['registration'])}</td>"

            f"<td>{_esc(a['aircraft_type'])}</td>"

            f"<td>{_esc(a['model'])}</td>"

            f"<td>{_esc(a['operator'])}</td>"

            f"<td>{_esc(a['first_seen_ist'])}</td>"

            f"<td>{_esc(a['last_seen_ist'])}</td>"

            f"<td>{a.get('visits_today', 0)}</td>"

            f"<td>{_esc(a.get('duration_today', '0m'))}</td>"

            f"<td>{a['lifetime_visits']}</td>"

            f"<td>{a['lifetime_observations']}</td>"

            "</tr>"
        )

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>SkyAlert</title>
</head>

<body>

<h2>SkyAlert Aircraft</h2>

<table>

<thead>
<tr>
    <th>ICAO</th>
    <th>Callsign</th>
    <th>Registration</th>
    <th>Type</th>
    <th>Model</th>
    <th>Operator</th>
    <th>First Seen</th>
    <th>Last Seen</th>
    <th>Today</th>
    <th>Duration</th>
    <th>Lifetime</th>
    <th>Observations</th>
</tr>
</thead>

<tbody>
    {''.join(rows)}
</tbody>

</table>

</body>
</html>
"""


@app.get(
    "/skyalert/aircraft/{aircraft_id}",
    response_class=HTMLResponse,
)
def html_aircraft(
    aircraft_id: str,
):
    # Accept either numeric id or ICAO hex.
    d = service.aircraft_detail(
        aircraft_id
    )

    if not d:
        return HTMLResponse(
            "Aircraft not found",
            status_code=404,
        )

    sess_rows = []

    for s in d["sessions"]:

        ended = (
            s["ended_at_ist"]
            if s["ended_at"]
            else "Active"
        )

        route = "-"

        if (
            s.get("origin_iata")
            and s.get("destination_iata")
        ):
            route = (
                f"{s['origin_iata']} → "
                f"{s['destination_iata']}"
            )

        elif (
            s.get("origin_icao")
            and s.get("destination_icao")
        ):
            route = (
                f"{s['origin_icao']} → "
                f"{s['destination_icao']}"
            )

        sess_rows.append(
            "<tr>"

            f"<td>{_esc(s['started_at_ist'])}</td>"

            f"<td>{_esc(format_ist_datetime(s['last_observed_at']))}</td>"

            f"<td>{_esc(ended)}</td>"

            f"<td>{_esc(route)}</td>"

            f"<td>{_esc(s['duration'])}</td>"

            f"<td>{s['observation_count']}</td>"

            f"<td>"
            f"{s['first_distance_km'] "
            f"if s['first_distance_km'] is not None else '-'} km"
            f"</td>"

            f"<td>"
            f"{s['last_distance_km'] "
            f"if s['last_distance_km'] is not None else '-'} km"
            f"</td>"

            "</tr>"
        )

    return f"""
<!DOCTYPE html>
<html>

<head>
    <meta charset="UTF-8">

    <title>
        SkyAlert - {_esc(d['icao_hex'])}
    </title>
</head>

<body>

<h2>
    {_esc(d['icao_hex'])}
    {(' · ' + _esc(d['callsign']))
        if d['callsign'] != '-'
        else ''}
</h2>

<div class="details-grid">

<div>
    <span>Registration</span>
    <strong>{_esc(d['registration'])}</strong>
</div>

<div>
    <span>Aircraft Type</span>
    <strong>{_esc(d['aircraft_type'])}</strong>
</div>

<div>
    <span>Manufacturer</span>
    <strong>{_esc(d['manufacturer'])}</strong>
</div>

<div>
    <span>Model</span>
    <strong>{_esc(d['model'])}</strong>
</div>

<div>
    <span>Operator</span>
    <strong>{_esc(d['operator'])}</strong>
</div>

<div>
    <span>Operator ICAO</span>
    <strong>{_esc(d['operator_icao'])}</strong>
</div>

<div>
    <span>First Seen</span>
    <strong>{_esc(d['first_seen_ist'])}</strong>
</div>

<div>
    <span>Last Seen</span>
    <strong>{_esc(d['last_seen_ist'])}</strong>
</div>

<div>
    <span>Lifetime Sessions</span>
    <strong>{d['total_sessions']}</strong>
</div>

<div>
    <span>Observations</span>
    <strong>{d['total_observations']}</strong>
</div>

</div>


<h2>Detection Sessions</h2>

<table>

<thead>
<tr>
    <th>Started</th>
    <th>Last Seen</th>
    <th>Ended</th>
    <th>Route</th>
    <th>Duration</th>
    <th>Observations</th>
    <th>First Distance</th>
    <th>Last Distance</th>
</tr>
</thead>

<tbody>
    {''.join(sess_rows)}
</tbody>

</table>

</body>
</html>
"""


@app.get("/")
def root():
    return {
        "service": "skyalert-backend",
        "status": "ok",
        "collector": collector.stats,
    }