"""Transport Router - Rutas, trenes, GTFS."""
from core.rate_limit import rate_limit_standard, rate_limit_strict
from fastapi import APIRouter, Request, Query, Depends
from typing import Dict, Any, List
from datetime import datetime, timezone
from db.models import User
from routers.auth import get_current_user, require_role
from app.core.entitlements import PlanTipo, requiere_plan_minimo

router = APIRouter(dependencies=[Depends(requiere_plan_minimo(PlanTipo.PRO))])

@router.post("/route")
async def get_route(request: Dict[str, Any], req: Request, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_strict)):
    gh = req.app.state.graphhopper
    if not gh:
        return {"error": "GraphHopper not initialized"}
    return await gh.get_route(
        request.get("from_lat", 0),
        request.get("from_lon", 0),
        request.get("to_lat", 0),
        request.get("to_lon", 0),
        request.get("vehicle", "car")
    )

@router.post("/isochrone")
async def get_isochrone(request: Dict[str, Any], req: Request, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_strict)):
    gh = req.app.state.graphhopper
    if not gh:
        return {"error": "GraphHopper not initialized"}
    return await gh.get_isochrone(
        request.get("lat", 0),
        request.get("lon", 0),
        request.get("time_limit", 600),
        request.get("vehicle", "car")
    )

@router.get("/trains/stations")
async def search_stations(query: str, limit: int = 10, req: Request = None, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)):
    db = req.app.state.db_trains
    if not db:
        return {"error": "DB Trains not initialized"}
    return await db.get_stations(query, limit)

@router.get("/trains/departures/{station_id}")
async def get_departures(station_id: str, duration: int = 60, req: Request = None, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)):
    db = req.app.state.db_trains
    if not db:
        return {"error": "DB Trains not initialized"}
    return await db.get_departures(station_id, duration)

@router.get("/gtfs/feeds")
async def get_gtfs_feeds(country: str = "", limit: int = 50, req: Request = None, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)):
    gtfs = req.app.state.gtfs_mobility
    if not gtfs:
        return {"error": "GTFS Mobility not initialized"}
    return await gtfs.get_feeds(country, limit)


@router.get("/ships")
async def get_ships(
    lat_min: float = Query(-90, ge=-90, le=90),
    lat_max: float = Query(90, ge=-90, le=90),
    lon_min: float = Query(-180, ge=-180, le=180),
    lon_max: float = Query(180, ge=-180, le=180),
    limit: int = Query(500, ge=1, le=2000),
    req: Request = None, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)
):
    """Obtener posiciones de barcos vía AIS."""
    ais = req.app.state.ais_connector
    if not ais:
        return {"error": "AIS connector not initialized"}
    ships = ais.get_ships_in_bbox(lat_min, lat_max, lon_min, lon_max)
    return {
        "count": len(ships),
        "ships": ships[:limit],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.get("/fishing")
async def get_fishing_vessels(
    limit: int = Query(100, ge=1, le=500),
    req: Request = None, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)
):
    """Obtener embarcaciones pesqueras vía Global Fishing Watch."""
    df = req.app.state.data_fetcher
    if not df or not hasattr(df, 'cache'):
        return {"error": "Data fetcher not initialized"}
    vessels = df.cache.get('fishing', [])
    return {
        "count": len(vessels),
        "vessels": vessels[:limit],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
