"""Puente de identidad y contexto SaaS entre Megalodon y Tezcatlipoca.

Este módulo evita duplicar autenticación, tenant resolution y shadow users.
La fuente de verdad es Megalodon; Tezcatlipoca solo materializa un espejo
local para auditoría y relaciones históricas que todavía dependen de una PK
entera local.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.errors import MegalodonException
from app.models.user import Tenant as MegalodonTenant
from app.models.user import User as MegalodonUser
from app.services.auth_service import AuthService as MegalodonAuthService
from db.models import User as ShadowUser


MEGALODON_SESSION_COOKIE = "megalodon_session"
MEGALODON_REFRESH_COOKIE = "megalodon_refresh_token"

ROLE_TO_TIER = {
    "superadmin": "admin",
    "admin": "admin",
    "tecnico": "full",
    "revisor": "restricted",
    "lector": "restricted",
    "invitado": "restricted",
}


@dataclass(slots=True)
class IdentityContext:
    """Contexto de identidad resuelto desde Megalodon."""

    megalodon_user: MegalodonUser
    shadow_user: ShadowUser
    tenant_plan: Optional[str] = None


def extract_bearer_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = None,
) -> Optional[str]:
    """Obtiene el token de sesión unificado sin inventar credenciales nuevas.

    La cabecera Authorization tiene prioridad sobre la cookie para que
    llamadas explícitas con Bearer no sean pisadas por una sesión previa
    del mismo cliente HTTP. La cookie queda como respaldo para el flujo
    web normal.
    """
    if credentials and credentials.credentials:
        return credentials.credentials
    return request.cookies.get(MEGALODON_SESSION_COOKIE)


def _raise_http_from_megalodon(exc: Exception) -> None:
    """Convierte errores de Megalodon a HTTPException estable."""
    status_code = getattr(exc, "status_code", status.HTTP_401_UNAUTHORIZED)
    detail = getattr(exc, "message", None) or str(exc) or "Authentication failed"
    raise HTTPException(status_code=status_code, detail=detail, headers={"WWW-Authenticate": "Bearer"})


async def load_megalodon_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials],
    megalodon_db: AsyncSession,
) -> MegalodonUser:
    """Valida el token usando la fuente de verdad de Megalodon."""
    token = extract_bearer_token(request, credentials)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return await MegalodonAuthService(megalodon_db).get_current_user_from_token(token)
    except MegalodonException as exc:
        _raise_http_from_megalodon(exc)


async def sync_shadow_user(
    shadow_db: AsyncSession,
    megalodon_user: MegalodonUser,
) -> ShadowUser:
    """Crea/actualiza el espejo local sin convertirlo en fuente de verdad."""
    megalodon_user_id = str(megalodon_user.id)
    tenant_id = str(megalodon_user.tenant_id) if megalodon_user.tenant_id else None
    role_value = getattr(megalodon_user.role, "value", str(megalodon_user.role)).lower()
    tier = ROLE_TO_TIER.get(role_value, "restricted")

    result = await shadow_db.execute(
        select(ShadowUser).where(ShadowUser.megalodon_user_id == megalodon_user_id)
    )
    shadow_user = result.scalar_one_or_none()

    if shadow_user is None:
        shadow_user = ShadowUser(
            username=megalodon_user.email or megalodon_user_id,
            password_hash="",
            tier=tier,
            megalodon_user_id=megalodon_user_id,
            tenant_id=tenant_id,
            is_active=True,
        )
        shadow_db.add(shadow_user)
    else:
        shadow_user.username = megalodon_user.email or shadow_user.username
        shadow_user.tier = tier
        shadow_user.tenant_id = tenant_id
        shadow_user.is_active = True

    shadow_user.last_login = datetime.now(timezone.utc)
    await shadow_db.commit()
    await shadow_db.refresh(shadow_user)
    return shadow_user


async def load_tenant_plan(
    megalodon_db: AsyncSession,
    tenant_id: str | None,
) -> Optional[str]:
    """Lee el plan efectivo del tenant desde Megalodon para gates SaaS."""
    if not tenant_id:
        return None

    result = await megalodon_db.execute(
        select(MegalodonTenant).where(MegalodonTenant.id == tenant_id)
    )
    tenant = result.scalar_one_or_none()
    return getattr(tenant, "plan", None) if tenant else None


def attach_identity(request: Request, megalodon_user: MegalodonUser, shadow_user: ShadowUser) -> None:
    """Propaga el contexto resolvido a request.state para auditoría y trazabilidad."""
    request.state.megalodon_user_id = str(megalodon_user.id)
    request.state.user_id = shadow_user.id
    request.state.username = shadow_user.username
    request.state.tenant_id = str(megalodon_user.tenant_id) if megalodon_user.tenant_id else None
    request.state.role = getattr(megalodon_user.role, "value", str(megalodon_user.role))
    request.state.tier = shadow_user.tier
    request.state.email = megalodon_user.email
