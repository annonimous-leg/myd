"""Sentinel-1 public catalogue via Copernicus Data Space OData (not retired SciHub).

Kept the historical class name for existing router compatibility. This client
searches metadata only; it does not pretend to download/process SAR rasters.
Only Sentinel data are selected (the portal has differently licensed assets).
"""
from __future__ import annotations

import math
from datetime import date, datetime, timezone
from uuid import UUID

import httpx


class CopernicusSciHubClient:
    BASE_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"

    def __init__(self, http: httpx.AsyncClient | None = None):
        self.http = http or httpx.AsyncClient(timeout=25, follow_redirects=False)
        self._owns_http = http is None

    async def close(self):
        if self._owns_http:
            await self.http.aclose()

    @staticmethod
    def _date(value: str | None) -> str | None:
        if not value:
            return None
        parsed = date.fromisoformat(value[:10])
        if len(value) != 10:
            raise ValueError("Expected YYYY-MM-DD")
        return parsed.isoformat() + "T00:00:00.000Z"

    async def search_sentinel1(
        self, bbox: list[float] | None = None, start_date: str | None = None,
        end_date: str | None = None, product_type: str = "GRD", limit: int = 50,
    ) -> list[dict]:
        if product_type not in ("GRD", "SLC", "RAW", "OCN"):
            return [{"error": "Unsupported Sentinel-1 product type"}]
        if not isinstance(limit, int) or not 1 <= limit <= 100:
            return [{"error": "Limit must be between 1 and 100"}]
        try:
            filters = ["Collection/Name eq 'SENTINEL-1'", f"contains(Name,'{product_type}')"]
            start, end = self._date(start_date), self._date(end_date)
            if start:
                filters.append(f"ContentDate/Start ge {start}")
            if end:
                filters.append(f"ContentDate/Start lt {end}")
            if bbox is not None:
                if (len(bbox) != 4 or not all(isinstance(v, (int, float)) and
                        not isinstance(v, bool) and math.isfinite(v) for v in bbox)):
                    raise ValueError("Invalid bbox")
                west, south, east, north = bbox
                if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
                    raise ValueError("Invalid bbox bounds")
                coords = f"{west} {south},{east} {south},{east} {north},{west} {north},{west} {south}"
                filters.append("OData.CSC.Intersects(area=geography'SRID=4326;POLYGON((" + coords + "))')")
            response = await self.http.get(self.BASE_URL, params={
                "$filter": " and ".join(filters),
                "$orderby": "ContentDate/Start desc",
                "$top": limit,
            })
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("value"), list):
                raise ValueError("Unexpected CDSE catalogue payload")
            return [{
                "id": item.get("Id"),
                "title": item.get("Name"),
                "date": (item.get("ContentDate") or {}).get("Start"),
                "bbox": item.get("GeoFootprint"),
                "url": self.BASE_URL + "(" + str(item.get("Id")) + ")",
                "source": "copernicus_data_space",
                "license": "Copernicus Sentinel Data Legal Notice",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            } for item in payload["value"] if isinstance(item, dict) and item.get("Id")]
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            return [{"error": "CDSE catalogue unavailable or invalid query", "source": "copernicus_data_space"}]

    async def get_product_odata(self, product_id: str) -> dict:
        try:
            normalized = str(UUID(product_id))
            response = await self.http.get(self.BASE_URL + "(" + normalized + ")")
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("Id") != normalized:
                raise ValueError("Invalid CDSE response")
            return {"status": "available", "source": "copernicus_data_space", "product": payload}
        except (httpx.HTTPError, ValueError, TypeError):
            return {"status": "unavailable", "source": "copernicus_data_space"}
