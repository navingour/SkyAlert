import time
import json
import re
import logging
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger("skyalert.specs")

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / "data" / "cache"
CACHE_FILE = CACHE_DIR / "specs_cache.json"

# Cache TTL: 7 days in seconds
SPECS_CACHE_TTL = 7 * 24 * 60 * 60

# Common ICAO type code to API Ninjas (Manufacturer, Model) mappings
TYPE_CODE_SPECS_MAP = {
    # Airbus
    "A318": ("Airbus", "A318"),
    "A319": ("Airbus", "A319"),
    "A320": ("Airbus", "A320"),
    "A20N": ("Airbus", "A320neo"),
    "A321": ("Airbus", "A321"),
    "A21N": ("Airbus", "A321neo"),
    "A332": ("Airbus", "A330-200"),
    "A333": ("Airbus", "A330-300"),
    "A338": ("Airbus", "A330-800"),
    "A339": ("Airbus", "A330-900"),
    "A343": ("Airbus", "A340-300"),
    "A346": ("Airbus", "A340-600"),
    "A359": ("Airbus", "A350-900"),
    "A35K": ("Airbus", "A350-1000"),
    "A388": ("Airbus", "A380-800"),
    "BCS1": ("Airbus", "A220-100"),
    "BCS3": ("Airbus", "A220-300"),
    # Boeing
    "B737": ("Boeing", "737"),
    "B738": ("Boeing", "737-800"),
    "B739": ("Boeing", "737-900"),
    "B38M": ("Boeing", "737 MAX 8"),
    "B39M": ("Boeing", "737 MAX 9"),
    "B744": ("Boeing", "747-400"),
    "B748": ("Boeing", "747-8"),
    "B752": ("Boeing", "757-200"),
    "B753": ("Boeing", "757-300"),
    "B763": ("Boeing", "766-300"),
    "B772": ("Boeing", "777-200"),
    "B773": ("Boeing", "777-300"),
    "B77W": ("Boeing", "777-300ER"),
    "B77L": ("Boeing", "777-200LR"),
    "B788": ("Boeing", "787-8"),
    "B789": ("Boeing", "787-9"),
    "B78X": ("Boeing", "787-10"),
    # Embraer
    "E190": ("Embraer", "E190"),
    "E195": ("Embraer", "E195"),
    "E290": ("Embraer", "E190-E2"),
    "E295": ("Embraer", "E195-E2"),
    "E170": ("Embraer", "E170"),
    "E175": ("Embraer", "E175"),
    # ATR & Bombardier
    "AT76": ("ATR", "72-600"),
    "AT75": ("ATR", "72-500"),
    "AT45": ("ATR", "42-500"),
    "CRJ9": ("Bombardier", "CRJ-900"),
    "CRJ7": ("Bombardier", "CRJ-700"),
    "CRJ2": ("Bombardier", "CRJ-200"),
    "DH8D": ("De Havilland", "Dash 8 Q400"),
    # Business Jets
    "GLF5": ("Gulfstream", "G550"),
    "GLF6": ("Gulfstream", "G650"),
    "GLEX": ("Bombardier", "Global 6000"),
    "CL60": ("Bombardier", "Challenger 604"),
    "C56X": ("Cessna", "Citation Excel"),
    "C680": ("Cessna", "Citation Sovereign"),
    "FA7X": ("Dassault", "Falcon 7X"),
    "FA8X": ("Dassault", "Falcon 8X"),
    # Helicopters
    "B06": ("Bell", "206"),
    "B429": ("Bell", "429"),
    "EC35": ("Eurocopter", "EC135"),
    "EC45": ("Eurocopter", "EC145"),
    "EC25": ("Eurocopter", "EC225"),
    "A139": ("AgustaWestland", "AW139"),
    "S76": ("Sikorsky", "S-76"),
    "S92": ("Sikorsky", "S-92"),
}

class AircraftSpecsService:
    def __init__(self):
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._load_cache()

    def _get_api_key(self) -> Optional[str]:
        try:
            from app.config import load_config
            cfg = load_config()
            return (cfg.get("providers", {}).get("api_ninjas") or {}).get("api_key")
        except Exception:
            return None

    def _load_cache(self):
        try:
            if CACHE_FILE.exists():
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    self._memory_cache = json.load(f)
        except Exception as e:
            logger.debug(f"Could not load specs cache: {e}")
            self._memory_cache = {}

    def _save_cache(self):
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self._memory_cache, f)
        except Exception as e:
            logger.debug(f"Could not save specs cache: {e}")

    def get_specs(self, manufacturer: Optional[str] = None, model: Optional[str] = None, type_code: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Fetches technical specifications for aircraft or helicopter from API Ninjas with caching.
        """
        mfr_raw = (manufacturer or "").strip()
        mdl_raw = (model or "").strip()
        type_clean = (type_code or "").strip().upper()

        # Check known mappings if model or manufacturer is vague
        if type_clean in TYPE_CODE_SPECS_MAP:
            mapped_mfr, mapped_mdl = TYPE_CODE_SPECS_MAP[type_clean]
            if not mfr_raw or mfr_raw.lower() in ("unknown", "commercial"):
                mfr_raw = mapped_mfr
            if not mdl_raw or mdl_raw.lower() in ("unknown", "commercial", type_clean.lower()):
                mdl_raw = mapped_mdl

        mfr_clean = self._clean_manufacturer(mfr_raw)
        mdl_clean = self._clean_model(mdl_raw)

        if not mdl_clean:
            return None

        cache_key = f"{mfr_clean}_{mdl_clean}".upper()
        now = time.time()

        if cache_key in self._memory_cache:
            entry = self._memory_cache[cache_key]
            cached_at = entry.get("timestamp", 0)
            if now - cached_at < SPECS_CACHE_TTL:
                return entry.get("data")

        api_key = self._get_api_key()
        specs_data = None

        if api_key:
            # 1. Try aircraft endpoint
            specs_data = self._query_api_ninjas("aircraft", mfr_clean, mdl_clean, api_key)
            # 2. If not found, try helicopter endpoint
            if not specs_data:
                specs_data = self._query_api_ninjas("helicopter", mfr_clean, mdl_clean, api_key)

        # Fallback to local reference database for common aircraft specs if API Ninjas key not set or 404
        if not specs_data:
            specs_data = self._get_local_fallback_specs(type_clean, mfr_clean, mdl_clean)

        self._memory_cache[cache_key] = {
            "timestamp": now,
            "data": specs_data
        }
        self._save_cache()
        return specs_data

    def _clean_manufacturer(self, mfr: str) -> str:
        if not mfr:
            return ""
        m = mfr.strip()
        if "AIRBUS" in m.upper():
            return "Airbus"
        if "BOEING" in m.upper():
            return "Boeing"
        if "EMBRAER" in m.upper():
            return "Embraer"
        if "BOMBARDIER" in m.upper():
            return "Bombardier"
        if "GULFSTREAM" in m.upper():
            return "Gulfstream"
        if "CESSNA" in m.upper():
            return "Cessna"
        if "DASSAULT" in m.upper():
            return "Dassault"
        if "BELL" in m.upper():
            return "Bell"
        if "SIKORSKY" in m.upper():
            return "Sikorsky"
        if "EUROCOPTER" in m.upper() or "AIRBUS HELICOPTERS" in m.upper():
            return "Eurocopter"
        if "AGUSTA" in m.upper() or "LEONARDO" in m.upper():
            return "AgustaWestland"
        if "ATR" in m.upper():
            return "ATR"
        return m.split()[0] if m else ""

    def _clean_model(self, model: str) -> str:
        if not model:
            return ""
        m = model.strip()
        # Remove common prefixes like 'AIRBUS A-321' -> 'A321'
        m = re.sub(r"^(AIRBUS|BOEING|EMBRAER|BOMBARDIER|GULFSTREAM|CESSNA|BELL|ATR)\s*", "", m, flags=re.IGNORECASE).strip()
        m = m.replace("A-", "A").replace("B-", "")
        return m

    def _query_api_ninjas(self, category: str, mfr: str, model: str, api_key: str) -> Optional[Dict[str, Any]]:
        try:
            params = {}
            if mfr:
                params["manufacturer"] = mfr
            if model:
                params["model"] = model
            if not params:
                return None

            url = f"https://api.api-ninjas.com/v1/{category}?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(url, headers={
                "X-Api-Key": api_key,
                "User-Agent": "SkyAlert/3.0"
            })
            with urllib.request.urlopen(req, timeout=4) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if isinstance(data, list) and len(data) > 0:
                        raw = data[0]
                        raw["category_type"] = category.capitalize()
                        return raw
        except Exception as e:
            logger.debug(f"API Ninjas {category} query failed: {e}")
        return None

    def _get_local_fallback_specs(self, type_code: str, mfr: str, model: str) -> Optional[Dict[str, Any]]:
        """Built-in specifications for primary commercial and corporate aircraft."""
        SPECS_DB = {
            "A321": {
                "manufacturer": "Airbus", "model": "A321-200", "engine_type": "Turbofan (CFM56 / IAE V2500)",
                "max_speed_knots": "470", "cruise_speed_knots": "450", "ceiling_ft": "39800",
                "gross_weight_lbs": "205000", "empty_weight_lbs": "106900", "length_ft": "146.0",
                "height_ft": "38.7", "wing_span_ft": "117.5", "range_nautical_miles": "3200",
                "category_type": "Aircraft"
            },
            "A320": {
                "manufacturer": "Airbus", "model": "A320-200", "engine_type": "Turbofan (CFM56 / IAE V2500)",
                "max_speed_knots": "470", "cruise_speed_knots": "450", "ceiling_ft": "39800",
                "gross_weight_lbs": "172000", "empty_weight_lbs": "93900", "length_ft": "123.3",
                "height_ft": "38.7", "wing_span_ft": "117.5", "range_nautical_miles": "3300",
                "category_type": "Aircraft"
            },
            "A20N": {
                "manufacturer": "Airbus", "model": "A320neo", "engine_type": "Turbofan (CFM LEAP-1A / PW1100G)",
                "max_speed_knots": "470", "cruise_speed_knots": "450", "ceiling_ft": "39800",
                "gross_weight_lbs": "174200", "empty_weight_lbs": "97700", "length_ft": "123.3",
                "height_ft": "38.7", "wing_span_ft": "117.5", "range_nautical_miles": "3500",
                "category_type": "Aircraft"
            },
            "A21N": {
                "manufacturer": "Airbus", "model": "A321neo", "engine_type": "Turbofan (CFM LEAP-1A / PW1100G)",
                "max_speed_knots": "470", "cruise_speed_knots": "450", "ceiling_ft": "39800",
                "gross_weight_lbs": "213800", "empty_weight_lbs": "110900", "length_ft": "146.0",
                "height_ft": "38.7", "wing_span_ft": "117.5", "range_nautical_miles": "4000",
                "category_type": "Aircraft"
            },
            "B738": {
                "manufacturer": "Boeing", "model": "737-800", "engine_type": "Turbofan (CFM56-7B)",
                "max_speed_knots": "469", "cruise_speed_knots": "453", "ceiling_ft": "41000",
                "gross_weight_lbs": "174200", "empty_weight_lbs": "91110", "length_ft": "129.5",
                "height_ft": "41.2", "wing_span_ft": "117.4", "range_nautical_miles": "2935",
                "category_type": "Aircraft"
            },
            "B77W": {
                "manufacturer": "Boeing", "model": "777-300ER", "engine_type": "Turbofan (GE90-115B)",
                "max_speed_knots": "510", "cruise_speed_knots": "482", "ceiling_ft": "43100",
                "gross_weight_lbs": "775000", "empty_weight_lbs": "370000", "length_ft": "242.3",
                "height_ft": "61.3", "wing_span_ft": "212.6", "range_nautical_miles": "7370",
                "category_type": "Aircraft"
            },
            "B789": {
                "manufacturer": "Boeing", "model": "787-9 Dreamliner", "engine_type": "Turbofan (GEnx-1B / Trent 1000)",
                "max_speed_knots": "511", "cruise_speed_knots": "488", "ceiling_ft": "43000",
                "gross_weight_lbs": "560000", "empty_weight_lbs": "284000", "length_ft": "206.1",
                "height_ft": "55.8", "wing_span_ft": "197.3", "range_nautical_miles": "7530",
                "category_type": "Aircraft"
            },
            "A359": {
                "manufacturer": "Airbus", "model": "A350-900", "engine_type": "Turbofan (Rolls-Royce Trent XWB-84)",
                "max_speed_knots": "510", "cruise_speed_knots": "488", "ceiling_ft": "43100",
                "gross_weight_lbs": "617290", "empty_weight_lbs": "313700", "length_ft": "219.2",
                "height_ft": "56.1", "wing_span_ft": "212.4", "range_nautical_miles": "8100",
                "category_type": "Aircraft"
            },
            "GLF5": {
                "manufacturer": "Gulfstream Aerospace", "model": "G550", "engine_type": "Turbofan (Rolls-Royce BR710)",
                "engine_thrust_lb_ft": "15385", "max_speed_knots": "590", "cruise_speed_knots": "566",
                "ceiling_ft": "51000", "takeoff_ground_run_ft": "5910", "landing_ground_roll_ft": "2770",
                "gross_weight_lbs": "91000", "empty_weight_lbs": "47900", "length_ft": "96.4",
                "height_ft": "25.8", "wing_span_ft": "93.5", "range_nautical_miles": "6750",
                "category_type": "Aircraft"
            },
            "B06": {
                "manufacturer": "Bell Helicopter", "model": "206L-3", "max_speed_sl_knots": "130",
                "cruise_speed_sl_knots": "110", "range_nautical_miles": "305", "cruise_time_min": "180",
                "fuel_capacity_gallons": "110", "gross_external_load_lbs": "4250", "main_rotor_diameter_ft": "37.0",
                "num_blades": "2", "length_ft": "42.7", "height_ft": "10.5",
                "category_type": "Helicopter"
            }
        }
        if type_code in SPECS_DB:
            return SPECS_DB[type_code]

        # Match by model key
        for k, v in SPECS_DB.items():
            if k.lower() in model.lower() or model.lower() in v["model"].lower():
                return v
        return None

specs_service = AircraftSpecsService()
