"""Settings Router - Configuración del sistema."""
from core.rate_limit import rate_limit_standard, rate_limit_strict
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.models import SystemSetting, User, get_async_db
from routers.auth import require_role

router = APIRouter(tags=["settings"])


def _tenant_id(current_user: User) -> str:
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El usuario autenticado no tiene tenant asignado.",
        )
    return tenant_id


def _normalize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if "settings" in payload and len(payload) == 1 and isinstance(payload["settings"], dict):
        return payload["settings"]
    return payload


async def _read_settings(
    db: AsyncSession, tenant_id: str, *, include_global: bool = False
) -> Dict[str, Any]:
    """Lee configuración del tenant; sólo el superadmin puede ver defaults globales."""
    merged: Dict[str, Any] = {}

    if include_global:
        result = await db.execute(
            select(SystemSetting).where(SystemSetting.tenant_id.is_(None))
        )
        for row in result.scalars().all():
            merged[row.key] = row.value

    # Las preferencias del tenant nunca requieren ni heredan lectura de secretos globales.
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.tenant_id == tenant_id)
    )
    for row in result.scalars().all():
        merged[row.key] = row.value

    return merged


@router.get("/")
async def get_settings(
    request: Request,
    current_user: User = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: bool = Depends(rate_limit_standard),
):
    tenant_id = _tenant_id(current_user)
    return {
        "tenant_id": tenant_id,
        "settings": await _read_settings(
            db, tenant_id, include_global=getattr(request.state, "role", None) == "superadmin"
        ),
    }


@router.post("/")
async def update_settings(
    payload: Dict[str, Any],
    current_user: User = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: bool = Depends(rate_limit_strict),
):
    tenant_id = _tenant_id(current_user)
    data = _normalize_payload(payload)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Se esperaba un objeto con claves de configuración.",
        )

    changed: Dict[str, Any] = {}
    for key, value in data.items():
        if not isinstance(key, str) or not key.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Clave de configuración inválida: {key!r}",
            )

        result = await db.execute(
            select(SystemSetting).where(
                SystemSetting.tenant_id == tenant_id,
                SystemSetting.key == key
            )
        )
        setting = result.scalar_one_or_none()

        if setting is None:
            setting = SystemSetting(tenant_id=tenant_id, key=key, value=value)
            db.add(setting)
        else:
            setting.value = value

    await db.commit()
    return {
        "status": "updated",
        "tenant_id": tenant_id,
        "settings": changed | data,
    }


@router.delete("/{key}")
async def delete_setting(
    key: str,
    current_user: User = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: bool = Depends(rate_limit_strict),
):
    tenant_id = _tenant_id(current_user)

    # Buscar en tenant primero
    result = await db.execute(
        select(SystemSetting).where(
            SystemSetting.tenant_id == tenant_id,
            SystemSetting.key == key
        )
    )
    setting = result.scalar_one_or_none()

    if setting is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe la configuración '{key}'.",
        )

    await db.delete(setting)
    await db.commit()
    return {
        "status": "deleted",
        "tenant_id": tenant_id,
        "key": key,
    }
