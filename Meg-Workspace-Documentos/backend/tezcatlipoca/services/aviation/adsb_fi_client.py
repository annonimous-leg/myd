"""adsb.fi - Vuelos militares y civiles sin autenticación."""
import aiohttp
from typing import Dict, List, Any
from datetime import datetime, timezone


class ADSBfiClient:
    """Cliente para adsb.fi API (sin auth, datos crudos)."""

    def __init__(self):
        self.base_url = "https://api.adsb.fi/v2"
        self.http = aiohttp.ClientSession()

    async def close(self):
        if self.http and not self.http.closed:
            await self.http.close()

    async def get_aircraft_near(self, lat: float, lon: float, dist: int = 250) -> List[Dict]:
        """Obtener aeronaves cercanas a un punto."""
        try:
            url = f"{self.base_url}/lat/{lat}/lon/{lon}/dist/{dist}"
            async with self.http.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    aircraft = data.get("aircraft", [])
                    return [{
                        "hex": a.get("hex", ""),
                        "flight": a.get("flight", ""),
                        "latitude": a.get("lat"),
                        "longitude": a.get("lon"),
                        "altitude": a.get("alt_baro", 0),
                        "speed": a.get("gs", 0),
                        "heading": a.get("track", 0),
                        "type": a.get("t", ""),
                        "category": a.get("category", ""),
                        "source": "adsb.fi",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    } for a in aircraft if a.get("lat") is not None and a.get("lon") is not None]
                elif resp.status == 429:
                    print("⚠️  adsb.fi rate limit (1/seg)")
                    return []
        except Exception as e:
            print(f"⚠️  Error adsb.fi: {e}")
        return []
