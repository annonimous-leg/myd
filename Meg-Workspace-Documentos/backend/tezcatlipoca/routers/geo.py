"""Authenticated geographic context with provider provenance and freshness."""
from datetime import datetime, timedelta, timezone
import math
import os
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from core.rate_limit import rate_limit_standard
from db.models import User
from routers.auth import get_current_user, require_role

router = APIRouter(tags=["Geo"])
_CACHE_MAX_AGE_SECONDS = 300
_AIS_MAX_AGE_SECONDS = 120


def _bounds(lat_min, lat_max, lon_min, lon_max):
    if lat_min > lat_max or lon_min > lon_max:
        raise HTTPException(status_code=422, detail="Bounding box minima must not exceed maxima")


def _inside(lat, lon, lat_min, lat_max, lon_min, lon_max):
    return (isinstance(lat, (int, float)) and not isinstance(lat, bool)
            and isinstance(lon, (int, float)) and not isinstance(lon, bool)
            and math.isfinite(lat) and math.isfinite(lon)
            and lat_min <= lat <= lat_max and lon_min <= lon <= lon_max)


def _observed(value):
    try:
        if not isinstance(value, str):
            return None
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except ValueError:
        return None


def _provider_state(fetcher, key):
    if fetcher is None:
        return {"status": "unavailable", "last_success": None}
    state = dict(getattr(fetcher, "source_status", {}).get(key, {}))
    last = getattr(fetcher, "last_fetch", {}).get(key)
    if last is None:
        return {**state, "status": state.get("status", "not_received"), "last_success": None}
    age = max(0, datetime.now(timezone.utc).timestamp() - last)
    state["age_seconds"] = round(age, 1)
    if age > _CACHE_MAX_AGE_SECONDS:
        state["status"] = "stale"
    return state


async def _aircraft(state, lat_min, lat_max, lon_min, lon_max, limit):
    adsb = getattr(state, "adsb_exchange", None)
    df = getattr(state, "data_fetcher", None)
    rows = []
    open_client = getattr(state, "adsb_lol", None)
    if open_client:
        try:
            aircraft = await open_client.get_aircraft_in_bbox(lat_min, lat_max, lon_min, lon_max)
            for ac in aircraft:
                y, x = ac.get("latitude"), ac.get("longitude")
                if not _inside(y, x, lat_min, lat_max, lon_min, lon_max):
                    continue
                rows.append({
                    "hex": ac.get("hex", ""), "callsign": ac.get("flight", ""),
                    "lat": y, "lon": x, "altitude": ac.get("altitude"),
                    "track": ac.get("heading"), "speed": ac.get("speed"),
                    "type": ac.get("type"), "timestamp": ac.get("timestamp"),
                    "source": "adsb_lol", "altitude_unit": "ft", "speed_unit": "kn",
                })
        except Exception:
            open_client.last_request_status = "unavailable"
    allow_restricted = os.getenv("TEZCATLIPOCA_ALLOW_RESTRICTED_PROVIDERS", "").lower() in ("1", "true", "yes")
    provider = {"status": "unavailable" if allow_restricted else "disabled_by_default", "last_success": None}
    if not rows and allow_restricted and adsb and getattr(adsb, "api_key", None):
        try:
            raw = await adsb.get_aircraft_in_bbox(lat_min, lat_max, lon_min, lon_max)
            provider = {
                "status": getattr(adsb, "last_request_status", "unavailable"),
                "last_success": getattr(adsb, "last_success", None),
                "coverage": "provider_radius_250_nm_max_200_records",
            }
            for ac in raw if isinstance(raw, list) else []:
                lat, lon = ac.get("latitude"), ac.get("longitude")
                if not _inside(lat, lon, lat_min, lat_max, lon_min, lon_max):
                    continue
                rows.append({
                    "hex": ac.get("hex", ""), "callsign": (ac.get("flight") or "").strip(),
                    "lat": lat, "lon": lon, "altitude": ac.get("altitude"),
                    "track": ac.get("heading"), "speed": ac.get("speed"),
                    "type": ac.get("type"), "timestamp": ac.get("timestamp"),
                    "source": "adsb_exchange", "altitude_unit": "ft", "speed_unit": "kn",
                })
        except Exception:
            provider["status"] = "unavailable"
    if not rows and allow_restricted and df:
        for ac in df.cache.get("flights", []):
            lat, lon = ac.get("lat"), ac.get("lon")
            if _inside(lat, lon, lat_min, lat_max, lon_min, lon_max):
                rows.append({
                    "hex": ac.get("icao24", ""), "callsign": ac.get("callsign", ""),
                    "lat": lat, "lon": lon, "altitude": ac.get("altitude"),
                    "track": ac.get("heading"), "speed": ac.get("velocity"),
                    "type": None, "timestamp": ac.get("timestamp"), "source": "opensky",
                    "altitude_unit": "m", "speed_unit": "m/s",
                })
    return rows[:limit], provider


def _open_aircraft_state(state):
    client = getattr(state, "adsb_lol", None)
    if client is None:
        return {"status": "not_initialized", "last_success": None}
    return {"status": client.last_request_status, "last_success": client.last_success,
            "coverage": client.coverage, "license": client.license,
            "attribution": "ADSB.lol contributors (ODbL 1.0)"}


def _ships(state, lat_min, lat_max, lon_min, lon_max, limit):
    ais = getattr(state, "ais_connector", None)
    rows = []
    latest = None
    try:
        source_rows = ais.get_ships_in_bbox(lat_min, lat_max, lon_min, lon_max) if ais else []
    except Exception:
        return [], {"status": "unavailable", "last_observation": None}
    for ship in source_rows:
        lat, lon = ship.get("latitude"), ship.get("longitude")
        if not _inside(lat, lon, lat_min, lat_max, lon_min, lon_max):
            continue
        observed = _observed(ship.get("timestamp"))
        if observed is None:
            continue
        latest = max(latest, observed) if latest else observed
        if not 0 <= (datetime.now(timezone.utc) - observed).total_seconds() <= _AIS_MAX_AGE_SECONDS:
            continue
        rows.append({
            "mmsi": ship.get("mmsi", ""), "name": ship.get("name", ""),
            "lat": lat, "lon": lon, "sog": ship.get("sog"), "cog": ship.get("cog"),
            "heading": ship.get("heading"), "timestamp": observed.isoformat(), "source": "ais",
        })
    connected = bool(ais and getattr(ais, "connected", False))
    status = "available" if connected and rows else "connected" if connected else "unavailable"
    if latest and (datetime.now(timezone.utc) - latest).total_seconds() > _AIS_MAX_AGE_SECONDS:
        status = "stale"
    return rows[:limit], {"status": status, "last_observation": latest.isoformat() if latest else None}


def _earthquakes(fetcher, lat_min, lat_max, lon_min, lon_max, magnitude, days, limit):
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    rows = []
    for q in fetcher.cache.get("quakes", []) if fetcher else []:
        lat, lon, mag = q.get("lat"), q.get("lon"), q.get("mag")
        observed = _observed(q.get("timestamp"))
        if (not _inside(lat, lon, lat_min, lat_max, lon_min, lon_max)
                or not isinstance(mag, (int, float)) or not math.isfinite(mag)
                or mag < magnitude or observed is None or not start <= observed <= now):
            continue
        rows.append(q)
    return rows[:limit]


@router.get("/flights")
async def get_geo_flights(
    lat_min: float = Query(-90, ge=-90, le=90), lat_max: float = Query(90, ge=-90, le=90),
    lon_min: float = Query(-180, ge=-180, le=180), lon_max: float = Query(180, ge=-180, le=180),
    limit: int = Query(500, ge=1, le=2000), req: Request = None,
    current_user: User = Depends(require_role(["full", "admin"])),
    _rate_limit: bool = Depends(rate_limit_standard),
):
    _bounds(lat_min, lat_max, lon_min, lon_max)
    rows, provider = await _aircraft(req.app.state, lat_min, lat_max, lon_min, lon_max, limit)
    return {
        "type": "flights", "count": len(rows), "bbox": [lat_min, lon_min, lat_max, lon_max],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sources": {"adsb_lol": _open_aircraft_state(req.app.state), "adsb_exchange": provider,
                    "opensky": _provider_state(getattr(req.app.state, "data_fetcher", None), "opensky")},
        "ac": [{"icao": r["hex"], "hex": r["hex"], "lat": r["lat"], "lon": r["lon"],
                "alt": r["altitude"], "track": r["track"], "spd": r["speed"], "flight": r["callsign"],
                "type": r["type"], "source": r["source"], "timestamp": r["timestamp"],
                "altitude_unit": r["altitude_unit"], "speed_unit": r["speed_unit"],
                "airline": "N/A", "from": "N/A", "to": "N/A"} for r in rows],
    }


@router.get("/ships")
async def get_geo_ships(
    lat_min: float = Query(-90, ge=-90, le=90), lat_max: float = Query(90, ge=-90, le=90),
    lon_min: float = Query(-180, ge=-180, le=180), lon_max: float = Query(180, ge=-180, le=180),
    limit: int = Query(500, ge=1, le=2000), req: Request = None,
    current_user: User = Depends(require_role(["full", "admin"])),
    _rate_limit: bool = Depends(rate_limit_standard),
):
    _bounds(lat_min, lat_max, lon_min, lon_max)
    rows, provider = _ships(req.app.state, lat_min, lat_max, lon_min, lon_max, limit)
    return {
        "type": "ships", "count": len(rows), "bbox": [lat_min, lon_min, lat_max, lon_max],
        "timestamp": datetime.now(timezone.utc).isoformat(), "sources": {"ais": provider},
        "ships": [{"mmsi": r["mmsi"], "shipname": r["name"], "latitude": r["lat"], "longitude": r["lon"],
                   "sog": r["sog"], "cog": r["cog"], "heading": r["heading"],
                   "source": r["source"], "timestamp": r["timestamp"],
                   "shiptype": "N/A", "destination": "N/A", "eta": "N/A"} for r in rows],
    }


@router.get("/earthquakes")
async def get_geo_earthquakes(
    min_magnitude: float = Query(2.5, ge=0, le=10), days: int = Query(1, ge=1, le=30),
    limit: int = Query(500, ge=1, le=2000), req: Request = None,
    current_user: User = Depends(require_role(["full", "admin"])),
    _rate_limit: bool = Depends(rate_limit_standard),
):
    df = getattr(req.app.state, "data_fetcher", None)
    rows = _earthquakes(df, -90, 90, -180, 180, min_magnitude, days, limit)
    return {
        "type": "FeatureCollection",
        "metadata": {"count": len(rows), "min_magnitude": min_magnitude, "days": days,
                     "timestamp": datetime.now(timezone.utc).isoformat(), "source": _provider_state(df, "usgs")},
        "features": [{"type": "Feature", "id": q["id"],
                      "geometry": {"type": "Point", "coordinates": [q["lon"], q["lat"], q.get("depth")]},
                      "properties": {"mag": q["mag"], "place": q.get("place"), "time": q.get("time_ms"),
                                     "tsunami": q.get("tsunami"), "alert": q.get("alert"), "url": q.get("url")}}
                     for q in rows],
    }


@router.get("/context")
async def get_geo_context(
    lat_min: float = Query(-90, ge=-90, le=90), lat_max: float = Query(90, ge=-90, le=90),
    lon_min: float = Query(-180, ge=-180, le=180), lon_max: float = Query(180, ge=-180, le=180),
    earthquake_days: int = Query(1, ge=1, le=30), earthquake_magnitude: float = Query(2.5, ge=0, le=10),
    limit: int = Query(100, ge=1, le=500), req: Request = None,
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """External context; imagery and feeds do not constitute a surveyed terrain."""
    _bounds(lat_min, lat_max, lon_min, lon_max)
    df = getattr(req.app.state, "data_fetcher", None)
    aircraft, adsb_status = await _aircraft(req.app.state, lat_min, lat_max, lon_min, lon_max, limit)
    ships, ais_status = _ships(req.app.state, lat_min, lat_max, lon_min, lon_max, limit)
    quakes = _earthquakes(df, lat_min, lat_max, lon_min, lon_max, earthquake_magnitude, earthquake_days, limit)
    return {
        "tenant_id": getattr(req.state, "tenant_id", None),
        "user_id": getattr(req.state, "megalodon_user_id", None),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "bbox": [lat_min, lon_min, lat_max, lon_max],
        "sources": {
            "gnss": {"status": "not_streamed_by_tezcatlipoca_context"},
            "adsb_lol": _open_aircraft_state(req.app.state),
            "adsb_exchange": adsb_status, "opensky": _provider_state(df, "opensky"),
            "ais": ais_status, "usgs": _provider_state(df, "usgs"),
            "telemetry": {"status": "running" if df else "offline",
                          "sources": list(df.cache.keys()) if df else [],
                          "metrics": getattr(df, "metrics", {}) if df else {}},
        },
        "aircraft": aircraft, "ships": ships,
        "earthquakes": [{"id": q["id"], "lat": q["lat"], "lon": q["lon"], "magnitude": q["mag"],
                         "place": q.get("place"), "time": q["timestamp"], "source": "usgs"}
                        for q in quakes],
    }
