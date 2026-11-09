"""USGS Earthquakes - Terremotos reales sin autenticación."""
import aiohttp
from typing import Dict, List, Any
from datetime import datetime, timezone


class USGSEarthquakeClient:
    """Cliente para USGS Earthquake API (sin auth, ilimitado)."""

    def __init__(self):
        self.base_url = "https://earthquake.usgs.gov/earthquakes/feed/v1.0"
        self.http = aiohttp.ClientSession()

    async def close(self):
        if self.http and not self.http.closed:
            await self.http.close()

    async def get_significant(self, min_mag: float = 4.5, days: int = 1) -> List[Dict]:
        """Obtener terremotos significativos."""
        try:
            url = f"{self.base_url}/summary/{min_mag}_day.geojson"
            async with self.http.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    features = data.get("features", [])
                    return [{
                        "id": f.get("id", ""),
                        "magnitude": f.get("properties", {}).get("mag", 0),
                        "place": f.get("properties", {}).get("place", ""),
                        "time": f.get("properties", {}).get("time", 0),
                        "latitude": f.get("geometry", {}).get("coordinates", [0, 0])[1],
                        "longitude": f.get("geometry", {}).get("coordinates", [0, 0])[0],
                        "depth": f.get("geometry", {}).get("coordinates", [0, 0, 0])[2],
                        "alert": f.get("properties", {}).get("alert", ""),
                        "tsunami": f.get("properties", {}).get("tsunami", 0),
                        "source": "earthquake.usgs.gov",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    } for f in features]
        except Exception as e:
            print(f"⚠️  Error USGS: {e}")
        return []

    async def query_bbox(self, min_lat: float, max_lat: float,
                         min_lon: float, max_lon: float,
                         min_mag: float = 4.0, start_time: str = None) -> List[Dict]:
        """Query espacial vía FDSN (hasta junio 2026)."""
        try:
            url = "https://earthquake.usgs.gov/fdsnws/event/1/query"
            params = {
                "format": "geojson",
                "minlatitude": min_lat,
                "maxlatitude": max_lat,
                "minlongitude": min_lon,
                "maxlongitude": max_lon,
                "minmagnitude": min_mag
            }
            if start_time:
                params["starttime"] = start_time

            async with self.http.get(url, params=params,
                                     timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    features = data.get("features", [])
                    return [{
                        "id": f.get("id", ""),
                        "magnitude": f.get("properties", {}).get("mag", 0),
                        "place": f.get("properties", {}).get("place", ""),
                        "latitude": f.get("geometry", {}).get("coordinates", [0, 0])[1],
                        "longitude": f.get("geometry", {}).get("coordinates", [0, 0])[0],
                        "depth": f.get("geometry", {}).get("coordinates", [0, 0, 0])[2],
                        "source": "earthquake.usgs.gov",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    } for f in features]
        except Exception as e:
            print(f"⚠️  Error USGS FDSN: {e}")
        return []
