"""GraphHopper Routes - Cálculo de rutas y optimización."""
import os
import aiohttp
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone


class GraphHopperClient:
    """Cliente para GraphHopper Directions API."""

    def __init__(self):
        self.api_key = os.getenv("GRAPHHOPPER_API_KEY", "")
        self.base_url = "https://graphhopper.com/api/1"
        self.http = aiohttp.ClientSession()

    async def close(self):
        if self.http and not self.http.closed:
            await self.http.close()

    async def get_route(self, from_lat: float, from_lon: float,
                        to_lat: float, to_lon: float,
                        vehicle: str = "car") -> Dict[str, Any]:
        """Calcular ruta entre dos puntos."""
        if not self.api_key:
            return {"error": "GRAPHHOPPER_API_KEY not configured"}

        try:
            url = f"{self.base_url}/route"
            params = {
                "point": [f"{from_lat},{from_lon}", f"{to_lat},{to_lon}"],
                "vehicle": vehicle,
                "locale": "en",
                "key": self.api_key,
                "instructions": "true",
                "points_encoded": "false"
            }
            async with self.http.get(url, params=params,
                                     timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    paths = data.get("paths", [])
                    if paths:
                        path = paths[0]
                        return {
                            "distance_m": path.get("distance", 0),
                            "time_ms": path.get("time", 0),
                            "points": path.get("points", {}).get("coordinates", []),
                            "instructions": path.get("instructions", []),
                            "vehicle": vehicle,
                            "source": "graphhopper.com",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
        except Exception as e:
            print(f"⚠️  Error GraphHopper: {e}")
        return {"error": "Failed to fetch route"}

    async def get_isochrone(self, lat: float, lon: float,
                           time_limit: int = 600,
                           vehicle: str = "car") -> Dict[str, Any]:
        """Calcular isócrona (área alcanzable en X segundos)."""
        if not self.api_key:
            return {"error": "GRAPHHOPPER_API_KEY not configured"}

        try:
            url = f"{self.base_url}/isochrone"
            params = {
                "point": f"{lat},{lon}",
                "time_limit": time_limit,
                "vehicle": vehicle,
                "key": self.api_key
            }
            async with self.http.get(url, params=params,
                                     timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "polygons": data.get("polygons", []),
                        "center": [lon, lat],
                        "time_limit": time_limit,
                        "vehicle": vehicle,
                        "source": "graphhopper.com",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
        except Exception as e:
            print(f"⚠️  Error GraphHopper isochrone: {e}")
        return {"error": "Failed to fetch isochrone"}
