"""Shared actor policy for HTTP adapters and domain commands.

Resource ownership remains a scoped domain query; a role never grants access
to another tenant. Internal commands resolve the persisted actor explicitly.
"""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode, MegalodonException
from app.models.user import Tenant, User

WRITE_ROLES = frozenset({'superadmin', 'admin', 'tecnico', 'revisor'})
APPROVAL_ROLES = frozenset({'superadmin', 'admin', 'revisor'})
ACTION_ROLES = {'write': WRITE_ROLES, 'approve': APPROVAL_ROLES}


def authorize(user: User, action: str = 'write', *, tenant_id: UUID | None = None) -> None:
    roles = ACTION_ROLES.get(action, frozenset())
    if (not user.is_active or not user.tenant_id or user.role not in roles
            or (tenant_id is not None and str(user.tenant_id) != str(tenant_id))):
        raise MegalodonException(ErrorCode.PERMISO_DENEGADO,
            'El actor no tiene permiso para esta operación', status_code=403)


async def authorize_by_id(db: AsyncSession, actor_id: UUID | None, tenant_id: UUID | None,
                          action: str = 'write') -> User:
    if actor_id is None or tenant_id is None:
        raise MegalodonException(ErrorCode.PERMISO_DENEGADO,
            'La operación requiere actor y organización explícitos', status_code=403)
    user = await db.scalar(select(User).join(Tenant, Tenant.id == User.tenant_id).where(
        User.id == actor_id, User.tenant_id == tenant_id, Tenant.is_active.is_(True)
    ).execution_options(populate_existing=True))
    if user is None:
        raise MegalodonException(ErrorCode.PERMISO_DENEGADO,
            'Actor u organización no disponibles', status_code=403)
    authorize(user, action, tenant_id=tenant_id)
    return user
