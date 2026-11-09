"""Geo Threats Router — Integra zonas de conflicto + malware intel.

Detecta zonas calientes via GDELT y enriquece automaticamente IPs/domains
de esas regiones con el MalwareAggregator.
"""
import asyncio
import math
from fastapi import APIRouter, Request, Query, HTTPException, Depends
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta

from db.models import User
from routers.auth import get_current_user, require_role
from app.core.entitlements import PlanTipo, requiere_plan_minimo
from core.rate_limit import rate_limit_standard, rate_limit_strict

router = APIRouter(tags=["Geo Threats"])

# BUG ORIGINAL (tarea C / "no va a funcionar como está"): este router
# tenía su propio rate limiter casero (_request_log, un dict de proceso
# en memoria). No funciona correctamente con más de un worker/réplica
# (cada proceso ve su propio dict, así que el límite real termina
# siendo N_workers veces el nominal) y tiene fuga de memoria: una IP
# que pega una sola vez y nunca vuelve se queda en el dict para
# siempre, sin TTL ni eviction. AHORA: se usa tezca_rate_limit (Redis
# sliding-window compartido, mismo mecanismo que ya usa el resto de la
# plataforma) vía Depends(), igual que el resto de los endpoints
# tocados en esta sesión.


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en km entre dos puntos."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


async def _fetch_gdelt_conflicts(
    lat_min: float, lat_max: float, lon_min: float, lon_max: float,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """Consultar GDELT por eventos de conflicto en un bbox."""
    try:
        import httpx
        # GDELT GEO API
        center_lat = (lat_min + lat_max) / 2
        center_lon = (lon_min + lon_max) / 2
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://api.gdeltproject.org/api/v2/geo/geo",
                params={
                    "query": "conflict OR war OR attack OR protest OR military OR terrorism",
                    "mode": "ArtList",
                    "format": "json",
                    "maxrecords": limit,
                }
            )
            if resp.status_code == 200:
                data = resp.json()
                articles = []
                for art in data.get("articles", []):
                    lat = art.get("lat")
                    lon = art.get("lon")
                    if lat and lon:
                        # Filtrar por bbox
                        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
                            articles.append({
                                "type": "conflict",
                                "title": art.get("title", ""),
                                "url": art.get("url", ""),
                                "lat": lat,
                                "lon": lon,
                                "source": art.get("domain", "GDELT"),
                                "timestamp": art.get("seendate", datetime.now(timezone.utc).isoformat()),
                                "severity": _estimate_severity(art.get("title", "")),
                            })
                return articles
    except Exception as e:
        print(f"⚠️ GDELT conflict fetch error: {e}")
    return []


def _estimate_severity(title: str) -> str:
    """Estimar severidad de un titulo de noticia."""
    title_lower = title.lower()
    critical = ["attack", "killed", "death", "bombing", "airstrike", "massacre", "invasion"]
    high = ["clash", "fighting", "shelling", "raid", "ambush", "explosion"]
    medium = ["protest", "demonstration", "tension", "standoff", "blockade"]

    for word in critical:
        if word in title_lower:
            return "critical"
    for word in high:
        if word in title_lower:
            return "high"
    for word in medium:
        if word in title_lower:
            return "medium"
    return "low"


async def _enrich_zone_ips(
    malware_agg,
    lat: float, lon: float, radius_km: float = 100
) -> List[Dict[str, Any]]:
    """Enriquecer amenazas con geolocalización verificable.

    El aggregator puede aportar geolocalización explícita. Si el indicador
    carece de coordenadas verificadas se devuelve ``geolocation_status`` como
    unresolved y no se inventa una posición cercana al centro del conflicto.
    """
    if not malware_agg:
        return []
    try:
        feeds = await malware_agg.get_feeds()
        threats = []
        for src, items in feeds.get("feeds", {}).items():
            for item in items[:5]:
                geo = item.get("geo") or item.get("geolocation") or {}
                threat_lat = geo.get("lat", geo.get("latitude"))
                threat_lon = geo.get("lon", geo.get("longitude"))
                try:
                    if threat_lat is not None: threat_lat = float(threat_lat)
                    if threat_lon is not None: threat_lon = float(threat_lon)
                except (TypeError, ValueError):
                    threat_lat = threat_lon = None
                threats.append({
                    "type": "malware_threat",
                    "source": src,
                    "indicator": item.get("ip") or item.get("url") or item.get("cve_id", ""),
                    "indicator_type": "ip" if item.get("ip") else ("url" if item.get("url") else "cve"),
                    "lat": threat_lat,
                    "lon": threat_lon,
                    "geolocation_status": "resolved" if threat_lat is not None and threat_lon is not None else "unresolved",
                    "severity": "high" if src == "feodo" else "medium",
                    "details": item,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
        return threats
    except Exception as e:
        print(f"⚠️ Zone enrichment error: {e}")
        return []


@router.get("/threats")
async def get_geo_threats(
    lat_min: float = Query(-90, ge=-90, le=90),
    lat_max: float = Query(90, ge=-90, le=90),
    lon_min: float = Query(-180, ge=-180, le=180),
    lon_max: float = Query(180, ge=-180, le=180),
    include_malware: bool = Query(True, description="Incluir enriquecimiento de malware"),
    include_conflicts: bool = Query(True, description="Incluir eventos de conflicto GDELT"),
    limit: int = Query(200, ge=1, le=1000),
    req: Request = None, current_user: User = Depends(require_role(["full", "admin"])),
    _rl: None = Depends(rate_limit_standard),
):
    """Obtener amenazas en formato GeoJSON para el mapa.

    Integra:
    - Eventos de conflicto de GDELT (gratuito)
    - Amenazas de malware enriquecidas por zona (via MalwareAggregator)
    """
    features = []
    metadata = {
        "bbox": [lat_min, lon_min, lat_max, lon_max],
        "sources": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    malware_agg = None
    if req and req.app and hasattr(req.app.state, "malware_agg"):
        malware_agg = req.app.state.malware_agg

    # 1. Eventos de conflicto GDELT
    if include_conflicts:
        conflicts = await _fetch_gdelt_conflicts(lat_min, lat_max, lon_min, lon_max, limit)
        metadata["sources"].append({"name": "GDELT", "count": len(conflicts)})
        for c in conflicts:
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [c["lon"], c["lat"]]},
                "properties": {
                    "type": "conflict",
                    "title": c["title"],
                    "url": c["url"],
                    "source": c["source"],
                    "severity": c["severity"],
                    "timestamp": c["timestamp"],
                }
            })

    # 2. Amenazas de malware enriquecidas
    if include_malware and malware_agg:
        center_lat = (lat_min + lat_max) / 2
        center_lon = (lon_min + lon_max) / 2
        malware_threats = await _enrich_zone_ips(
            malware_agg, center_lat, center_lon,
            radius_km=_haversine(lat_min, lon_min, lat_max, lon_max) / 2
        )
        metadata["sources"].append({"name": "MalwareAggregator", "count": len(malware_threats)})
        for t in malware_threats:
            features.append({
                "type": "Feature",
                "geometry": (
                    {"type": "Point", "coordinates": [t["lon"], t["lat"]]}
                    if t.get("lat") is not None and t.get("lon") is not None
                    else None
                ),
                "properties": {
                    "type": "malware_threat",
                    "indicator": t["indicator"],
                    "indicator_type": t["indicator_type"],
                    "source": t["source"],
                    "severity": t["severity"],
                    "timestamp": t["timestamp"],
                }
            })

    return {
        "type": "FeatureCollection",
        "metadata": {
            **metadata,
            "total_features": len(features),
            "include_malware": include_malware,
            "include_conflicts": include_conflicts,
        },
        "features": features[:limit],
    }


@router.get("/hotzones")
async def get_hotzones(
    req: Request = None,
    hours: int = Query(24, ge=1, le=168, description="Horas hacia atras para detectar conflictos"), current_user: User = Depends(require_role(["full", "admin"])),
    _rl: None = Depends(rate_limit_strict),
):
    """Detectar zonas calientes globalmente via GDELT.

    Devuelve clusters de eventos de conflicto para que el frontend
    pueda enfocar el mapa automaticamente.
    """
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://api.gdeltproject.org/api/v2/geo/geo",
                params={
                    "query": "conflict OR war OR attack OR protest OR military",
                    "mode": "ArtList",
                    "format": "json",
                    "maxrecords": 100,
                }
            )
            if resp.status_code == 200:
                data = resp.json()
                zones = {}
                for art in data.get("articles", []):
                    lat = art.get("lat")
                    lon = art.get("lon")
                    if lat and lon:
                        # Agrupar por region aproximada (1 grado)
                        key = (round(lat, 0), round(lon, 0))
                        if key not in zones:
                            zones[key] = {
                                "lat": key[0],
                                "lon": key[1],
                                "count": 0,
                                "articles": [],
                                "severity_score": 0,
                            }
                        zones[key]["count"] += 1
                        zones[key]["articles"].append({
                            "title": art.get("title", ""),
                            "url": art.get("url", ""),
                        })
                        sev = {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(
                            _estimate_severity(art.get("title", "")), 1
                        )
                        zones[key]["severity_score"] += sev

                # Ordenar por severidad
                hotzones = sorted(zones.values(), key=lambda x: -x["severity_score"])[:10]
                for z in hotzones:
                    z["articles"] = z["articles"][:5]  # Limitar
                    z["risk_level"] = _score_to_risk(min(10, z["severity_score"] / 3))

                return {
                    "hotzones": hotzones,
                    "total_events": sum(z["count"] for z in hotzones),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
    except Exception as e:
        print(f"⚠️ Hotzones error: {e}")

    return {
        "hotzones": [],
        "total_events": 0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "note": "GDELT data unavailable"
    }


def _score_to_risk(score: float) -> str:
    if score >= 8:
        return "critical"
    elif score >= 6:
        return "high"
    elif score >= 4:
        return "medium"
    elif score >= 2:
        return "low"
    return "none"
