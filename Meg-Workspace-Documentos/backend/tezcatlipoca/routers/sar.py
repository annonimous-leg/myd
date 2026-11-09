"""SAR Router - NASA, GEE, Copernicus."""
from core.rate_limit import rate_limit_standard, rate_limit_strict
from fastapi import APIRouter, Request, Depends
from typing import Dict, Any, List
from datetime import datetime, timezone
from db.models import User
from routers.auth import get_current_user, require_role
from app.core.entitlements import PlanTipo, requiere_plan_minimo

router = APIRouter(dependencies=[Depends(requiere_plan_minimo(PlanTipo.PRO))])

@router.get("/nasa/search")
async def search_nasa(collection: str = "C1442068286-ASF",
                      bbox: str = "", start_date: str = None,
                      end_date: str = None, limit: int = 50,
                      req: Request = None, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)):
    nasa = req.app.state.nasa_earthdata
    if not nasa:
        return {"error": "NASA Earthdata not initialized"}
    bbox_list = [float(x) for x in bbox.split(",")] if bbox else None
    return await nasa.search_granules(collection, bbox_list, start_date, end_date, limit)

@router.get("/nasa/collections")
async def get_nasa_collections(keyword: str = "SAR", req: Request = None, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)):
    nasa = req.app.state.nasa_earthdata
    if not nasa:
        return {"error": "NASA Earthdata not initialized"}
    return await nasa.get_collections(keyword)

@router.get("/copernicus/search")
async def search_copernicus(bbox: str = "", start_date: str = None,
                            end_date: str = None, product_type: str = "GRD",
                            limit: int = 50, req: Request = None, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)):
    cop = req.app.state.copernicus_scihub
    if not cop:
        return {"error": "Copernicus SciHub not initialized"}
    bbox_list = [float(x) for x in bbox.split(",")] if bbox else None
    return await cop.search_sentinel1(bbox_list, start_date, end_date, product_type, limit)

@router.get("/gee/collection")
async def get_gee_collection(collection_id: str = "COPERNICUS/S1_GRD",
                             bbox: str = "", start_date: str = None,
                             end_date: str = None, limit: int = 10,
                             req: Request = None, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)):
    gee = req.app.state.gee
    if not gee:
        return {"error": "Google Earth Engine not initialized"}
    bbox_list = [float(x) for x in bbox.split(",")] if bbox else None
    return gee.get_sar_collection(collection_id, bbox_list, start_date, end_date, limit)


@router.get("/anomalies")
async def get_sar_anomalies(
    bbox: str = "",
    start_date: str = None,
    end_date: str = None,
    req: Request = None, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)
):
    """Detectar anomalías SAR (cambios de superficie, subsidencia)."""
    sar = req.app.state.sar_connector
    if not sar:
        return {"error": "SAR connector not initialized"}

    bbox_list = [float(x) for x in bbox.split(",")] if bbox else None

    # Buscar en ASF + OPERA para detectar cambios
    results = []
    try:
        asf_data = await sar.search_asf(bbox_list or [-180, -90, 180, 90], start_date, end_date)
        for r in asf_data:
            results.append({
                "type": "sar_scene",
                "granule": r.get("granule", ""),
                "platform": r.get("platform", ""),
                "date": r.get("date", ""),
                "bbox": r.get("bbox", []),
                "anomaly_score": None,
                "anomaly_status": "NOT_COMPUTED_RASTER_REQUIRED",
                "anomaly_type": None,
                "source": r.get("source", "asf"),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
    except Exception as e:
        print(f"⚠️  Error SAR anomalies: {e}")

    return {
        "count": len(results),
        "anomalies": results,
        "bbox": bbox_list,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.get("/scenes")
async def get_sar_scenes(
    collection: str = "C1442068286-ASF",
    bbox: str = "",
    start_date: str = None,
    end_date: str = None,
    limit: int = 50,
    req: Request = None, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)
):
    """Obtener escenas SAR disponibles (NASA Earthdata + Copernicus)."""
    nasa = req.app.state.nasa_earthdata
    cop = req.app.state.copernicus_scihub

    scenes = []
    bbox_list = [float(x) for x in bbox.split(",")] if bbox else None

    # NASA Earthdata
    if nasa:
        try:
            nasa_scenes = await nasa.search_granules(collection, bbox_list, start_date, end_date, limit)
            if isinstance(nasa_scenes, list):
                for s in nasa_scenes:
                    if "error" not in s:
                        scenes.append({
                            "id": s.get("granule", ""),
                            "platform": s.get("platform", "SENTINEL-1"),
                            "date": s.get("date", ""),
                            "bbox": s.get("bbox", []),
                            "url": s.get("url", ""),
                            "provider": "NASA Earthdata",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        })
        except Exception as e:
            print(f"⚠️  Error NASA scenes: {e}")

    # Copernicus
    if cop:
        try:
            cop_scenes = await cop.search_sentinel1(bbox_list, start_date, end_date, "GRD", limit)
            if isinstance(cop_scenes, list):
                for s in cop_scenes:
                    if "error" not in s:
                        scenes.append({
                            "id": s.get("id", ""),
                            "platform": s.get("platform", "SENTINEL-1"),
                            "date": s.get("date", ""),
                            "bbox": s.get("bbox", []),
                            "url": s.get("url", ""),
                            "provider": "Copernicus SciHub",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        })
        except Exception as e:
            print(f"⚠️  Error Copernicus scenes: {e}")

    return {
        "count": len(scenes),
        "scenes": scenes[:limit],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
