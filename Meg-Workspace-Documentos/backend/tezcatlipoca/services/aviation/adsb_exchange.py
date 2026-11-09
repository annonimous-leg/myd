"""ADS-B Exchange - Datos de vuelo para detección GPSJam."""
import os
import aiohttp
from typing import Dict, List, Any
from datetime import datetime, timedelta, timezone


class ADSBExchangeClient:
    """Cliente para ADS-B Exchange API (requiere API key)."""

    def __init__(self):
        self.api_key = os.getenv("ADSBEXCHANGE_API_KEY", "")
        self.base_url = "https://api.adsbexchange.com/api/v2"
        self.http = aiohttp.ClientSession()
        self.last_request_status = "not_requested"
        self.last_success = None

    async def close(self):
        if self.http and not self.http.closed:
            await self.http.close()

    async def get_aircraft_in_bbox(self, lat_min: float, lat_max: float,
                                    lon_min: float, lon_max: float) -> List[Dict]:
        """Obtener aeronaves en bounding box."""
        if not self.api_key:
            self.last_request_status = "config_required"
            return []

        self.last_request_status = "unavailable"
        try:
            url = f"{self.base_url}/lat/{(lat_min + lat_max) / 2}/lon/{(lon_min + lon_max) / 2}/dist/250"
            headers = {"api-auth": self.api_key}
            async with self.http.get(url, headers=headers,
                                     timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if not isinstance(data, dict) or not isinstance(data.get("ac"), list):
                        raise ValueError("Invalid ADS-B provider response")
                    aircraft = data["ac"]
                    received = datetime.now(timezone.utc)
                    self.last_request_status = "available"
                    self.last_success = received.isoformat()
                    return [{
                        "hex": a.get("hex", ""),
                        "flight": a.get("flight", ""),
                        "latitude": a.get("lat"),
                        "longitude": a.get("lon"),
                        "altitude": a.get("alt_baro", 0),
                        "speed": a.get("gs", 0),
                        "heading": a.get("track", 0),
                        "type": a.get("t", ""),
                        "source": "adsbexchange.com",
                        "timestamp": (received - timedelta(seconds=a["seen_pos"])).isoformat()
                        if isinstance(a.get("seen_pos"), (int, float)) and 0 <= a["seen_pos"] <= 86400 else None,
                        "received_at": received.isoformat(),
                    } for a in aircraft if isinstance(a, dict)
                       and isinstance(a.get("lat"), (int, float))
                       and isinstance(a.get("lon"), (int, float))
                       and lat_min <= a["lat"] <= lat_max and lon_min <= a["lon"] <= lon_max][:200]
        except Exception as e:
            self.last_request_status = "unavailable"
            print(f"ADS-B request failed ({type(e).__name__})")
        return []

    async def get_aircraft_by_hex(self, hex_id: str) -> Dict[str, Any]:
        """Obtener aeronave por ID hexadecimal."""
        if not self.api_key:
            return {"error": "ADSBEXCHANGE_API_KEY not configured"}

        try:
            url = f"{self.base_url}/hex/{hex_id}"
            headers = {"api-auth": self.api_key}
            async with self.http.get(url, headers=headers,
                                     timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            print(f"⚠️  Error ADS-B hex: {e}")
        return {"error": "Failed to fetch aircraft"}

    def detect_gps_jam(self, aircraft_list: List[Dict]) -> List[Dict]:
        """Detectar posibles interferencias GPS basado en anomalías."""
        suspicious = []
        for ac in aircraft_list:
            # Detección simple: aeronaves sin posición válida o con altitud inconsistente
            lat = ac.get("latitude")
            lon = ac.get("longitude")
            alt = ac.get("altitude", 0)

            if lat is None or lon is None or abs(lat) > 90 or abs(lon) > 180:
                suspicious.append({
                    "hex": ac.get("hex", ""),
                    "flight": ac.get("flight", ""),
                    "reason": "invalid_position",
                    "last_known": {"lat": lat, "lon": lon, "alt": alt},
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            elif alt > 50000 or alt < -1000:  # Altitud imposible
                suspicious.append({
                    "hex": ac.get("hex", ""),
                    "flight": ac.get("flight", ""),
                    "reason": "altitude_anomaly",
                    "altitude": alt,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })

        return suspicious
