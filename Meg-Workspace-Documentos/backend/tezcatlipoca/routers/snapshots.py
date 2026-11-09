"""Snapshots Router V2 — Persisted in SQLite/Postgres.

Provides CRUD for map state snapshots with tenant + user ownership.

FASE 3 (2026-08-02): antes de este cambio había 3 problemas reales,
no solo falta de tenant_id:
  1. get_snapshot() no validaba autorización en absoluto -- cualquier
     usuario autenticado podía leer cualquier snapshot por ID.
  2. list_snapshots() mostraba snapshots con user_id=NULL a TODOS los
     usuarios sin límite de tenant -- fuga entre organizaciones.
  3. delete_snapshot() dejaba que cualquier tier=admin borrara
     snapshots de cualquier tenant, no solo el propio.
Los tres se corrigen aquí junto con el tenant_id real.
"""
from core.rate_limit import rate_limit_standard, rate_limit_strict

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from db.models import get_async_db, Snapshot
from routers.auth import get_current_user
from db.models import User

router = APIRouter(tags=["snapshots"])


class SnapshotCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    layers: list = Field(default_factory=list)
    viewport: Optional[dict] = None


class SnapshotResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    layers: list
    viewport: Optional[dict]
    created_at: str

    class Config:
        from_attributes = True


def _to_response(s: Snapshot) -> SnapshotResponse:
    return SnapshotResponse(
        id=s.id,
        name=s.name,
        description=s.description,
        layers=s.layers or [],
        viewport=s.viewport,
        created_at=s.created_at.isoformat()
    )


@router.get("/", response_model=list[SnapshotResponse])
async def list_snapshots(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db), _rate_limit: bool = Depends(rate_limit_standard)
):
    """List snapshots visibles para el usuario actual.

    La regla aquí es determinista: admin ve todo su tenant; el resto
    solo ve lo propio. No se mezclan visibilidad pública ni heurísticas
    para no abrir fugas entre tenants.
    """
    if current_user.tier == "admin":
        stmt = select(Snapshot).where(Snapshot.tenant_id == current_user.tenant_id)
    else:
        stmt = select(Snapshot).where(
            Snapshot.tenant_id == current_user.tenant_id,
            Snapshot.user_id == current_user.id,
        )
    result = await db.execute(stmt.order_by(Snapshot.created_at.desc()))
    items = result.scalars().all()

    return [_to_response(s) for s in items]


@router.get("/{snapshot_id}", response_model=SnapshotResponse)
async def get_snapshot(
    snapshot_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db), _rate_limit: bool = Depends(rate_limit_standard)
):
    """Get a specific snapshot -- ahora SÍ valida tenant/ownership."""
    if current_user.tier == "admin":
        stmt = select(Snapshot).where(
            Snapshot.id == snapshot_id,
            Snapshot.tenant_id == current_user.tenant_id,
        )
    else:
        stmt = select(Snapshot).where(
            Snapshot.id == snapshot_id,
            Snapshot.tenant_id == current_user.tenant_id,
            Snapshot.user_id == current_user.id,
        )
    result = await db.execute(stmt)
    snapshot = result.scalar_one_or_none()
    if not snapshot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot not found")

    return _to_response(snapshot)


@router.post("/create", response_model=SnapshotResponse)
async def create_snapshot(
    req: SnapshotCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db), _rate_limit: bool = Depends(rate_limit_strict)
):
    """Create a new snapshot, asociado al tenant del usuario actual."""
    snapshot = Snapshot(
        name=req.name,
        description=req.description,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        layers=req.layers,
        viewport=req.viewport
    )
    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)

    return _to_response(snapshot)


@router.delete("/{snapshot_id}")
async def delete_snapshot(
    snapshot_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db), _rate_limit: bool = Depends(rate_limit_strict)
):
    """Delete a snapshot (owner o admin -- del MISMO tenant)."""
    result = await db.execute(
        select(Snapshot).where(Snapshot.id == snapshot_id, Snapshot.tenant_id == current_user.tenant_id)
    )
    snapshot = result.scalar_one_or_none()
    if not snapshot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot not found")

    if snapshot.tenant_id != current_user.tenant_id:
        # Ni siquiera admin cruza de tenant.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot not found")

    if snapshot.user_id != current_user.id and current_user.tier != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this snapshot")

    await db.delete(snapshot)
    await db.commit()

    return {"status": "deleted", "id": snapshot_id}
