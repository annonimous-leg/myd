"""NASA Earthdata - Acceso a datos SAR de NASA/OPERA."""
import os
import aiohttp
from typing import Dict, List, Any
from datetime import datetime, timezone


class NASAEarthdataClient:
    """Cliente para NASA Earthdata (requiere registro gratuito)."""

    def __init__(self):
        self.username = os.getenv("NASA_ED_USERNAME", "")
        self.password = os.getenv("NASA_ED_PASSWORD", "")
        self.base_url = "https://cmr.earthdata.nasa.gov/search"
        self.http = aiohttp.ClientSession()
        self.token = None

    async def close(self):
        if self.http and not self.http.closed:
            await self.http.close()

    async def _authenticate(self):
        """Autenticar con NASA Earthdata."""
        if not self.username or not self.password:
            return False
        # NASA usa Basic Auth o token bearer
        self.token = f"{self.username}:{self.password}"
        return True

    async def search_granules(self, collection: str = "C1442068286-ASF",
                               bbox: List[float] = None,
                               start_date: str = None,
                               end_date: str = None,
                               limit: int = 50) -> List[Dict]:
        """Buscar granulos SAR por colección y bounding box."""
        if not await self._authenticate():
            return [{"error": "NASA_ED_USERNAME/PASSWORD not configured"}]

        try:
            url = f"{self.base_url}/granules.json"
            params = {
                "collection_concept_id": collection,
                "page_size": limit,
                "sort_key": "-start_date"
            }
            if bbox:
                params["bounding_box"] = ",".join(map(str, bbox))
            if start_date:
                params["temporal"] = f"{start_date},{end_date or ''}"

            auth = aiohttp.BasicAuth(self.username, self.password)
            async with self.http.get(url, params=params, auth=auth,
                                     timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    granules = data.get("feed", {}).get("entry", [])
                    return [{
                        "id": g.get("id", ""),
                        "title": g.get("title", ""),
                        "time_start": g.get("time_start", ""),
                        "time_end": g.get("time_end", ""),
                        "bbox": g.get("boxes", []),
                        "links": [l.get("href", "") for l in g.get("links", []) if l.get("href", "").endswith(".zip") or l.get("href", "").endswith(".h5")],
                        "source": "earthdata.nasa.gov",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    } for g in granules]
                elif resp.status == 401:
                    return [{"error": "Invalid NASA Earthdata credentials"}]
        except Exception as e:
            print(f"⚠️  Error NASA Earthdata: {e}")
        return []

    async def get_collections(self, keyword: str = "SAR") -> List[Dict]:
        """Buscar colecciones disponibles."""
        if not await self._authenticate():
            return [{"error": "NASA_ED_USERNAME/PASSWORD not configured"}]

        try:
            url = f"{self.base_url}/collections.json"
            params = {"keyword": keyword, "page_size": 20}
            auth = aiohttp.BasicAuth(self.username, self.password)
            async with self.http.get(url, params=params, auth=auth,
                                     timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    collections = data.get("feed", {}).get("entry", [])
                    return [{
                        "id": c.get("id", ""),
                        "title": c.get("title", ""),
                        "summary": c.get("summary", ""),
                        "source": "earthdata.nasa.gov"
                    } for c in collections]
        except Exception as e:
            print(f"⚠️  Error NASA collections: {e}")
        return []
