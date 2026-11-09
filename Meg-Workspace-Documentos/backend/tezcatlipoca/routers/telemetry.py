"""Telemetry Router - Conectado a DataFetcherEngine real."""
from core.rate_limit import rate_limit_standard, rate_limit_strict
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Depends

from services.data_fetcher import DataFetcherEngine
from db.models import User
from routers.auth import get_current_user, require_role
from app.core.entitlements import PlanTipo, requiere_plan_minimo

router = APIRouter(dependencies=[Depends(requiere_plan_minimo(PlanTipo.PRO))])
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
async def get_telemetry(request: Request, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)):
    fetcher = _get_data_fetcher(request)
    if not fetcher:
        return {"status": "offline", "error": "Data fetcher not initialized"}
    cache_keys = list(fetcher.cache.keys())
    metrics = fetcher.metrics if hasattr(fetcher, 'metrics') else {}
    return {
        "status": "online",
        "sources": len(cache_keys),
        "active_layers": cache_keys[:10],
        "metrics": metrics,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.get("/cache")
async def get_cache_stats(request: Request, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)):
    fetcher = _get_data_fetcher(request)
    if not fetcher:
        return {"error": "Data fetcher not initialized"}
    return {
        "cache_keys": list(fetcher.cache.keys()),
        "sizes": {k: len(v) if isinstance(v, list) else 1 for k, v in fetcher.cache.items()}
    }


@router.get("/metrics")
async def get_metrics(request: Request, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)):
    fetcher = _get_data_fetcher(request)
    if not fetcher:
        return {"error": "Data fetcher not initialized"}
    return fetcher.metrics if hasattr(fetcher, 'metrics') else {}
