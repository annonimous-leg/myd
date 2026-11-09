from __future__ import annotations
from typing import Any, Dict

from fastapi import APIRouter, Depends, Query, Request

from db.models import User
from routers.auth import get_current_user, require_role
from services.osint_recon.osint_engine import OSINTReconEngine

from core.rate_limit import rate_limit_standard, rate_limit_strict
router = APIRouter()
_osint_engine: OSINTReconEngine | None = None

def set_osint_engine(engine: OSINTReconEngine):
    global _osint_engine
    _osint_engine = engine

def _get_osint_engine(request: Request = None) -> OSINTReconEngine | None:
    if _osint_engine:
        return _osint_engine
    if request is not None:
        return getattr(request.app.state, "osint_engine", None)
    return None

@router.get("/lookup")
async def osint_lookup_get(
    request: Request,
    target: str = Query(...),
    type: str = Query("auto", alias="type"), current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    engine = _get_osint_engine(request)
    if not engine:
        return {"error": "OSINT engine not initialized"}
    if not target:
        return {"error": "Target required"}
    return await engine.lookup(target, type)

@router.post("/lookup")
async def osint_lookup_post(
    request: Request,
    payload: Dict[str, Any],
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    engine = _get_osint_engine(request)
    if not engine:
        return {"error": "OSINT engine not initialized"}
    target = payload.get("target") or payload.get("entity") or ""
    lookup_type = payload.get("lookup_type") or payload.get("type") or "auto"
    if not target:
        return {"error": "Target required"}
    return await engine.lookup(target, lookup_type)

@router.post("/expand")
async def osint_expand(
    request: Request,
    payload: Dict[str, Any],
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    engine = _get_osint_engine(request)
    if not engine:
        return {"error": "OSINT engine not initialized"}
    entity = payload.get("entity", "")
    if not entity:
        return {"error": "Entity required"}
    return await engine.expand_entity(entity, payload.get("depth", 1))

@router.get("/ip/{ip}")
async def lookup_ip(
    ip: str,
    request: Request,
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    engine = _get_osint_engine(request)
    if not engine:
        return {"error": "OSINT engine not initialized"}
    return await engine.lookup_ip(ip)

@router.get("/dns/{domain}")
async def lookup_dns(
    domain: str,
    request: Request,
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    engine = _get_osint_engine(request)
    if not engine:
        return {"error": "OSINT engine not initialized"}
    return await engine.lookup_dns(domain)

@router.get("/cve/{cve_id}")
async def lookup_cve(
    cve_id: str,
    request: Request,
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    engine = _get_osint_engine(request)
    if not engine:
        return {"error": "OSINT engine not initialized"}
    return await engine.lookup_cve(cve_id)
