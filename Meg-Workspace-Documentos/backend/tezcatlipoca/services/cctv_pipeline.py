"""CCTV Pipeline - Fetch de cámaras públicas."""
import aiohttp
from typing import Dict, List, Any
from datetime import datetime, timezone


class CCTVPipeline:
    def __init__(self):
        self.http = aiohttp.ClientSession()
        self.cameras: List[Dict] = []

    async def close(self):
        if self.http and not self.http.closed:
            await self.http.close()

    async def fetch_all(self) -> List[Dict]:
        cameras = []
        cameras.extend(await self._fetch_insecam())
        self.cameras = cameras
        return cameras

    async def _fetch_insecam(self) -> List[Dict]:
        try:
            url = "https://www.insecam.org/en/jsoncountries/"
            async with self.http.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    cameras = []
                    for country_code, info in data.get("countries", {}).items():
                        cameras.append({
                            "id": f"insecam_{country_code}",
                            "country": country_code,
                            "country_name": info.get("country", "Unknown"),
                            "count": info.get("count", 0),
                            "latitude": info.get("lat", 0),
                            "longitude": info.get("lon", 0),
                            "source": "insecam.org",
                            "type": "public_cctv",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "url": f"https://www.insecam.org/en/bycountry/{country_code}"
                        })
                    return cameras
        except Exception as e:
            print(f"⚠️  Error fetch Insecam: {e}")
        return []

    def get_cameras_by_country(self, country_code: str) -> List[Dict]:
        return [c for c in self.cameras if c.get("country") == country_code.upper()]

    def get_all_cameras(self) -> List[Dict]:
        return self.cameras
