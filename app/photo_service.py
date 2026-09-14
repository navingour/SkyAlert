import time
import json
import logging
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger("skyalert.photo")

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / "data" / "cache"
CACHE_FILE = CACHE_DIR / "photo_cache.json"

# Cache TTL: 5 days in seconds
PHOTO_CACHE_TTL = 5 * 24 * 60 * 60

class AircraftPhotoService:
    def __init__(self):
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._load_cache()

    def _load_cache(self):
        try:
            if CACHE_FILE.exists():
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    self._memory_cache = json.load(f)
        except Exception as e:
            logger.debug(f"Could not load photo cache: {e}")
            self._memory_cache = {}

    def _save_cache(self):
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self._memory_cache, f)
        except Exception as e:
            logger.debug(f"Could not save photo cache: {e}")

    def get_photo(self, registration: Optional[str] = None, hex_code: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieves aircraft photo details (image_url, thumbnail_url, photographer, link, copyright).
        Checks temporary cache first, then tries Planespotters and JetPhotos/Airport-data.
        """
        reg_clean = (registration or "").strip().upper()
        if reg_clean in ("-", "UNKNOWN", "NONE", ""):
            reg_clean = ""

        hex_clean = (hex_code or "").strip().upper()
        if hex_clean in ("-", "UNKNOWN", "NONE", ""):
            hex_clean = ""

        cache_key = reg_clean or hex_clean
        if not cache_key:
            return None

        now = time.time()

        # Check cache
        if cache_key in self._memory_cache:
            entry = self._memory_cache[cache_key]
            cached_at = entry.get("timestamp", 0)
            if now - cached_at < PHOTO_CACHE_TTL:
                return entry.get("data")

        # Fetch live photo from providers
        photo_data = self._fetch_planespotters(reg_clean, hex_clean)
        if not photo_data and reg_clean:
            photo_data = self._fetch_airport_data(reg_clean)

        # Store in cache (even None to avoid spamming failed lookups for 1 day)
        ttl_used = PHOTO_CACHE_TTL if photo_data else (24 * 60 * 60)
        self._memory_cache[cache_key] = {
            "timestamp": now - (PHOTO_CACHE_TTL - ttl_used),
            "data": photo_data
        }
        if reg_clean and hex_clean:
            self._memory_cache[hex_clean] = self._memory_cache[cache_key]
            self._memory_cache[reg_clean] = self._memory_cache[cache_key]

        self._save_cache()
        return photo_data

    def _fetch_planespotters(self, reg: str, hex_code: str) -> Optional[Dict[str, Any]]:
        """Planespotters.net Public API Lookup."""
        urls = []
        if reg:
            urls.append(f"https://api.planespotters.net/pub/photos/reg/{urllib.parse.quote(reg)}")
        if hex_code:
            urls.append(f"https://api.planespotters.net/pub/photos/hex/{urllib.parse.quote(hex_code)}")

        for url in urls:
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": "SkyAlert/3.0 (https://github.com/navingour/SkyAlert-Full; contact@skyalert.local)",
                    "Accept": "application/json"
                })
                with urllib.request.urlopen(req, timeout=3) as resp:
                    if resp.status == 200:
                        body = json.loads(resp.read().decode("utf-8"))
                        photos = body.get("photos", [])
                        if photos:
                            p = photos[0]
                            # Medium or large thumbnail
                            thumbnail = p.get("thumbnail_large", {}).get("src") or p.get("thumbnail", {}).get("src")
                            large_img = p.get("thumbnail_large", {}).get("src") or thumbnail
                            photographer = p.get("photographer")
                            link = p.get("link")
                            copyright_info = f"© {photographer} (Planespotters.net)" if photographer else "Planespotters.net"
                            return {
                                "image_url": large_img or thumbnail,
                                "thumbnail_url": thumbnail or large_img,
                                "photographer": photographer or "Planespotters Contributor",
                                "copyright": copyright_info,
                                "source": "Planespotters.net",
                                "link": link or "https://www.planespotters.net"
                            }
            except Exception as e:
                logger.debug(f"Planespotters lookup error for {url}: {e}")
                continue

        return None

    def _fetch_airport_data(self, reg: str) -> Optional[Dict[str, Any]]:
        """Airport-data.com fallback lookup."""
        try:
            url = f"https://airport-data.com/api/ac_thumb.json?r={urllib.parse.quote(reg)}"
            req = urllib.request.Request(url, headers={"User-Agent": "SkyAlert/3.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    body = json.loads(resp.read().decode("utf-8"))
                    data = body.get("data", [])
                    if data:
                        p = data[0]
                        img = p.get("image")
                        link = p.get("link")
                        photographer = p.get("photographer")
                        return {
                            "image_url": img,
                            "thumbnail_url": img,
                            "photographer": photographer or "Airport-Data Contributor",
                            "copyright": f"© {photographer} (Airport-Data.com)" if photographer else "Airport-Data.com",
                            "source": "Airport-Data.com",
                            "link": link or "https://airport-data.com"
                        }
        except Exception as e:
            logger.debug(f"Airport-Data lookup error for {reg}: {e}")

        return None

photo_service = AircraftPhotoService()
