"""Admin Router — Dashboard and management endpoints.

Requires admin tier access.
"""
from core.rate_limit import rate_limit_standard, rate_limit_strict

from datetime import datetime, timezone, timedelta
from typing import Optional, List

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from db.models import get_async_db, User, ApiLog, Snapshot
from app.core.deps import get_db as megalodon_get_db
from app.api.v1.users import require_tenant_admin
from app.models.user import User as MegalodonUser
from routers.auth import get_current_user

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ─── Pydantic Models ───

class LogsFilterRequest(BaseModel):
    hours: int = Field(default=24, ge=1, le=168)
    endpoint: Optional[str] = Field(default=None, max_length=255)
    status_code: Optional[int] = Field(default=None, ge=100, le=599)
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=1000, ge=1, le=10000)


async def require_admin(current_user: User = Depends(get_current_user)):
    """Dependency to require admin access."""
    if current_user.tier != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


@router.get("/dashboard")
async def admin_dashboard(
    admin: MegalodonUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(get_async_db),
    megalodon_db: AsyncSession = Depends(megalodon_get_db),
    _rate_limit: bool = Depends(rate_limit_standard)
):
    """Get admin dashboard statistics."""
    # User stats
    result = await megalodon_db.execute(select(func.count()).select_from(MegalodonUser).where(MegalodonUser.tenant_id == admin.tenant_id))
    total_users = result.scalar()

    result = await megalodon_db.execute(select(func.count()).select_from(MegalodonUser).where(MegalodonUser.tenant_id == admin.tenant_id, MegalodonUser.is_active == True))
    active_users = result.scalar()

    result = await megalodon_db.execute(
        select(func.count()).select_from(MegalodonUser).where(
            MegalodonUser.tenant_id == admin.tenant_id,
            MegalodonUser.created_at >= datetime.now(timezone.utc) - timedelta(days=1)
        )
    )
    new_users_today = result.scalar()

    # API stats
    result = await db.execute(select(func.count()).select_from(ApiLog).where(ApiLog.tenant_id == str(admin.tenant_id)))
    total_requests = result.scalar()

    result = await db.execute(
        select(func.count()).select_from(ApiLog).where(
            ApiLog.tenant_id == str(admin.tenant_id),
            ApiLog.timestamp >= datetime.now(timezone.utc) - timedelta(days=1)
        )
    )
    requests_today = result.scalar()

    result = await db.execute(
        select(func.count()).select_from(ApiLog).where(
            ApiLog.tenant_id == str(admin.tenant_id),
            ApiLog.status_code >= 400,
            ApiLog.timestamp >= datetime.now(timezone.utc) - timedelta(days=1)
        )
    )
    error_count = result.scalar()
    error_rate = round(error_count / requests_today * 100, 2) if requests_today > 0 else 0

    # Top endpoints
    result = await db.execute(
        select(ApiLog.endpoint, func.count(ApiLog.id).label("count"))
        .where(ApiLog.tenant_id == str(admin.tenant_id), ApiLog.timestamp >= datetime.now(timezone.utc) - timedelta(days=1))
        .group_by(ApiLog.endpoint)
        .order_by(func.count(ApiLog.id).desc())
        .limit(10)
    )
    top_endpoints = result.all()

    # Snapshots
    result = await db.execute(select(func.count()).select_from(Snapshot).where(Snapshot.tenant_id == str(admin.tenant_id)))
    total_snapshots = result.scalar()

    return {
        "users": {
            "total": total_users,
            "active": active_users,
            "new_today": new_users_today
        },
        "api": {
            "total_requests": total_requests,
            "requests_today": requests_today,
            "error_rate": error_rate,
            "top_endpoints": [{"endpoint": e[0], "count": e[1]} for e in top_endpoints]
        },
        "snapshots": total_snapshots,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.get("/logs")
async def get_logs(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
    hours: int = 24,
    endpoint: Optional[str] = None,
    status_code: Optional[int] = None,
    skip: int = 0,
    limit: int = 1000,
    _rate_limit: bool = Depends(rate_limit_standard)
):
    """Get API logs with filtering."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    conditions = [ApiLog.tenant_id == str(admin.tenant_id), ApiLog.timestamp >= since]

    if endpoint:
        safe_endpoint = endpoint.replace("%", "").replace("_", "")
        conditions.append(ApiLog.endpoint.contains(safe_endpoint))
    if status_code:
        conditions.append(ApiLog.status_code == status_code)

    stmt = (
        select(ApiLog)
        .where(and_(*conditions))
        .order_by(ApiLog.timestamp.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    logs = result.scalars().all()

    return [
        {
            "id": l.id,
            "endpoint": l.endpoint,
            "method": l.method,
            "status_code": l.status_code,
            "ip_address": l.ip_address,
            "timestamp": l.timestamp.isoformat() if l.timestamp else None
        }
        for l in logs
    ]


@router.get("/health/detailed")
async def detailed_health(
    admin: User = Depends(require_admin),
    _rate_limit: bool = Depends(rate_limit_standard)
):
    """Get detailed system health information."""
    import psutil
    import time

    uptime = time.time() - __import__("main").ws_manager.startup_time

    return {
        "system": {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_usage": psutil.disk_usage("/").percent,
            "uptime_seconds": int(uptime)
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
