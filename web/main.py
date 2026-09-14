import os
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from web.routers import api
from web.routers import dashboard
from web.routers import settings
from web.routers import ws

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Run collector in background unless disabled
    collector_task = None
    enable_collector = os.environ.get("ENABLE_COLLECTOR", "true").lower() not in ("false", "0", "no")
    
    if enable_collector:
        try:
            from app.collector.engine import collector_engine
            collector_task = asyncio.create_task(collector_engine.start())
        except Exception as e:
            import logging
            logging.getLogger("skyalert.web").error(f"Failed to start collector: {e}")

    yield

    # Shutdown: Cleanly close collector
    if collector_task:
        try:
            from app.collector.engine import collector_engine
            await collector_engine.close()
            collector_task.cancel()
        except Exception:
            pass


app = FastAPI(
    title="SkyAlert Aviation Intelligence & Fixed Station Monitoring",
    description="Fixed-location ADS-B aircraft monitoring, analytics, and intelligence platform.",
    version="3.0",
    lifespan=lifespan
)


from fastapi.responses import FileResponse

app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR / "static"),
    name="static"
)

@app.api_route("/favicon.ico", methods=["GET", "HEAD"], include_in_schema=False)
async def favicon():
    return FileResponse(BASE_DIR / "static" / "img" / "favicon-32.png")

# API router
app.include_router(api.router)

# Dashboard / Web Views router
app.include_router(dashboard.router)

# Settings router
app.include_router(settings.router)

# WebSocket router
app.include_router(ws.router)
