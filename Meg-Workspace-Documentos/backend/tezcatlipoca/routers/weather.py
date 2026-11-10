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
