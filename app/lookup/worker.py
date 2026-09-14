from pathlib import Path
import time
import yaml

from app.lookup.queue import lookup_queue
from app.lookup.manager import lookup_manager
from app.logger import logger
from app.event_database import event_db
from app.telegram import TelegramNotifier

from app.config import load_config

config = load_config()


telegram = None

if config["telegram"]["enabled"]:
    telegram = TelegramNotifier(
        config["telegram"]["bot_token"],
        config["telegram"]["chat_id"]
    )


class LookupWorker:

    def run(self):

        logger.info("Lookup Worker Started")

        while True:

            try:

                hex_code = lookup_queue.next()

                if not hex_code:
                    time.sleep(5)
                    continue

                logger.info(
                    "Looking up %s",
                    hex_code
                )

                result = lookup_manager.lookup(
                    hex_code
                )

                if result:

                    row = event_db.update_from_lookup(
                        hex_code,
                        result
                    )

                    if row:

                        flight, registration, aircraft_type = row

                        if telegram:
                            fl_str = (flight or '').strip()
                            reg_str = (registration or '').strip()
                            links = []
                            if fl_str and fl_str != 'Unknown':
                                links.append(f'<a href="https://www.flightradar24.com/{fl_str}">Flightradar24</a>')
                                links.append(f'<a href="https://planefinder.net/flight/{fl_str}">Plane Finder</a>')
                            elif reg_str and reg_str != 'Unknown':
                                links.append(f'<a href="https://www.flightradar24.com/data/aircraft/{reg_str}">Flightradar24</a>')
                                links.append(f'<a href="https://planefinder.net/data/aircraft/{reg_str}">Plane Finder</a>')
                            elif hex_code:
                                links.append(f'<a href="https://www.flightradar24.com/{hex_code}">Flightradar24</a>')
                                links.append(f'<a href="https://planefinder.net/data/aircraft/{hex_code}">Plane Finder</a>')
                            if hex_code:
                                links.append(f'<a href="https://globe.adsbexchange.com/?icao={hex_code.lower()}">ADS-B Exchange</a>')

                            links_section = f"\n🔗 <b>Live Tracking:</b> {' · '.join(links)}\n" if links else ""

                            telegram.send(
                                f"<b>✅ Aircraft Identified</b>\n\n"
                                f"✈️ <b>Flight:</b> <code>{flight or 'Unknown'}</code>\n"
                                f"🛩 <b>Registration:</b> <code>{registration or 'Unknown'}</code>\n"
                                f"🏷 <b>ICAO Type:</b> <code>{aircraft_type or 'Unknown'}</code>\n"
                                f"🔷 <b>HEX:</b> <code>{hex_code}</code>\n"
                                f"{links_section}"
                            )

                    lookup_queue.completed(
                        hex_code
                    )

                    logger.info(
                        "Lookup complete %s",
                        hex_code
                    )

                else:

                    lookup_queue.failed(
                        hex_code
                    )

                    logger.warning(
                        "Lookup failed %s",
                        hex_code
                    )

                time.sleep(2)

            except Exception:

                logger.exception(
                    "Lookup Worker Error"
                )

                time.sleep(5)


worker = LookupWorker()
