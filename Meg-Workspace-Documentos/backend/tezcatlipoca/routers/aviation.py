"""Aviation Router - NOTAMs, METAR, TAF, ADS-B."""
from core.rate_limit import rate_limit_standard, rate_limit_strict
from fastapi import APIRouter, Request, Depends
from typing import Dict, Any, List
from datetime import datetime, timezone
from db.models import User
from routers.auth import get_current_user, require_role
from app.core.entitlements import PlanTipo, requiere_plan_minimo

router = APIRouter(dependencies=[Depends(requiere_plan_minimo(PlanTipo.PRO))])

@router.get("/notams")
async def get_notams(icao: str = "", lat: float = None, lon: float = None,
                     radius_nm: int = 50, req: Request = None, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)):
    faa = req.app.state.faa_notams
    if not faa:
        return {"error": "FAA NOTAMs not initialized"}
    return await faa.get_notams(icao, radius_nm, lat, lon)

@router.get("/metar/{icao}")
async def get_metar(icao: str, req: Request = None, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)):
    avwx = req.app.state.avwx
    if not avwx:
        return {"error": "AVWX not initialized"}
    return await avwx.get_metar(icao)

@router.get("/taf/{icao}")
async def get_taf(icao: str, req: Request = None, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)):
    avwx = req.app.state.avwx
    if not avwx:
        return {"error": "AVWX not initialized"}
    return await avwx.get_taf(icao)

@router.get("/adsb/aircraft")
async def get_aircraft(lat_min: float, lat_max: float, lon_min: float, lon_max: float,
                       req: Request = None, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)):
    adsb = req.app.state.adsb_exchange
    if not adsb:
        return {"error": "ADS-B Exchange not initialized"}
    return await adsb.get_aircraft_in_bbox(lat_min, lat_max, lon_min, lon_max)

@router.post("/adsb/gpsjam")
async def detect_gps_jam(request: Dict[str, Any], req: Request = None, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_strict)):
    adsb = req.app.state.adsb_exchange
    if not adsb:
        return {"error": "ADS-B Exchange not initialized"}
    aircraft = request.get("aircraft", [])
    return adsb.detect_gps_jam(aircraft)


@router.get("/military")
async def get_military_aircraft(
    lat_min: float = -90,
    lat_max: float = 90,
    lon_min: float = -180,
    lon_max: float = 180,
    limit: int = 200,
    req: Request = None, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)
):
    """Aeronaves militares vía adsb.lol (sin autenticación)."""
    df = req.app.state.data_fetcher

    # Intentar obtener del cache del data_fetcher
    if df and hasattr(df, 'cache'):
        military = df.cache.get('military_flights', [])
        if military:
            # Filtrar por bbox
            filtered = [
                m for m in military
                if lat_min <= m.get('lat', 0) <= lat_max 
                and lon_min <= m.get('lon', 0) <= lon_max
            ]
            return {
                "type": "military_aircraft",
                "count": len(filtered),
                "bbox": [lat_min, lon_min, lat_max, lon_max],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "aircraft": filtered[:limit]
            }

    # Fallback: fetch directo a adsb.lol
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get("https://api.adsb.lol/v2/mil")
            if resp.status_code == 200:
                data = resp.json()
                ac = data.get('ac', [])
                aircraft = []
                for a in ac[:limit]:
                    if lat_min <= a.get('lat', 0) <= lat_max and lon_min <= a.get('lon', 0) <= lon_max:
                        aircraft.append({
                            "hex": a.get('hex'),
                            "flight": a.get('flight', '').strip(),
                            "type": a.get('type'),
                            "r": a.get('r'),
                            "t": a.get('t'),
                            "alt_baro": a.get('alt_baro'),
                            "alt_geom": a.get('alt_geom'),
                            "gs": a.get('gs'),
                            "track": a.get('track'),
                            "lat": a.get('lat'),
                            "lon": a.get('lon'),
                            "nic": a.get('nic'),
                            "rc": a.get('rc'),
                            "seen_pos": a.get('seen_pos'),
                            "version": a.get('version'),
                            "category": a.get('category'),
                            "source": "adsb.lol",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        })
                return {
                    "type": "military_aircraft",
                    "count": len(aircraft),
                    "bbox": [lat_min, lon_min, lat_max, lon_max],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "aircraft": aircraft
                }
    except Exception as e:
        print(f"⚠️  Error fetching military aircraft: {e}")

    return {
        "type": "military_aircraft",
        "count": 0,
        "bbox": [lat_min, lon_min, lat_max, lon_max],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "aircraft": [],
        "note": "No data available. Ensure data_fetcher is running or adsb.lol is accessible."
    }
