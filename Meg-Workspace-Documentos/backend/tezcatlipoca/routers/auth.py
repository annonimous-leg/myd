"""Identidad de Tezcatlipoca: MEGALODON es la única autoridad de sesiones.

El espejo conserva claves locales de recursos y auditoría, nunca credenciales.
Login, refresh y logout pertenecen exclusivamente a /api/v1/auth.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.deps import get_db as megalodon_get_db
from app.api.v1.users import require_tenant_admin
from app.models.user import User as MegalodonUser
from core.rate_limit import rate_limit_standard
from core.megalodon_bridge import attach_identity, load_megalodon_user, sync_shadow_user
from db.models import get_async_db, User

router = APIRouter(tags=["identity"])
security_bearer = HTTPBearer(auto_error=False)

class UserResponse(BaseModel):
    username: str
    tier: str
    created_at: str
    api_calls_total: int

async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security_bearer),
    megalodon_db: AsyncSession = Depends(megalodon_get_db),
    shadow_db: AsyncSession = Depends(get_async_db),
) -> User:
    """Autentica con Megalodon y mantiene un espejo local mínimo.

    Todo request de datos/operaciones de Tezcatlipoca debe pertenecer a un
    tenant de Megalodon. Los datasets públicos siguen siendo globales como
    dato de origen, pero la consulta, cuota, auditoría y cualquier resultado
    persistido quedan bajo el contexto del tenant.
    """
    megalodon_user = await load_megalodon_user(request, credentials, megalodon_db)
    if not getattr(megalodon_user, "tenant_id", None):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El usuario autenticado no tiene tenant activo.",
        )
    user = await sync_shadow_user(shadow_db, megalodon_user)
    attach_identity(request, megalodon_user, user)
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

def require_role(roles: list):
    """Dependency factory to require specific user roles."""
    async def _check_role(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_async_db)
    ):
        if current_user.tier not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required role: one of {roles}"
            )
        return current_user
    return _check_role

@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db), _rate_limit: bool = Depends(rate_limit_standard)):
    """Get current authenticated user information."""
    return UserResponse(
        username=current_user.username,
        tier=current_user.tier,
        created_at=current_user.created_at.isoformat(),
        api_calls_total=current_user.api_calls_total
    )


@router.get("/users/count")
async def get_user_count(
    current_user: MegalodonUser = Depends(require_tenant_admin),
    db: AsyncSession = Depends(megalodon_get_db),
    _rate_limit: bool = Depends(rate_limit_standard),
):
    """Count authoritative tenant identities, including users without a mirror."""
    count = await db.scalar(select(func.count()).select_from(MegalodonUser).where(
        MegalodonUser.tenant_id == current_user.tenant_id))
    return {"total_users": count}
