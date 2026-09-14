import math


class RuleEngine:

    def __init__(self, config):
        self.config = config

    def _in_radius(self, lat, lon, center_lat, center_lon, radius_km):
        if lat is None or lon is None or center_lat is None or center_lon is None:
            return False
        R = 6371.0
        dlat = math.radians(center_lat - lat)
        dlon = math.radians(center_lon - lon)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat))
            * math.cos(math.radians(center_lat))
            * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distance = R * c
        return distance <= radius_km

    def evaluate(self, plane, special=None):

        alerts = []
        special = special or {}

        flight = plane.get("flight", "").strip().upper()
        registration = str(plane.get("registration", "")).strip().upper()
        aircraft_type = str(plane.get("aircraft_type", "")).strip().upper()
        hexcode = str(plane.get("hex", "")).strip().upper()
        squawk = str(plane.get("squawk", ""))
        altitude = plane.get("alt_baro")
        speed = plane.get("gs")
        lat = plane.get("lat")
        lon = plane.get("lon")
        r_dst = plane.get("r_dst")
        desc = str(plane.get("description", "")).lower()
        operator = special.get("operator", "") or plane.get("operator", "")

        # ------------------------------------------------
        # SQUAWK ALERTS
        # ------------------------------------------------

        if self.config.get("alerts", {}).get("squawk", True):

            squawk_cfg = self.config.get("squawk", {})

            if squawk in squawk_cfg.get("hijack", ["7500"]):
                alerts.append({
                    "priority": 1,
                    "title": "🚨 HIJACK ALERT (Squawk 7500)"
                })
            elif squawk in squawk_cfg.get("radio_failure", ["7600"]):
                alerts.append({
                    "priority": 1,
                    "title": "📻 RADIO FAILURE (Squawk 7600)"
                })
            elif squawk in squawk_cfg.get("emergency", ["7700"]):
                alerts.append({
                    "priority": 1,
                    "title": "🚨 GENERAL EMERGENCY (Squawk 7700)"
                })

        # ------------------------------------------------
        # SPECIAL AIRCRAFT DATABASE (MILITARY / GOV / POLICE)
        # ------------------------------------------------

        campaign = special.get("campaign", "")
        is_mil = plane.get("mil") or campaign == "Mil" or "military" in desc
        is_gov = campaign == "Gov" or "vip" in desc or "government" in desc

        if is_mil and self.config.get("alerts", {}).get("military", True):
            alerts.append({
                "priority": 2,
                "title": "🪖 MILITARY AIRCRAFT DETECTED"
            })
        elif is_gov and self.config.get("alerts", {}).get("government", True):
            alerts.append({
                "priority": 2,
                "title": "👑 GOVERNMENT / VIP AIRCRAFT"
            })
        elif campaign == "Police" and self.config.get("alerts", {}).get("police", True):
            alerts.append({
                "priority": 2,
                "title": "🚓 POLICE / LAW ENFORCEMENT"
            })

        # ------------------------------------------------
        # HELICOPTERS & ROTORCRAFT
        # ------------------------------------------------

        if self.config.get("alerts", {}).get("helicopters", False) or self.config.get("alerts", {}).get("helicopter", False):
            heli_types = {"B06", "B206", "B429", "B412", "B407", "EC45", "H145", "EC35", "H135", "EC30", "H130", "AS50", "H125", "A139", "AW139", "AW109", "A109", "S76", "S92", "MI8", "MI17", "UH60", "CH47", "R44", "R66", "R22", "ALH", "LCH"}
            is_heli = (
                aircraft_type in heli_types
                or "helicopter" in desc
                or "rotorcraft" in desc
                or special.get("category") == "Helicopter"
            )
            if is_heli:
                alerts.append({
                    "priority": 3,
                    "title": f"🚁 HELICOPTER IN VICINITY ({aircraft_type or 'Rotorcraft'})"
                })

        # ------------------------------------------------
        # RARE AIRCRAFT
        # ------------------------------------------------

        if self.config.get("alerts", {}).get("rare_aircraft", True):

            rare_types = self.config.get("rare_aircraft", {}).get("aircraft_types", [])

            if aircraft_type in rare_types:
                alerts.append({
                    "priority": 3,
                    "title": f"⭐ RARE AIRCRAFT DETECTED ({aircraft_type})"
                })

        # ------------------------------------------------
        # TARGET TRACKING & WATCHLIST (WITH VICINITY RULES)
        # ------------------------------------------------

        if self.config.get("alerts", {}).get("watchlist", True):

            watch = self.config.get("watchlist", {})

            # 1. Hex Tracking
            if hexcode and hexcode in [h.upper() for h in watch.get("hex", [])]:
                alerts.append({
                    "priority": 4,
                    "title": f"🎯 TRACKED HEX IN VICINITY ({hexcode})"
                })

            # 2. Registration Tracking
            if registration and registration in [r.upper() for r in watch.get("registrations", [])]:
                alerts.append({
                    "priority": 4,
                    "title": f"🎯 TRACKED TAIL NUMBER ({registration})"
                })

            # 3. Flight / Callsign Tracking
            if flight:
                for prefix in watch.get("flights", []):
                    if flight.startswith(prefix.upper()):
                        alerts.append({
                            "priority": 4,
                            "title": f"🎯 TRACKED FLIGHT / CALLSIGN ({flight})"
                        })
                        break

            # 4. Operator Tracking
            if operator:
                for op in watch.get("operators", []):
                    if op.lower() in operator.lower():
                        alerts.append({
                            "priority": 4,
                            "title": f"🎯 TRACKED OPERATOR ({operator})"
                        })
                        break

            # 5. Structured Targets (with custom vicinity radius)
            # targets: [{"type": "hex"|"reg"|"flight"|"operator", "value": "...", "label": "...", "radius_km": 50}]
            for target in watch.get("targets", []):
                t_type = target.get("type", "hex")
                t_val = str(target.get("value", "")).strip().upper()
                t_label = target.get("label") or t_val
                t_radius = target.get("radius_km")
                t_enabled = target.get("enabled", True)

                if not t_enabled or not t_val:
                    continue

                matched = False
                if t_type == "hex" and hexcode == t_val:
                    matched = True
                elif t_type in ("registration", "reg") and registration == t_val:
                    matched = True
                elif t_type in ("flight", "callsign") and flight.startswith(t_val):
                    matched = True
                elif t_type == "operator" and t_val.lower() in operator.lower():
                    matched = True

                if matched:
                    # Check vicinity distance constraint if specified
                    if t_radius is not None and t_radius > 0:
                        if r_dst is not None:
                            if r_dst <= t_radius:
                                alerts.append({
                                    "priority": 4,
                                    "title": f"🎯 TARGET IN VICINITY: {t_label} ({round(r_dst, 1)} km away)"
                                })
                        elif lat is not None and lon is not None:
                            # If receiver lat/lon in config
                            st_lat = self.config.get("station", {}).get("latitude") or self.config.get("geofence", {}).get("latitude")
                            st_lon = self.config.get("station", {}).get("longitude") or self.config.get("geofence", {}).get("longitude")
                            if st_lat and st_lon and self._in_radius(lat, lon, st_lat, st_lon, t_radius):
                                alerts.append({
                                    "priority": 4,
                                    "title": f"🎯 TARGET IN VICINITY: {t_label} (Within {t_radius} km)"
                                })
                    else:
                        alerts.append({
                            "priority": 4,
                            "title": f"🎯 TRACKED TARGET DETECTED: {t_label}"
                        })

        # ------------------------------------------------
        # GEOFENCE & BOUNDARY RULES
        # ------------------------------------------------

        geofence_cfg = self.config.get("geofence", {})
        if geofence_cfg.get("enabled"):
            c_lat = geofence_cfg.get("latitude")
            c_lon = geofence_cfg.get("longitude")
            radius = geofence_cfg.get("radius_km", 50)
            if c_lat and c_lon and self._in_radius(lat, lon, c_lat, c_lon, radius):
                alerts.append({
                    "priority": 4,
                    "title": f"📍 GEOFENCE ZONE ({geofence_cfg.get('name', 'Restricted Area')})"
                })

        # ------------------------------------------------
        # ALTITUDE / SPEED THRESHOLD RULES
        # ------------------------------------------------

        thresholds = self.config.get("thresholds", {})
        if thresholds.get("enabled"):
            min_alt = thresholds.get("min_altitude")
            max_speed = thresholds.get("max_speed")
            if min_alt and altitude is not None and altitude < min_alt:
                alerts.append({
                    "priority": 4,
                    "title": f"⚠️ LOW ALTITUDE ALERT (<{min_alt} ft)"
                })
            if max_speed and speed is not None and speed > max_speed:
                alerts.append({
                    "priority": 4,
                    "title": f"⚡ HIGH SPEED ALERT (>{max_speed} kt)"
                })

        return alerts
