"""FAA NOTAMs - NOTAMs activos via FAA NMS API."""
import os
import aiohttp
from typing import Dict, List, Any
from datetime import datetime, timezone


class FAANOTAMClient:
    """Cliente para FAA NMS API (requiere cuenta MyAccess)."""

    def __init__(self):
        self.api_key = os.getenv("FAA_NMS_API_KEY", "")
        self.base_url = "https://api.faa.gov/nmsapi"
        self.http = aiohttp.ClientSession()

    async def close(self):
        if self.http and not self.http.closed:
            await self.http.close()

    async def get_notams(self, icao: str = "", radius_nm: int = 50,
                         lat: float = None, lon: float = None) -> List[Dict]:
        """Obtener NOTAMs activos por ubicación o ICAO."""
        if not self.api_key:
            return [{"error": "FAA_NMS_API_KEY not configured"}]

        try:
            url = f"{self.base_url}/notams"
            params = {"api_key": self.api_key}
            if icao:
                params["icao"] = icao
            if lat and lon:
                params["lat"] = lat
                params["lon"] = lon
                params["radius"] = radius_nm

            async with self.http.get(url, params=params,
                                     timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    notams = data.get("notams", []) if isinstance(data, dict) else data
                    return [{
                        "id": n.get("id", ""),
                        "icao": n.get("icao", ""),
                        "text": n.get("text", ""),
                        "type": n.get("type", ""),
                        "start": n.get("start", ""),
                        "end": n.get("end", ""),
                        "source": "faa.gov",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    } for n in notams[:100]]
                elif resp.status == 401:
                    return [{"error": "Invalid FAA API key"}]
        except Exception as e:
            print(f"⚠️  Error FAA NOTAMs: {e}")
        return []

    async def get_notam_detail(self, notam_id: str) -> Dict[str, Any]:
        """Obtener detalle de un NOTAM específico."""
        if not self.api_key:
            return {"error": "FAA_NMS_API_KEY not configured"}

        try:
            url = f"{self.base_url}/notams/{notam_id}"
            params = {"api_key": self.api_key}
            async with self.http.get(url, params=params,
                                     timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            print(f"⚠️  Error FAA NOTAM detail: {e}")
        return {"error": "Failed to fetch NOTAM detail"}
