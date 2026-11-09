"""Deutsche Bahn Trains - Datos en tiempo real de trenes alemanes."""
import aiohttp
from typing import Dict, List, Any
from datetime import datetime, timezone


class DBTrainClient:
    """Cliente para API de Deutsche Bahn (v5.transport.rest)."""

    def __init__(self):
        self.base_url = "https://v5.db.transport.rest"
        self.http = aiohttp.ClientSession()

    async def close(self):
        if self.http and not self.http.closed:
            await self.http.close()

    async def get_stations(self, query: str, limit: int = 10) -> List[Dict]:
        """Buscar estaciones por nombre."""
        try:
            url = f"{self.base_url}/locations"
            params = {"query": query, "results": limit}
            async with self.http.get(url, params=params,
                                     timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return [{
                        "id": s.get("id", ""),
                        "name": s.get("name", ""),
                        "latitude": s.get("location", {}).get("latitude"),
                        "longitude": s.get("location", {}).get("longitude"),
                        "source": "db.transport.rest",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    } for s in data]
        except Exception as e:
            print(f"⚠️  Error DB stations: {e}")
        return []

    async def get_departures(self, station_id: str, duration: int = 60) -> List[Dict]:
        """Obtener salidas de una estación."""
        try:
            url = f"{self.base_url}/stations/{station_id}/departures"
            params = {"duration": duration}
            async with self.http.get(url, params=params,
                                     timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    departures = data.get("departures", []) if isinstance(data, dict) else data
                    return [{
                        "trip_id": d.get("tripId", ""),
                        "line": d.get("line", {}).get("name", "Unknown"),
                        "direction": d.get("direction", ""),
                        "platform": d.get("platform", ""),
                        "when": d.get("when", ""),
                        "delay": d.get("delay", 0),
                        "cancelled": d.get("cancelled", False),
                        "source": "db.transport.rest",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    } for d in departures[:50]]
        except Exception as e:
            print(f"⚠️  Error DB departures: {e}")
        return []

    async def get_journey(self, from_id: str, to_id: str) -> Dict[str, Any]:
        """Calcular viaje entre dos estaciones."""
        try:
            url = f"{self.base_url}/journeys"
            params = {"from": from_id, "to": to_id, "results": 5}
            async with self.http.get(url, params=params,
                                     timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    journeys = data.get("journeys", []) if isinstance(data, dict) else []
                    return {
                        "journeys": [{
                            "legs": len(j.get("legs", [])),
                            "duration": sum(l.get("duration", 0) for l in j.get("legs", [])),
                            "price": j.get("price", {}).get("amount", "N/A") if j.get("price") else "N/A"
                        } for j in journeys[:5]],
                        "source": "db.transport.rest",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
        except Exception as e:
            print(f"⚠️  Error DB journey: {e}")
        return {"error": "Failed to fetch journey"}
