#!/usr/bin/env python3
"""
SkyAlert Master Application Entry Point
Starts both the Unified ADS-B Collector and the Web Intelligence Platform concurrently.
"""

import sys
import os
import argparse
import asyncio
import logging
import signal
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


async def run_unified_app(web_only: bool = False, collector_only: bool = False, host: str = "0.0.0.0", port: int = 8080):
    tasks = []

    # 1. Start Collector if not web_only
    if not web_only:
        from app.collector.engine import collector_engine
        collector_task = asyncio.create_task(collector_engine.start())
        tasks.append(collector_task)
    else:
        logger.info("ℹ️  Running in WEB-ONLY mode (Collector disabled).")

    # 2. Start Web Server if not collector_only
    if not collector_only:
        import uvicorn
        from web.main import app as fastapi_app

        config = uvicorn.Config(app=fastapi_app, host=host, port=port, log_level="info", access_log=False)
        server = uvicorn.Server(config)
        server_task = asyncio.create_task(server.serve())
        tasks.append(server_task)
    else:
        logger.info("ℹ️  Running in HEADLESS COLLECTOR-ONLY mode (Web server disabled).")

    # Wait for completion or shutdown
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("Application shutdown requested.")
    finally:
        if not web_only:
            from app.collector.engine import collector_engine
            await collector_engine.close()


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

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    main_task = loop.create_task(run_unified_app(
        web_only=args.web_only,
        collector_only=args.collector_only,
        host=args.host,
        port=args.port
    ))

    def handle_signal():
        logger.info("Stopping SkyAlert services...")
        main_task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except (NotImplementedError, AttributeError):
            pass

    try:
        loop.run_until_complete(main_task)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received.")
    finally:
        loop.close()
        logger.info("SkyAlert terminated safely.")


if __name__ == "__main__":
    main()
