"""Tenant user administration against the authoritative identity database."""
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole, Tenant
from app.models.audit_ledger import TipoAccion
from app.modules.audit.service import AuditService


ADMIN_ROLES = {UserRole.ADMIN.value, UserRole.SUPERADMIN.value}


def role_value(user: User) -> str:
    return user.role.value if isinstance(user.role, UserRole) else str(user.role)


def user_view(user: User) -> dict:
    return {
        "id": str(user.id), "email": user.email, "full_name": user.full_name,
        "role": role_value(user), "is_active": user.is_active,
        "created_at": user.created_at.isoformat(),
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }


class IdentityService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def update_user(self, *, actor: User, user_id: UUID,
                          role: UserRole | None, is_active: bool | None,
                          reason: str, ip_address: str | None = None,
                          user_agent: str | None = None) -> User:
        # Serialize administrators of one organization before loading actors
        # and targets again: permission checks must see committed changes,
        # including an administrator disabled by a concurrent request.
        tenant_id, actor_id = actor.tenant_id, actor.id
        try:
            tenant = await self.db.scalar(
                select(Tenant).where(Tenant.id == tenant_id)
                .with_for_update(key_share=True)
                .execution_options(populate_existing=True)
            )
            if not tenant or not tenant.is_active:
                raise HTTPException(403, "Organización inactiva")
            actor = await self.db.scalar(
                select(User).where(User.id == actor_id, User.tenant_id == tenant_id)
                .with_for_update(key_share=True)
                .execution_options(populate_existing=True)
            )
            if not actor or not actor.is_active or role_value(actor) not in ADMIN_ROLES:
                raise HTTPException(403, "Se requiere un administrador activo")
            target = await self.db.scalar(
                select(User).where(User.id == user_id, User.tenant_id == tenant_id)
                .with_for_update(key_share=True)
                .execution_options(populate_existing=True)
            )
            if not target:
                raise HTTPException(404, "Usuario no encontrado")
            if role_value(target) == UserRole.SUPERADMIN.value or role == UserRole.SUPERADMIN:
                raise HTTPException(403, "Los privilegios de plataforma no se administran desde un tenant")
            before = {"role": role_value(target), "is_active": target.is_active}
            after = {"role": role.value if role is not None else before["role"],
                     "is_active": is_active if is_active is not None else before["is_active"]}
            if before == after:
                await self.db.commit()
                return target
            if target.id == actor.id:
                raise HTTPException(403, "Otro administrador debe cambiar tu rol o estado")
            if before["role"] == UserRole.ADMIN.value and before["is_active"] and (
                after["role"] != UserRole.ADMIN.value or not after["is_active"]
            ):
                remaining = await self.db.scalar(select(func.count()).select_from(User).where(
                    User.tenant_id == tenant_id, User.id != target.id,
                    User.is_active.is_(True), User.role == UserRole.ADMIN.value,
                ))
                if not remaining:
                    raise HTTPException(409, "La organización debe conservar un administrador activo")
            target.role, target.is_active = after["role"], after["is_active"]
            # Access and refresh tokens include this version. Increasing it in
            # the same transaction prevents old sessions returning on re-enable.
            target.auth_version += 1
            await AuditService(self.db).registrar_accion(
                user_id=actor.id, user_email=actor.email, user_role=role_value(actor),
                tenant_id=tenant_id, entidad_tipo="USUARIO", entidad_id=str(target.id),
                accion=TipoAccion.MODIFICAR, descripcion=reason,
                datos_anteriores=before, datos_nuevos=after,
                ip_address=ip_address, user_agent=user_agent, commit=False,
            )
            await self.db.commit()
            return target
        except Exception:
            await self.db.rollback()
            raise
