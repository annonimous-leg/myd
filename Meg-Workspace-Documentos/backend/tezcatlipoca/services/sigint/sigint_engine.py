"""SIGINT Engine - KiwiSDR y OpenMHZ."""
import aiohttp
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone


class SIGINTEngine:
    def __init__(self):
        self._http: Optional[aiohttp.ClientSession] = None
        self.kiwisdr_list: List[Dict] = []
        self.openmhz_systems: List[Dict] = []

    @property
    def http(self) -> aiohttp.ClientSession:
        if self._http is None or self._http.closed:
            self._http = aiohttp.ClientSession()
        return self._http

    async def close(self):
        if self._http and not self._http.closed:
            await self._http.close()

    async def fetch_kiwisdr_list(self) -> List[Dict]:
        try:
            url = "http://kiwisdr.com/public/json/kiwisdr_com.json"
            async with self.http.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    receivers = []
                    for rx in data.get("channels", [])[:100]:
                        receivers.append({
                            "id": rx.get("id", ""),
                            "name": rx.get("name", "Unknown"),
                            "location": rx.get("location", "Unknown"),
                            "latitude": rx.get("lat", 0),
                            "longitude": rx.get("lon", 0),
                            "frequency_khz": rx.get("freq", 0),
                            "url": rx.get("url", ""),
                            "source": "kiwisdr.com",
                            "type": "kiwisdr",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        })
                    self.kiwisdr_list = receivers
                    return receivers
        except Exception as e:
            print(f"⚠️  Error KiwiSDR: {e}")
        return []

    async def fetch_openmhz_systems(self) -> List[Dict]:
        try:
            url = "https://api.openmhz.com/systems"
            async with self.http.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    systems = []
                    for sys in data.get("systems", [])[:100]:
                        systems.append({
                            "id": sys.get("shortName", ""),
                            "name": sys.get("name", "Unknown"),
                            "type": sys.get("systemType", "Unknown"),
                            "latitude": sys.get("lat", 0),
                            "longitude": sys.get("lng", 0),
                            "county": sys.get("county", ""),
                            "state": sys.get("state", ""),
                            "source": "openmhz.com",
                            "type": "openmhz",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        })
                    self.openmhz_systems = systems
                    return systems
        except Exception as e:
            print(f"⚠️  Error OpenMHZ: {e}")
        return []

    def get_receivers_by_bbox(self, lat_min: float, lat_max: float,
                              lon_min: float, lon_max: float) -> List[Dict]:
        all_rx = self.kiwisdr_list + self.openmhz_systems
        return [
            rx for rx in all_rx
            if lat_min <= rx.get("latitude", 0) <= lat_max
            and lon_min <= rx.get("longitude", 0) <= lon_max
        ]

    def get_all_receivers(self) -> List[Dict]:
        return self.kiwisdr_list + self.openmhz_systems
