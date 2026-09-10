import asyncio
import httpx
import logging
from typing import Dict, Any, List
from app.backend.session_manager import session_manager

logger = logging.getLogger("skyalert.backend.collector")

class Collector:
    def __init__(self, url: str, poll_interval: int = 5):
        self.url = url
        self.poll_interval = poll_interval
        self.client = httpx.AsyncClient(timeout=10.0)

    async def run(self):
        logger.info(f"Starting collector, polling {self.url} every {self.poll_interval}s")
        while True:
            try:
                resp = await self.client.get(self.url)
                if resp.status_code == 200:
                    data = resp.json()
                    aircraft_list = data.get("aircraft", [])
                    for plane in aircraft_list:
                        # Process each observation through the session manager
                        session_manager.process_observation(plane)
                else:
                    logger.warning(f"Collector HTTP error: {resp.status_code}")
            except Exception as e:
                logger.error(f"Collector connection error: {e}")
            
            await asyncio.sleep(self.poll_interval)

    async def close(self):
        await self.client.aclose()
