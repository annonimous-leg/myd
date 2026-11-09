"""Photogrammetry Router - WebODM."""
from core.rate_limit import rate_limit_standard, rate_limit_strict
from fastapi import APIRouter, Request, Depends
from typing import Dict, Any, List
from db.models import User
from routers.auth import get_current_user, require_role
from app.core.entitlements import PlanTipo, requiere_plan_minimo

router = APIRouter(dependencies=[Depends(requiere_plan_minimo(PlanTipo.PRO))])

@router.get("/projects")
async def get_projects(req: Request = None, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)):
    w = req.app.state.webodm
    if not w:
        return {"error": "WebODM not initialized"}
    return await w.get_projects()

@router.post("/projects")
async def create_project(request: Dict[str, Any], req: Request = None, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_strict)):
    w = req.app.state.webodm
    if not w:
        return {"error": "WebODM not initialized"}
    return await w.create_project(request.get("name", ""), request.get("description", ""))

@router.get("/tasks/{project_id}/{task_id}")
async def get_task_status(project_id: int, task_id: str, req: Request = None, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)):
    w = req.app.state.webodm
    if not w:
        return {"error": "WebODM not initialized"}
    return await w.get_task_status(project_id, task_id)
