"""Routes on an operator-managed OSRM server, never a public demo server."""
from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx


class OSRMClient:
    def __init__(self, base_url: str | None = None, http: httpx.AsyncClient | None = None):
        self.base_url = (base_url if base_url is not None else os.getenv("TEZCATLIPOCA_OSRM_URL", "")).rstrip("/")
        if self.base_url:
            url = urlsplit(self.base_url)
            if (url.scheme not in ("http", "https") or not url.hostname
                    or url.username or url.password or url.query or url.fragment
                    or url.path not in ("", "/")):
                raise ValueError("Invalid OSRM base URL; configure a dedicated operator-managed host")
        self.http = http or httpx.AsyncClient(timeout=15, follow_redirects=False)
        self._owns_http = http is None

    async def close(self):
        if self._owns_http:
            await self.http.aclose()

    async def get_route(self, from_lat, from_lon, to_lat, to_lon, vehicle="car") -> dict:
        if not self.base_url:
            return {"status": "config_required", "error": "Configure TEZCATLIPOCA_OSRM_URL"}
        if vehicle != "car":
            return {"status": "unsupported_profile", "error": "OSRM is configured for the driving profile only"}
        coords = (from_lat, from_lon, to_lat, to_lon)
        if (not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                    and math.isfinite(v) for v in coords)
                or not all(-90 <= y <= 90 for y in (from_lat, to_lat))
                or not all(-180 <= x <= 180 for x in (from_lon, to_lon))):
            return {"status": "invalid_coordinates", "error": "Invalid route coordinates"}
        path = f"/route/v1/driving/{from_lon:.6f},{from_lat:.6f};{to_lon:.6f},{to_lat:.6f}"
        try:
            response = await self.http.get(
                self.base_url + path,
                params={"overview": "full", "geometries": "geojson", "steps": "false"},
            )
            response.raise_for_status()
            data = response.json()
            if data.get("code") != "Ok" or not data.get("routes"):
                return {"status": "unavailable", "error": "No OSRM route", "provider_code": data.get("code")}
            route = data["routes"][0]
            if not isinstance(route.get("distance"), (int, float)) or not isinstance(route.get("duration"), (int, float)):
                raise ValueError("Incomplete OSRM route")
            return {
                "status": "available", "distance_m": route["distance"],
                "time_ms": round(route["duration"] * 1000),
                "points": route.get("geometry", {}).get("coordinates", []),
                "instructions": [], "vehicle": vehicle,
                "source": "osrm_self_hosted", "road_data_license": "ODbL-1.0",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            return {"status": "unavailable", "error": "OSRM backend unavailable"}
