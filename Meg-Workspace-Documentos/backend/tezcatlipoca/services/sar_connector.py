"""SAR Connector - ASF, OPERA, Copernicus."""
import os
import aiohttp
from typing import Dict, List, Any
from datetime import datetime, timezone


class SARConnector:
    def __init__(self):
        self.http = aiohttp.ClientSession()
        self.asf_user = os.getenv("ASF_USERNAME", "")
        self.asf_pass = os.getenv("ASF_PASSWORD", "")

    async def close(self):
        if self.http and not self.http.closed:
            await self.http.close()

    async def search_asf(self, bbox: List[float], start_date: str, end_date: str,
                         platform: str = "SENTINEL-1") -> List[Dict]:
        try:
            url = "https://api.daac.asf.alaska.edu/services/search/param"
            params = {
                "bbox": ",".join(map(str, bbox)),
                "start": start_date, "end": end_date,
                "platform": platform, "output": "json"
            }
            async with self.http.get(url, params=params,
                                     timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return [{
                        "granule": r.get("granuleName", ""),
                        "platform": r.get("platform", ""),
                        "date": r.get("sceneDate", ""),
                        "bbox": r.get("bbox", []),
                        "url": r.get("url", ""),
                        "source": "asf.alaska.edu",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    } for r in data.get("results", [])[:50]]
        except Exception as e:
            print(f"⚠️  Error ASF: {e}")
        return []

    async def get_opera_disp(self, bbox: List[float]) -> Dict:
        try:
            url = "https://opera-disp.s3.us-west-2.amazonaws.com/docs/catalog.json"
            async with self.http.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    return {
                        "catalog": await resp.json(),
                        "bbox": bbox,
                        "source": "opera-disp",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
        except Exception as e:
            print(f"⚠️  Error OPERA: {e}")
        return {}

    async def get_copernicus_egms(self, point: List[float]) -> Dict:
        try:
            url = "https://egms.land.copernicus.eu/rest_api"
            params = {"lat": point[0], "lon": point[1]}
            async with self.http.get(url, params=params,
                                     timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    return {
                        "data": await resp.json(),
                        "point": point,
                        "source": "copernicus-egms",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
        except Exception as e:
            print(f"⚠️  Error EGMS: {e}")
        return {}
