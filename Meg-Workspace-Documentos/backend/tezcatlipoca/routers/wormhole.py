"""Wormhole Router - Secure data bridges and tunneling.

Endpoints for:
- Encrypted tunnel management
- Dead drop messaging
- Secure file transfer
- Bridge status and health

SECURITY: All endpoints require authentication and are scoped by
tenant (decisión de producto, Fase 2: recursos de Tezcatlipoca son por
tenant de Megalodon).

FASE 3 (2026-08-02) -- qué cambió respecto a la versión anterior:
  1. _tunnels/_dead_drops eran dicts en memoria del proceso: se perdían
     en cada reinicio, sin tenant. Ahora son tablas Tunnel/DeadDrop en
     la misma base de datos (ver db/models.py).
  2. BUG REAL encontrado: create_dead_drop() solo guardaba
     sha256(payload) -- get_dead_drop() jamás podía devolver el
     mensaje original, nunca. El feature de "dead drop messaging" no
     funcionaba. Ahora el payload se cifra con Fernet (services/crypto.py,
     clave derivada de SECRET_KEY) y SÍ se puede recuperar hasta
     agotar max_reads o expirar -- momento en el que se borra de la
     fila (no solo se marca expirado), para preservar la propiedad de
     "secreto que desaparece" incluso con persistencia en Postgres.
  3. Todas las verificaciones de "owner o admin" ahora primero exigen
     que el recurso sea del MISMO tenant -- ni siquiera un admin ve
     tuneles/dead-drops de otro tenant. 404 en vez de 403 cuando el
     tenant no coincide, para no confirmar que el ID existe en otro lado.
"""
from core.rate_limit import rate_limit_standard, rate_limit_strict

from fastapi import APIRouter, HTTPException, Depends, Request, status
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
import secrets
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from cryptography.fernet import InvalidToken

from db.models import get_async_db, User, Tunnel, DeadDrop
from routers.auth import get_current_user, require_role
from app.core.entitlements import PlanTipo, requiere_plan_minimo
from services.crypto import encrypt_payload, decrypt_payload

router = APIRouter(tags=["wormhole"])


# ─── Pydantic Models ───

class TunnelCreateRequest(BaseModel):
    destination: str = Field(..., min_length=1, max_length=512, pattern=r"^[a-zA-Z0-9\.\-_/:]+$")
    encryption: str = Field(default="aes-256-gcm", pattern=r"^(aes-256-gcm|chacha20-poly1305|none)$")
    ttl_minutes: int = Field(default=60, ge=1, le=1440)

class DeadDropCreateRequest(BaseModel):
    payload: str = Field(..., min_length=1, max_length=65536)
    ttl_minutes: int = Field(default=60, ge=1, le=1440)
    max_reads: int = Field(default=1, ge=1, le=100)

class TunnelResponse(BaseModel):
    tunnel_id: str
    status: str
    expires_in: str
    connect_url: str


def _tunnel_to_dict(t: Tunnel) -> dict:
    return {
        "id": t.id,
        "destination": t.destination,
        "encryption": t.encryption,
        "created_at": t.created_at.isoformat(),
        "expires_at": t.expires_at.isoformat(),
        "status": t.status,
        "bytes_transferred": t.bytes_transferred,
        "packets": t.packets,
        "latency_ms": t.latency_ms,
        "owner": t.owner_username,
    }


def _same_tenant_or_404(resource_tenant_id: str, current_user: User):
    if resource_tenant_id != current_user.tenant_id:
        # 404, no 403: no confirmamos si el ID existe en otro tenant.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")


def _owner_or_admin_or_403(owner_user_id: int, current_user: User):
    if owner_user_id != current_user.id and current_user.tier != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")


# ─── Tunnel Endpoints ───

@router.post("/tunnel/create", response_model=TunnelResponse)
async def create_tunnel(
    req: TunnelCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db), _rate_limit: bool = Depends(rate_limit_strict)
):
    """Create an encrypted tunnel to a destination. (Auth required)"""
    tunnel_id = secrets.token_urlsafe(16)
    now = datetime.now(timezone.utc)

    tunnel = Tunnel(
        id=tunnel_id,
        tenant_id=current_user.tenant_id,
        owner_user_id=current_user.id,
        owner_username=current_user.username,
        destination=req.destination,
        encryption=req.encryption,
        status="active",
        created_at=now,
        expires_at=now + timedelta(minutes=req.ttl_minutes),
    )
    db.add(tunnel)
    await db.commit()

    return TunnelResponse(
        tunnel_id=tunnel_id,
        status="created",
        expires_in=f"{req.ttl_minutes}m",
        connect_url=f"wormhole://localhost:8000/tunnel/{tunnel_id}"
    )


@router.get("/tunnel/{tunnel_id}")
async def get_tunnel(
    tunnel_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db), _rate_limit: bool = Depends(rate_limit_standard)
):
    """Get tunnel status and statistics. (Auth required, same tenant)"""
    result = await db.execute(select(Tunnel).where(Tunnel.id == tunnel_id))
    tunnel = result.scalar_one_or_none()
    if not tunnel:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tunnel not found")

    _same_tenant_or_404(tunnel.tenant_id, current_user)
    _owner_or_admin_or_403(tunnel.owner_user_id, current_user)

    if datetime.now(timezone.utc) > tunnel.expires_at.replace(tzinfo=timezone.utc):
        tunnel.status = "expired"
        await db.commit()

    return _tunnel_to_dict(tunnel)


@router.post("/tunnel/{tunnel_id}/close")
async def close_tunnel(
    tunnel_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db), _rate_limit: bool = Depends(rate_limit_strict)
):
    """Close an active tunnel. (Auth required - owner or admin, same tenant)"""
    result = await db.execute(select(Tunnel).where(Tunnel.id == tunnel_id))
    tunnel = result.scalar_one_or_none()
    if not tunnel:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tunnel not found")

    _same_tenant_or_404(tunnel.tenant_id, current_user)
    _owner_or_admin_or_403(tunnel.owner_user_id, current_user)

    tunnel.status = "closed"
    tunnel.closed_at = datetime.now(timezone.utc)
    await db.commit()

    return {"status": "closed", "tunnel_id": tunnel_id}


@router.get("/tunnels")
async def list_tunnels(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db), _rate_limit: bool = Depends(rate_limit_standard)
):
    """List tunnels visibles para el tenant del usuario actual."""
    stmt = select(Tunnel).where(Tunnel.tenant_id == current_user.tenant_id)
    if current_user.tier != "admin":
        stmt = stmt.where(Tunnel.owner_user_id == current_user.id)
    stmt = stmt.order_by(Tunnel.created_at.desc())
    result = await db.execute(stmt)
    tunnels = result.scalars().all()
    return {"tunnels": [_tunnel_to_dict(t) for t in tunnels]}


# ─── Dead Drop Endpoints ───

@router.post("/dead-drop/create")
async def create_dead_drop(
    req: DeadDropCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db), _rate_limit: bool = Depends(rate_limit_strict)
):
    """Create a secure dead drop message. (Auth required)

    El payload se cifra antes de guardarse (ver services/crypto.py).
    Antes de este cambio solo se guardaba un hash y el mensaje real era
    irrecuperable -- ver nota al inicio del archivo.
    """
    drop_id = secrets.token_urlsafe(16)
    now = datetime.now(timezone.utc)

    dead_drop = DeadDrop(
        id=drop_id,
        tenant_id=current_user.tenant_id,
        owner_user_id=current_user.id,
        owner_username=current_user.username,
        encrypted_payload=encrypt_payload(req.payload),
        created_at=now,
        expires_at=now + timedelta(minutes=req.ttl_minutes),
        max_reads=req.max_reads,
        reads=0,
        status="active",
    )
    db.add(dead_drop)
    await db.commit()

    return {
        "drop_id": drop_id,
        "status": "created",
        "expires_in": f"{req.ttl_minutes}m",
        "max_reads": req.max_reads
    }


@router.get("/dead-drop/{drop_id}")
async def get_dead_drop(
    drop_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db), _rate_limit: bool = Depends(rate_limit_standard)
):
    """Retrieve a dead drop message. (Auth required - owner or admin, same tenant)

    Devuelve el payload real (descifrado), no un hash -- ver nota al
    inicio del archivo sobre el bug que tenía la versión anterior.
    """
    result = await db.execute(select(DeadDrop).where(DeadDrop.id == drop_id))
    dead_drop = result.scalar_one_or_none()
    if not dead_drop:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dead drop not found")

    _same_tenant_or_404(dead_drop.tenant_id, current_user)
    _owner_or_admin_or_403(dead_drop.owner_user_id, current_user)

    if datetime.now(timezone.utc) > dead_drop.expires_at.replace(tzinfo=timezone.utc):
        dead_drop.status = "expired"
        dead_drop.encrypted_payload = None  # se borra de verdad, no solo se marca
        await db.commit()
        raise HTTPException(410, "Dead drop has expired")

    if dead_drop.reads >= dead_drop.max_reads or dead_drop.encrypted_payload is None:
        dead_drop.status = "consumed"
        dead_drop.encrypted_payload = None
        await db.commit()
        raise HTTPException(410, "Dead drop has been consumed")

    try:
        payload = decrypt_payload(dead_drop.encrypted_payload)
    except InvalidToken:
        # SECRET_KEY rotó desde que se creó, o el dato está corrupto.
        dead_drop.status = "unavailable"
        dead_drop.encrypted_payload = None
        await db.commit()
        raise HTTPException(410, "Dead drop is no longer decryptable (secret rotated)")

    dead_drop.reads += 1
    if dead_drop.reads >= dead_drop.max_reads:
        dead_drop.status = "consumed"
        dead_drop.encrypted_payload = None  # se borra al agotar lecturas
    await db.commit()

    return {
        "drop_id": drop_id,
        "status": dead_drop.status,
        "reads": dead_drop.reads,
        "max_reads": dead_drop.max_reads,
        "payload": payload,
    }


@router.get("/dead-drops")
async def list_dead_drops(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db), _rate_limit: bool = Depends(rate_limit_standard)
):
    """List dead drops visibles para el tenant (sin exponer payload)."""
    stmt = select(DeadDrop).where(DeadDrop.tenant_id == current_user.tenant_id)
    if current_user.tier != "admin":
        stmt = stmt.where(DeadDrop.owner_user_id == current_user.id)
    stmt = stmt.order_by(DeadDrop.created_at.desc())
    result = await db.execute(stmt)
    items = result.scalars().all()
    return {
        "dead_drops": [
            {
                "id": d.id,
                "status": d.status,
                "reads": d.reads,
                "max_reads": d.max_reads,
                "created_at": d.created_at.isoformat(),
                "expires_at": d.expires_at.isoformat(),
                "owner": d.owner_username,
            }
            for d in items
        ]
    }


@router.get("/health")
async def health(db: AsyncSession = Depends(get_async_db), _rate_limit: bool = Depends(rate_limit_standard)):
    """Public health check endpoint."""
    result = await db.execute(select(func.count()).select_from(Tunnel).where(Tunnel.status == "active"))
    active_tunnels = result.scalar()
    result = await db.execute(select(func.count()).select_from(DeadDrop).where(DeadDrop.status == "active"))
    active_drops = result.scalar()
    return {
        "status": "healthy",
        "active_tunnels": active_tunnels,
        "active_drops": active_drops,
    }
