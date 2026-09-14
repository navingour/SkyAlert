#!/usr/bin/env python3
"""
SkyAlert Master Application Entry Point
Starts the Unified ADS-B Collector & Web Intelligence Platform.
"""

import sys
import os
import argparse
import asyncio
import logging
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("skyalert.main")


def main():
    parser = argparse.ArgumentParser(description="SkyAlert Aviation Intelligence & ADS-B Fixed Station Platform")
    parser.add_argument("--web-only", "-w", action="store_true", help="Start only the web dashboard (disable collector)")
    parser.add_argument("--collector-only", "-c", action="store_true", help="Start only the collector engine (headless)")
    parser.add_argument("--port", "-p", type=int, default=8080, help="Web dashboard port (default: 8080)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Web dashboard host (default: 0.0.0.0)")
    args = parser.parse_args()

    print("\n" + "=" * 65)
    print("  ✈  SkyAlert Aviation Intelligence & Fixed Station Control")
    print("=" * 65 + "\n")

    if args.collector_only:
        # Headless collector only
        from app.collector.engine import collector_engine
        try:
            asyncio.run(collector_engine.start())
        except KeyboardInterrupt:
            logger.info("Collector interrupted by user.")
        finally:
            asyncio.run(collector_engine.close())
    else:
        # Web dashboard + background collector (via lifespan)
        if args.web_only:
            os.environ["ENABLE_COLLECTOR"] = "false"
        else:
            os.environ["ENABLE_COLLECTOR"] = "true"

        import uvicorn
        uvicorn.run("web.main:app", host=args.host, port=args.port, reload=False, log_level="info")


if __name__ == "__main__":
    main()
