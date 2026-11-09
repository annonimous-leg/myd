"""Administrative user API owned by MEGALODON IAM."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, oauth2_scheme
from app.config import settings
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from app.models.user import User, UserRole, Tenant
from app.services.identity_service import IdentityService, ADMIN_ROLES, role_value, user_view

router = APIRouter()


class UserUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: UserRole | None = None
    is_active: StrictBool | None = None
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_change(self):
        self.reason = self.reason.strip()
        if not self.reason or not (self.model_fields_set & {"role", "is_active"}):
            raise ValueError("Indicar cambio y motivo")
        for field in self.model_fields_set & {"role", "is_active"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} no admite null")
        return self


async def require_tenant_admin(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> User:
    if role_value(user) not in ADMIN_ROLES or not user.is_active:
        raise HTTPException(403, "Se requiere un administrador activo")
    tenant = await db.get(Tenant, user.tenant_id)
    if not tenant or not tenant.is_active:
        raise HTTPException(403, "Organización inactiva")
    return user


@router.get("")
async def list_users(
    admin: User = Depends(require_tenant_admin), db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
    _rate_limit: bool = Depends(rate_limit_standard),
):
    rows = await db.scalars(select(User).where(User.tenant_id == admin.tenant_id)
                            .order_by(User.created_at, User.id).offset(skip).limit(limit))
    return [user_view(user) for user in rows]


async def verify_browser_origin(request: Request, token: str | None = Depends(oauth2_scheme)):
    # Explicit credentials are not automatically attached by a hostile page.
    if token:
        return
    origins = list(request.headers.getlist("origin"))
    trusted = set(settings.CORS_ALLOWED_ORIGINS)
    trusted.add(f"{request.url.scheme}://{request.url.netloc}")
    if len(origins) != 1 or origins[0] == "null" or origins[0] not in trusted:
        raise HTTPException(403, "Origen de la operación no autorizado")


@router.patch("/{user_id}", dependencies=[Depends(verify_browser_origin)])
async def update_user(
    user_id: UUID, req: UserUpdateRequest, request: Request,
    admin: User = Depends(require_tenant_admin), db: AsyncSession = Depends(get_db),
    _rate_limit: bool = Depends(rate_limit_strict),
):
    user = await IdentityService(db).update_user(
        actor=admin, user_id=user_id, role=req.role, is_active=req.is_active,
        reason=req.reason, ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent", "")[:500],
    )
    return user_view(user)
