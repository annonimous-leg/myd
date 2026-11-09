"""AVWX Engine - METARs, TAFs y NOTAMs de múltiples fuentes."""
import os
import aiohttp
from typing import Dict, List, Any
from datetime import datetime, timezone


class AVWXClient:
    """Cliente para AVWX API (requiere API key)."""

    def __init__(self):
        self.api_key = os.getenv("AVWX_API_KEY", "")
        self.base_url = "https://avwx.rest/api"
        self.http = aiohttp.ClientSession()

    async def close(self):
        if self.http and not self.http.closed:
            await self.http.close()

    async def get_metar(self, icao: str) -> Dict[str, Any]:
        """Obtener METAR por código ICAO."""
        if not self.api_key:
            return {"error": "AVWX_API_KEY not configured"}

        try:
            url = f"{self.base_url}/metar/{icao}"
            headers = {"Authorization": self.api_key}
            async with self.http.get(url, headers=headers,
                                     timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "icao": icao,
                        "raw": data.get("raw", ""),
                        "wind": data.get("wind_speed", {}),
                        "visibility": data.get("visibility", {}),
                        "temperature": data.get("temperature", {}),
                        "altimeter": data.get("altimeter", {}),
                        "flight_rules": data.get("flight_rules", ""),
                        "source": "avwx.rest",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
        except Exception as e:
            print(f"⚠️  Error AVWX METAR: {e}")
        return {"error": "Failed to fetch METAR"}

    async def get_taf(self, icao: str) -> Dict[str, Any]:
        """Obtener TAF por código ICAO."""
        if not self.api_key:
            return {"error": "AVWX_API_KEY not configured"}

        try:
            url = f"{self.base_url}/taf/{icao}"
            headers = {"Authorization": self.api_key}
            async with self.http.get(url, headers=headers,
                                     timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "icao": icao,
                        "raw": data.get("raw", ""),
                        "forecast": data.get("forecast", []),
                        "source": "avwx.rest",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
        except Exception as e:
            print(f"⚠️  Error AVWX TAF: {e}")
        return {"error": "Failed to fetch TAF"}

    async def get_station(self, icao: str) -> Dict[str, Any]:
        """Obtener información de estación."""
        if not self.api_key:
            return {"error": "AVWX_API_KEY not configured"}

        try:
            url = f"{self.base_url}/station/{icao}"
            headers = {"Authorization": self.api_key}
            async with self.http.get(url, headers=headers,
                                     timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            print(f"⚠️  Error AVWX station: {e}")
        return {"error": "Failed to fetch station"}
