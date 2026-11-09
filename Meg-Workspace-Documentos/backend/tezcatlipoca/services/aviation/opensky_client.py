"""OpenSky Network - Vuelos reales con autenticación."""
import os
import aiohttp
from typing import Dict, List, Any
from datetime import datetime, timezone


class OpenSkyClient:
    """Cliente para OpenSky Network API."""

    def __init__(self):
        self.username = os.getenv("OPENSKY_USERNAME", "")
        self.password = os.getenv("OPENSKY_PASSWORD", "")
        self.base_url = "https://opensky-network.org/api"
        self.http = aiohttp.ClientSession()

    async def close(self):
        if self.http and not self.http.closed:
            await self.http.close()

    async def get_states(self, lamin: float = -20, lamax: float = 10,
                         lomin: float = -60, lomax: float = -30) -> List[Dict]:
        """Obtener estados de vuelo en bounding box (Latinoamérica por defecto)."""
        try:
            url = f"{self.base_url}/states/all"
            params = {"lamin": lamin, "lamax": lamax, "lomin": lomin, "lomax": lomax}
            auth = aiohttp.BasicAuth(self.username, self.password) if self.username else None
            async with self.http.get(url, params=params, auth=auth,
                                     timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    states = data.get("states", [])
                    return [{
                        "icao24": s[0],
                        "callsign": s[1].strip() if s[1] else "Unknown",
                        "origin_country": s[2],
                        "latitude": s[6],
                        "longitude": s[5],
                        "altitude": s[7],
                        "velocity": s[9],
                        "heading": s[10],
                        "vertical_rate": s[11],
                        "squawk": s[14],
                        "source": "opensky-network.org",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    } for s in states if s[6] is not None and s[5] is not None]
                elif resp.status == 429:
                    print("⚠️  OpenSky rate limit (4000/día)")
                    return []
        except Exception as e:
            print(f"⚠️  Error OpenSky: {e}")
        return []
