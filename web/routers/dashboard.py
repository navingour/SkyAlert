from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from web.services.config_manager import config_manager
from web.services.status_service import status_service

BASE_DIR = Path(__file__).resolve().parent.parent

templates = Jinja2Templates(
    directory=str(BASE_DIR / "templates")
)

router = APIRouter()

@router.get("/")
@router.get("/dashboard")
@router.get("/live")
@router.get("/aircraft")
@router.get("/aircraft/{subpath:path}")
@router.get("/sessions")
@router.get("/sessions/{subpath:path}")
@router.get("/flight/{subpath:path}")
@router.get("/replay/{subpath:path}")
@router.get("/analytics")
@router.get("/analytics/{subpath:path}")
@router.get("/map")
@router.get("/operators")
@router.get("/operators/{subpath:path}")
@router.get("/types")
@router.get("/types/{subpath:path}")
@router.get("/rare")
@router.get("/rare-aircraft")
@router.get("/unknown")
@router.get("/telegram")
@router.get("/telegram/{subpath:path}")
@router.get("/settings")
async def index_view(request: Request, subpath: str = ""):
    """Renders the master SkyAlert aviation monitoring and intelligence platform."""
    config = config_manager.load()
    return templates.TemplateResponse(
        request=request,
        name="layout/base.html",
        context={
            "request": request,
            "title": "SkyAlert · Aviation Intelligence & Station Radar",
            "config": config
        }
    )
