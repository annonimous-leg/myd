"""ADSB.lol open-data adapter. ODbL 1.0; no global coverage is implied."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import httpx


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 3440.065 * 2 * math.asin(min(1, math.sqrt(a)))


class ADSBLoLClient:
    """Geographic ADS-B lookup limited to one 250 NM circle per request.

    Requests covering larger viewports are deliberately not represented as a
    worldwide dataset. To expand coverage, implement a quota-aware tiler.
    """

    def __init__(self, http: httpx.AsyncClient | None = None):
        self.http = http or httpx.AsyncClient(timeout=15, follow_redirects=False)
        self._owns_http = http is None
        self.last_request_status = "not_requested"
        self.last_success: str | None = None
        self.coverage = "single_circle_max_250_nm"
        self.license = "ODbL-1.0"

    async def close(self) -> None:
        if self._owns_http:
            await self.http.aclose()

    async def get_aircraft_in_bbox(
        self, lat_min: float, lat_max: float, lon_min: float, lon_max: float
    ) -> list[dict]:
        vals = (lat_min, lat_max, lon_min, lon_max)
        if (not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                    and math.isfinite(v) for v in vals)
                or lat_min < -90 or lat_max > 90 or lon_min < -180 or lon_max > 180
                or lat_min > lat_max or lon_min > lon_max):
            raise ValueError("Invalid geographic bounding box")
        lat = (lat_min + lat_max) / 2
        lon = (lon_min + lon_max) / 2
        radius = max(
            _haversine_nm(lat, lon, y, x)
            for y in (lat_min, lat_max) for x in (lon_min, lon_max)
        )
        if radius > 250:
            self.last_request_status = "coverage_limited"
            return []
        radius_nm = max(1, math.ceil(radius))
        self.last_request_status = "unavailable"
        try:
            resp = await self.http.get(
                f"https://api.adsb.lol/v2/lat/{lat:.5f}/lon/{lon:.5f}/dist/{radius_nm}"
            )
            resp.raise_for_status()
            body = resp.json()
            if not isinstance(body, dict) or not isinstance(body.get("ac"), list):
                raise ValueError("Unexpected ADSB.lol payload")
            now = datetime.now(timezone.utc)
            rows = []
            for ac in body["ac"]:
                if not isinstance(ac, dict):
                    continue
                y, x = ac.get("lat"), ac.get("lon")
                if (not isinstance(y, (float, int)) or isinstance(y, bool)
                        or not isinstance(x, (float, int)) or isinstance(x, bool)
                        or not math.isfinite(y) or not math.isfinite(x)
                        or not lat_min <= y <= lat_max or not lon_min <= x <= lon_max):
                    continue
                age = ac.get("seen_pos")
                observed = (now - timedelta(seconds=age)).isoformat() if (
                    isinstance(age, (float, int)) and not isinstance(age, bool)
                    and math.isfinite(age) and 0 <= age <= 120
                ) else None
                # Do not show un-timestamped or old positions as live.
                if observed is None:
                    continue
                rows.append({
                    "hex": ac.get("hex") or "",
                    "flight": (ac.get("flight") or "").strip(),
                    "latitude": y, "longitude": x,
                    "altitude": ac.get("alt_baro") if isinstance(ac.get("alt_baro"), (int, float)) else None,
                    "speed": ac.get("gs"),
                    "heading": ac.get("track"),
                    "type": ac.get("t"),
                    "timestamp": observed, "received_at": now.isoformat(),
                    "source": "adsb.lol", "altitude_unit": "ft", "speed_unit": "kn",
                })
            self.last_request_status = "available"
            self.last_success = now.isoformat()
            return rows[:500]
        except (httpx.HTTPError, ValueError, TypeError):
            self.last_request_status = "unavailable"
            return []
