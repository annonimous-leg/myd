"""Copernicus Open Access Hub (SciHub) - Datos Sentinel-1."""
import os
import aiohttp
from typing import Dict, List, Any
from datetime import datetime, timezone


class CopernicusSciHubClient:
    """Cliente para Copernicus Open Access Hub (requiere cuenta gratuita ESA)."""

    def __init__(self):
        self.username = os.getenv("COPERNICUS_USERNAME", "")
        self.password = os.getenv("COPERNICUS_PASSWORD", "")
        self.base_url = "https://scihub.copernicus.eu/dhus"
        self.http = aiohttp.ClientSession()

    async def close(self):
        if self.http and not self.http.closed:
            await self.http.close()

    async def search_sentinel1(self, bbox: List[float] = None,
                                start_date: str = None,
                                end_date: str = None,
                                product_type: str = "GRD",
                                limit: int = 50) -> List[Dict]:
        """Buscar productos Sentinel-1."""
        if not self.username or not self.password:
            return [{"error": "COPERNICUS_USERNAME/PASSWORD not configured"}]

        try:
            url = f"{self.base_url}/search"
            params = {
                "q": f"platformname:Sentinel-1 AND producttype:{product_type}",
                "rows": limit,
                "start": 0,
                "sortedby": "ingestiondate",
                "order": "desc"
            }
            if bbox:
                params["q"] += f' AND footprint:"Intersects(POLYGON(({bbox[0]} {bbox[1]},{bbox[2]} {bbox[1]},{bbox[2]} {bbox[3]},{bbox[0]} {bbox[3]},{bbox[0]} {bbox[1]})))"'
            if start_date and end_date:
                params["q"] += f" AND beginPosition:[{start_date} TO {end_date}]"

            auth = aiohttp.BasicAuth(self.username, self.password)
            async with self.http.get(url, params=params, auth=auth,
                                     timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 200:
                    import xml.etree.ElementTree as ET
                    text = await resp.text()
                    root = ET.fromstring(text)

                    # Namespace de OpenSearch
                    ns = {"opensearch": "http://a9.com/-/spec/opensearch/1.1/",
                          "atom": "http://www.w3.org/2005/Atom",
                          "dc": "http://purl.org/dc/elements/1.1/"}

                    entries = root.findall("atom:entry", ns)
                    results = []
                    for entry in entries:
                        title = entry.find("atom:title", ns)
                        summary = entry.find("atom:summary", ns)
                        date = entry.find("dc:date", ns)

                        # Buscar link de descarga
                        links = entry.findall("atom:link", ns)
                        download_link = None
                        for link in links:
                            if link.get("rel") == "enclosure":
                                download_link = link.get("href")
                                break

                        results.append({
                            "title": title.text if title is not None else "",
                            "summary": summary.text if summary is not None else "",
                            "date": date.text if date is not None else "",
                            "download_url": download_link,
                            "source": "scihub.copernicus.eu",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        })
                    return results
                elif resp.status == 401:
                    return [{"error": "Invalid Copernicus credentials"}]
        except Exception as e:
            print(f"⚠️  Error Copernicus SciHub: {e}")
        return []

    async def get_product_odata(self, product_id: str) -> Dict[str, Any]:
        """Obtener metadatos de un producto via OData."""
        if not self.username or not self.password:
            return {"error": "COPERNICUS_USERNAME/PASSWORD not configured"}

        try:
            url = f"{self.base_url}/odata/v1/Products('{product_id}')"
            auth = aiohttp.BasicAuth(self.username, self.password)
            async with self.http.get(url, auth=auth,
                                     timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            print(f"⚠️  Error Copernicus OData: {e}")
        return {"error": "Failed to fetch product metadata"}
