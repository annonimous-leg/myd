"""GTFS Mobility Database - Feeds de transporte público global."""
import aiohttp
from typing import Dict, List, Any
from datetime import datetime, timezone


class GTFSMobilityClient:
    """Cliente para Mobility Database (GTFS feeds)."""

    def __init__(self):
        self.base_url = "https://api.mobilitydatabase.org/v1"
        self.http = aiohttp.ClientSession()

    async def close(self):
        if self.http and not self.http.closed:
            await self.http.close()

    async def get_feeds(self, country: str = "", limit: int = 50) -> List[Dict]:
        """Obtener feeds GTFS disponibles."""
        try:
            url = f"{self.base_url}/gtfs_feeds"
            params = {"limit": limit}
            if country:
                params["country_code"] = country
            async with self.http.get(url, params=params,
                                     timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    feeds = data.get("feeds", []) if isinstance(data, dict) else data
                    return [{
                        "id": f.get("id", ""),
                        "name": f.get("name", ""),
                        "country": f.get("country_code", ""),
                        "provider": f.get("provider", ""),
                        "status": f.get("status", ""),
                        "source": "mobilitydatabase.org",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    } for f in feeds[:limit]]
        except Exception as e:
            print(f"⚠️  Error GTFS feeds: {e}")
        return []

    async def get_feed_data(self, feed_id: str) -> Dict[str, Any]:
        """Obtener datos de un feed específico."""
        try:
            url = f"{self.base_url}/gtfs_feeds/{feed_id}"
            async with self.http.get(url,
                                     timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            print(f"⚠️  Error GTFS feed data: {e}")
        return {"error": "Failed to fetch feed data"}
