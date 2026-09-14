from app.logger import logger
from datetime import datetime
from app.event_database import event_db


class Notifier:

    def __init__(self, telegram=None):
        self.telegram = telegram

    def send(self, alert, plane):

        special = plane.get("special") or {}

        # -------------------------------------------------
        # Aircraft information
        # -------------------------------------------------

        flight = (plane.get("flight") or "").strip() or "N/A"
        registration = plane.get("registration") or "N/A"
        aircraft = plane.get("description") or plane.get("model") or "Unknown Model"
        aircraft_type = plane.get("aircraft_type") or plane.get("type") or "N/A"
        manufacturer = plane.get("manufacturer") or ""
        owner = plane.get("owner") or special.get("operator") or ""

        hexcode = str(plane.get("hex", "")).strip().upper()
        squawk = str(plane.get("squawk") or "----")

        alt_val = plane.get("alt_baro")
        altitude = "N/A" if alt_val is None else f"{alt_val:,} ft"

        dst_val = plane.get("r_dst")
        distance = "N/A" if dst_val is None else f"{round(dst_val, 1)} km"

        trk_val = plane.get("track")
        heading = "N/A" if trk_val is None else f"{round(trk_val)}°"

        gs_val = plane.get("gs")
        speed = "N/A" if gs_val is None else f"{round(gs_val * 1.852)} km/h ({round(gs_val)} kt)"

        operator = special.get("operator") or plane.get("operator") or ""
        campaign = special.get("campaign") or ""
        category = special.get("category") or ""
        photo_url = plane.get("image_url") or plane.get("photo_url") or special.get("image_url")

        tags = []
        for key in ("tag1", "tag2", "tag3"):
            value = special.get(key, "").strip()
            if value:
                tags.append(value)

        # -------------------------------------------------
        # Build HTML Telegram Message
        # -------------------------------------------------

        title_header = alert.get('title', '🚨 SKYALERT DETECTION')

        message = f"<b>{title_header}</b>\n\n"
        message += f"✈️ <b>Flight:</b> <code>{flight}</code>\n"
        message += f"🛩 <b>Registration:</b> <code>{registration}</code>\n"
        message += f"📋 <b>Aircraft:</b> {aircraft} (<code>{aircraft_type}</code>)\n"

        if operator:
            message += f"👥 <b>Operator:</b> {operator}\n"
        elif manufacturer:
            message += f"🏭 <b>Manufacturer:</b> {manufacturer}\n"

        message += f"\n🎯 <b>Squawk:</b> <code>{squawk}</code>\n"
        message += f"📏 <b>Altitude:</b> {altitude}\n"
        message += f"🚀 <b>Speed:</b> {speed}\n"
        message += f"📍 <b>Distance from Station:</b> {distance}\n"
        message += f"🧭 <b>Track:</b> {heading}  ·  <b>HEX:</b> <code>{hexcode}</code>\n"

        if campaign:
            message += f"🎖 <b>Category/Role:</b> {campaign} {category}\n"

        if tags:
            message += f"🏷 <b>Tags:</b> {', '.join(tags)}\n"

        time_str = datetime.now().strftime('%d %b %Y %H:%M:%S IST')
        message += f"\n🕒 <i>{time_str}</i>"

        logger.info(f"Generated Alert: {title_header} | Flight: {flight} | Hex: {hexcode}")

        # -------------------------------------------------
        # Save event to database
        # -------------------------------------------------

        try:
            event_id = event_db.save(alert, plane)
            plane["_event_id"] = event_id
        except Exception:
            logger.exception("Failed to save event")

        # -------------------------------------------------
        # Dispatch Telegram Notification
        # -------------------------------------------------

        if self.telegram:
            try:
                self.telegram.send(message, photo_url=photo_url)
            except Exception:
                logger.exception("Telegram notification delivery failed")
