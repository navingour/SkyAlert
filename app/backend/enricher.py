import asyncio
import httpx
import logging
from typing import Dict, Any, Optional
from app.backend.db import db_manager

logger = logging.getLogger("skyalert.backend.enricher")

class EnricherService:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=5.0)

    async def close(self):
        await self.client.aclose()

    async def enrich_aircraft(self, ac_id: int, hex_code: str, callsign: str, session_id: Optional[int] = None):
        """Fetches data from ADSBDB and fallbacks, then updates the database."""
        enrich_data = await self._fetch_adsbdb(hex_code, callsign)
        
        if not enrich_data.get("aircraft"):
            logger.info(f"ADSBDB aircraft data missing for {hex_code}, trying fallback HexDB")
            fallback_data = await self._fetch_hexdb(hex_code)
            if not fallback_data:
                fallback_data = await self._fetch_airframes(hex_code)
            
            if fallback_data:
                enrich_data["aircraft"] = fallback_data
        
        if enrich_data.get("aircraft"):
            db_manager.upsert_enrichment(ac_id, enrich_data["aircraft"])

        if session_id and enrich_data.get("route"):
            db_manager.update_session_route(session_id, enrich_data["route"])

    async def _fetch_adsbdb(self, hex_code: str, callsign: str) -> Dict[str, Any]:
        result = {"aircraft": None, "route": None}
        try:
            url = f"https://api.adsbdb.com/v0/aircraft/{hex_code}"
            if callsign and callsign.strip():
                url += f"?callsign={callsign.strip()}"
            
            resp = await self.client.get(url)
            if resp.status_code == 200:
                data = resp.json().get("response", {})
                
                ac_data = data.get("aircraft")
                if ac_data:
                    result["aircraft"] = {
                        "registration": ac_data.get("registration"),
                        "aircraft_type": ac_data.get("type"),
                        "manufacturer": ac_data.get("manufacturer"),
                        "model": ac_data.get("type"),  # adsbdb uses 'type' for model
                        "operator_name": ac_data.get("registered_owner"),
                        "operator_icao": ac_data.get("registered_owner_operator_flag_code"),
                        "country": ac_data.get("registered_owner_country_name"),
                        "source": "adsbdb",
                        "source_url": url,
                        "icao_aircraft_type": ac_data.get("icao_type"),
                    }
                
                route_data = data.get("flightroute")
                if route_data and route_data.get("origin") and route_data.get("destination"):
                    orig = route_data["origin"]
                    dest = route_data["destination"]
                    result["route"] = {
                        "origin_iata": orig.get("iata_code"),
                        "origin_icao": orig.get("icao_code"),
                        "destination_iata": dest.get("iata_code"),
                        "destination_icao": dest.get("icao_code")
                    }
        except Exception as e:
            logger.warning(f"ADSBDB lookup failed for {hex_code}: {e}")
        return result

    async def _fetch_hexdb(self, hex_code: str) -> Optional[Dict[str, Any]]:
        try:
            url = f"https://hexdb.io/api/v1/aircraft/{hex_code}"
            resp = await self.client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "registration": data.get("Registration"),
                    "aircraft_type": data.get("Type"),
                    "manufacturer": data.get("Manufacturer"),
                    "model": data.get("Model"),
                    "operator_name": data.get("OperatorFlagCode"),
                    "icao_aircraft_type": data.get("ICAOTypeCode"),
                    "source": "hexdb",
                    "source_url": url
                }
        except Exception as e:
            logger.debug(f"HexDB lookup failed for {hex_code}: {e}")
        return None

    async def _fetch_airframes(self, hex_code: str) -> Optional[Dict[str, Any]]:
        try:
            url = f"https://api.airframes.io/v1/airframes/icao/{hex_code}"
            resp = await self.client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                if "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
                    ac = data["data"][0]
                    return {
                        "registration": ac.get("registration"),
                        "aircraft_type": ac.get("type", {}).get("description"),
                        "manufacturer": ac.get("manufacturer", {}).get("name"),
                        "icao_aircraft_type": ac.get("type", {}).get("icao"),
                        "source": "airframes.io",
                        "source_url": url
                    }
        except Exception as e:
            logger.debug(f"Airframes lookup failed for {hex_code}: {e}")
        return None

enricher_service = EnricherService()
