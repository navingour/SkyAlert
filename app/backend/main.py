import asyncio
import logging
import yaml
from pathlib import Path
from app.backend.collector import Collector
from app.backend.session_manager import session_manager
from app.backend.enricher import enricher_service
from app.backend.db import db_manager

# Set up simple logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("skyalert.backend.main")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_FILE = BASE_DIR / "config" / "config.yaml"

def load_config():
    with open(CONFIG_FILE, "r") as f:
        return yaml.safe_load(f)

async def async_main():
    config = load_config()
    url = config.get("tar1090", {}).get("url", "http://localhost/tar1090/data/aircraft.json")
    poll_interval = config.get("general", {}).get("poll_interval", 5)

    # Initialize collector
    collector = Collector(url=url, poll_interval=poll_interval)

    # Update session manager with configured station location if available
    station_config = config.get("station", {})
    if "latitude" in station_config and "longitude" in station_config:
        session_manager.station_lat = station_config["latitude"]
        session_manager.station_lon = station_config["longitude"]

    logger.info("=" * 60)
    logger.info("SkyAlert Backend Started")
    logger.info("=" * 60)

    try:
        await collector.run()
    except asyncio.CancelledError:
        logger.info("Shutting down SkyAlert backend...")
    finally:
        await collector.close()
        await enricher_service.close()

def main():
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user, shutting down.")

if __name__ == "__main__":
    main()
