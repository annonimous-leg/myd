"""Commercial-use compatible weather endpoint with honest coverage metadata."""
from fastapi import APIRouter, Depends, Query, Request

from core.rate_limit import rate_limit_standard
from routers.auth import get_current_user

router = APIRouter()


@router.get("/forecast")
async def forecast(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    req: Request = None,
    _user=Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_standard),
):
    client = getattr(req.app.state, "noaa_weather", None)
    if client is None:
        return {"status": "config_required", "source": "noaa_nws", "periods": []}
    return await client.forecast(lat, lon)


@router.get("/global")
async def global_forecast(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    req: Request = None,
    _user=Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_standard),
):
    """Local ECMWF open-data forecast sample; not a live site measurement.

    Returns config_required when no real licensed GRIB dataset was ingested.
    """
    store = getattr(req.app.state, "ecmwf_grids", None)
    if store is None:
        return {"status": "config_required", "source": "ecmwf_open_data"}
    return store.forecast_at(lat, lon)
