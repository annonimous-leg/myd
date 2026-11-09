"""CelesTrak - TLEs de satélites."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp


class CelesTrakClient:
    """Cliente para CelesTrak TLEs públicos.

    El cliente es perezoso: la sesión HTTP se crea solo al primer request,
    para evitar side effects durante import/arranque y mantener el ciclo de
    vida controlado por el runtime de Tezcatlipoca.
    """

    def __init__(self, base_url: str = "https://celestrak.org/NORAD/elements"):
        self.base_url = base_url.rstrip("/")
        self.http: Optional[aiohttp.ClientSession] = None

    async def _session(self) -> aiohttp.ClientSession:
        if self.http is None or self.http.closed:
            timeout = aiohttp.ClientTimeout(total=20, connect=5)
            self.http = aiohttp.ClientSession(timeout=timeout, raise_for_status=False)
        return self.http

    async def close(self) -> None:
        if self.http and not self.http.closed:
            await self.http.close()
        self.http = None

    async def get_tles(self, group: str = "starlink") -> List[Dict[str, Any]]:
        """Obtiene TLEs de un grupo público de CelesTrak."""
        session = await self._session()
        try:
            url = f"{self.base_url}/gp.php"
            params = {"GROUP": group, "FORMAT": "tle"}
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return []
                text = await resp.text()
        except Exception as exc:
            print(f"⚠️  Error CelesTrak: {exc}")
            return []

        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        satellites: List[Dict[str, Any]] = []

        # CelesTrak TLE text format: 3-line blocks => name / line1 / line2
        for i in range(0, len(lines) - 2, 3):
            name, line1, line2 = lines[i], lines[i + 1], lines[i + 2]
            if not line1.startswith("1 ") or not line2.startswith("2 "):
                # Skip malformed blocks instead of poisoning the feed.
                continue
            satellites.append(
                {
                    "name": name,
                    "tle_line1": line1,
                    "tle_line2": line2,
                    "group": group,
                    "source": "celestrak.org",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

        return satellites

    async def get_visual(self) -> List[Dict[str, Any]]:
        """Satélites visibles a simple vista."""
        return await self.get_tles("visual")

    async def get_weather_satellites(self) -> List[Dict[str, Any]]:
        """Satélites meteorológicos."""
        return await self.get_tles("weather")
