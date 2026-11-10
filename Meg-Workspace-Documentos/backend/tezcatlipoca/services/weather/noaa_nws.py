"""Site-specific NOAA/NWS forecast. Coverage is chiefly United States."""
from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx


class NOAAWeatherClient:
    def __init__(self, http: httpx.AsyncClient | None = None):
        self.http = http or httpx.AsyncClient(
            timeout=15, follow_redirects=False,
            headers={"User-Agent": os.getenv("TEZCATLIPOCA_NWS_USER_AGENT", "Megalodon-Tezcatlipoca (https://github.com/annonimous-leg/myd)"),
                     "Accept": "application/geo+json"},
        )
        self._owns_http = http is None

    async def close(self):
        if self._owns_http:
            await self.http.aclose()

    async def forecast(self, lat: float, lon: float) -> dict:
        if (not isinstance(lat, (float, int)) or not isinstance(lon, (float, int))
                or isinstance(lat, bool) or isinstance(lon, bool)
                or not math.isfinite(lat) or not math.isfinite(lon)
                or not -90 <= lat <= 90 or not -180 <= lon <= 180):
            return {"status": "invalid_coordinates", "source": "noaa_nws", "periods": []}
        try:
            point = await self.http.get(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}")
            if point.status_code in (400, 404, 422):
                return {"status": "out_of_coverage", "source": "noaa_nws", "periods": []}
            point.raise_for_status()
            target = point.json()["properties"]["forecast"]
            parts = urlsplit(target)
            # A provider response cannot redirect Megalodon into internal URLs.
            if parts.scheme != "https" or parts.hostname != "api.weather.gov" or parts.username or parts.password:
                raise ValueError("Untrusted NOAA forecast URL")
            response = await self.http.get(target)
            response.raise_for_status()
            periods = response.json()["properties"]["periods"]
            if not isinstance(periods, list):
                raise ValueError("Invalid NOAA forecast")
            return {
                "status": "available", "source": "noaa_nws",
                "license": "US federal public data",
                "lat": lat, "lon": lon, "periods": periods[:14],
                "received_at": datetime.now(timezone.utc).isoformat(),
                "coverage": "NWS supported territories only",
            }
        except (httpx.HTTPError, KeyError, ValueError, TypeError):
            return {"status": "unavailable", "source": "noaa_nws", "periods": []}
