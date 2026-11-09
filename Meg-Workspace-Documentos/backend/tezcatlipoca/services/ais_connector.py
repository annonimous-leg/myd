"""AIS Connector - Conexión real a aisstream.io vía WebSocket."""
import os
import json
import asyncio
from typing import Dict, List, Any
from datetime import datetime, timezone
import websockets


class AISConnector:
    def __init__(self):
        self.api_key = os.getenv("AISSTREAM_API_KEY", "")
        self.ws_url = "wss://stream.aisstream.io/v0/stream"
        self.connected = False
        self.ws = None
        self.ships: Dict[str, Dict] = {}
        self._listen_task = None

    async def connect(self):
        if not self.api_key:
            print("⚠️  AISSTREAM_API_KEY no configurada. estado unavailable.")
            self.connected = False
            return
        try:
            self.ws = await websockets.connect(f"{self.ws_url}?api_key={self.api_key}")
            self.connected = True
            subscribe_msg = {
                "APIKey": self.api_key,
                "BoundingBoxes": [[[-90, -180], [90, 180]]],
                "FilterMessageTypes": ["PositionReport"]
            }
            await self.ws.send(json.dumps(subscribe_msg))
            self._listen_task = asyncio.create_task(self._listen())
        except Exception as e:
            print(f"❌ Error conectando AIS: {e}")
            self.connected = False

    async def _listen(self):
        try:
            async for message in self.ws:
                data = json.loads(message)
                await self._process_ais_message(data)
        except websockets.exceptions.ConnectionClosed:
            self.connected = False
        except Exception as e:
            print(f"❌ Error listen AIS: {e}")
            self.connected = False

    async def _process_ais_message(self, msg: Dict):
        try:
            metadata = msg.get("MetaData", {})
            message = msg.get("Message", {})
            position = message.get("PositionReport", {})
            mmsi = metadata.get("MMSI", "unknown")
            self.ships[mmsi] = {
                "mmsi": mmsi,
                "name": metadata.get("ShipName", f"SHIP_{mmsi}"),
                "latitude": position.get("Latitude"),
                "longitude": position.get("Longitude"),
                "sog": position.get("Sog"),
                "cog": position.get("Cog"),
                "heading": position.get("TrueHeading"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "aisstream.io"
            }
        except Exception as e:
            print(f"⚠️  Error procesando AIS: {e}")

    async def disconnect(self):
        self.connected = False
        if self._listen_task:
            self._listen_task.cancel()
        if self.ws:
            await self.ws.close()

    def get_ships_in_bbox(self, lat_min: float, lat_max: float, lon_min: float, lon_max: float) -> List[Dict]:
        return [
            ship for ship in self.ships.values()
            if ship.get("latitude") is not None and ship.get("longitude") is not None
            and lat_min <= ship["latitude"] <= lat_max
            and lon_min <= ship["longitude"] <= lon_max
        ]

    def get_all_ships(self) -> List[Dict]:
        return list(self.ships.values())
