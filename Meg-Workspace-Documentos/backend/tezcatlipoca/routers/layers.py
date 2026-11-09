"""Layers Router - Conectado a DataFetcherEngine real."""
from core.rate_limit import rate_limit_standard, rate_limit_strict
from fastapi import APIRouter, Request, Depends

from services.data_fetcher import DataFetcherEngine
from db.models import User
from routers.auth import get_current_user, require_role

router = APIRouter()
_data_fetcher: DataFetcherEngine | None = None


def set_data_fetcher(fetcher: DataFetcherEngine):
    global _data_fetcher
    _data_fetcher = fetcher


def _get_data_fetcher(request: Request = None) -> DataFetcherEngine | None:
    if _data_fetcher:
        return _data_fetcher
    if request is not None:
        return getattr(request.app.state, "data_fetcher", None)
    return None


@router.get("/")
async def get_layers(request: Request, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)):
    fetcher = _get_data_fetcher(request)
    if not fetcher:
        return {"layers": [], "error": "Data fetcher not initialized"}

    available_layers = list(fetcher.cache.keys())
    layer_map = {
        "flights": {"name": "Flights", "icon": "✈️"},
        "ships": {"name": "Ships", "icon": "🚢"},
        "quakes": {"name": "Earthquakes", "icon": "🌋"},
        "firms": {"name": "FIRMS", "icon": "🔥"},
        "weather": {"name": "Weather", "icon": "🌤️"},
        "air_quality": {"name": "Air Quality", "icon": "💨"},
        "military_flights": {"name": "Military", "icon": "🛩️"},
        "satellites": {"name": "Satellites", "icon": "🛰️"},
        "cctv": {"name": "CCTV", "icon": "📹"},
        "sigint": {"name": "SIGINT", "icon": "📡"},
        "sar": {"name": "SAR", "icon": "📡"},
        "malware": {"name": "Malware", "icon": "🦠"},
        "mesh": {"name": "Mesh", "icon": "🕸️"},
    }

    layers = []
    for layer_id in available_layers:
        info = layer_map.get(layer_id, {"name": layer_id, "icon": "📊"})
        data = fetcher.cache.get(layer_id, [])
        count = len(data) if isinstance(data, list) else 0
        layers.append({
            "id": layer_id,
            "name": info["name"],
            "icon": info["icon"],
            "active": True,
            "count": count
        })

    return {"layers": layers}


@router.get("/{layer_id}")
async def get_layer_data(layer_id: str, request: Request, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)):
    fetcher = _get_data_fetcher(request)
    if not fetcher:
        return {"error": "Data fetcher not initialized"}
    data = fetcher.cache.get(layer_id, [])
    return {"layer_id": layer_id, "data": data[:100], "total": len(data) if isinstance(data, list) else 0}
