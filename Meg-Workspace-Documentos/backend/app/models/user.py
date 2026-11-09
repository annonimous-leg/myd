# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Modelos de usuario y autenticación.
"""
from datetime import datetime
from enum import Enum
from uuid import uuid4
from typing import TYPE_CHECKING

from sqlalchemy import String, Boolean, DateTime, ForeignKey, Index, Integer
from app.db.types import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, TenantMixin

if TYPE_CHECKING:
    from app.models.expediente import ExpedienteObra


class UserRole(str, Enum):
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    TECNICO = "tecnico"
    REVISOR = "revisor"
    LECTOR = "lector"
    INVITADO = "invitado"


class User(Base, UUIDMixin, TenantMixin):
    """Usuario del sistema."""
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    rfc: Mapped[str | None] = mapped_column(String(13), nullable=True, index=True)
    curp: Mapped[str | None] = mapped_column(String(18), nullable=True)
    role: Mapped[UserRole] = mapped_column(String(50), default=UserRole.TECNICO)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    auth_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relaciones
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="users")
    expedientes: Mapped[list["ExpedienteObra"]] = relationship(
        "ExpedienteObra",
        back_populates="responsable_user",
        foreign_keys="ExpedienteObra.responsable_id",
    )


class Tenant(Base, UUIDMixin):
    """Organización / Tenant multi-tenant."""
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    rfc: Mapped[str | None] = mapped_column(String(13), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    settings: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    # Plan efectivo actual (ver app.services.entitlements_service.
    # obtener_plan_efectivo, que además revisa plan_vencimiento -- si ya
    # venció, el plan efectivo es FREE aunque esta columna diga otra cosa
    # hasta que un job/consulta la corrija). Suscripcion (app/models/
    # entitlements.py) es el historial completo y auditable; esto es solo
    # la vista rápida para no tener que hacer join en cada request.
    plan: Mapped[str] = mapped_column(String(20), default="FREE", nullable=False, index=True)
    plan_vencimiento: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relaciones
    users: Mapped[list["User"]] = relationship("User", back_populates="tenant")
    expedientes: Mapped[list["ExpedienteObra"]] = relationship(
        "ExpedienteObra", back_populates="tenant"
    )


class InvitationStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"


class Invitation(Base, UUIDMixin, TenantMixin):
    """Invitación para unirse a un tenant existente con un rol fijo.

    SEGURIDAD (cierre de auditoría, punto B): el registro público
    (`POST /auth/register`) YA NO acepta `tenant_id`/`role` arbitrarios
    del cliente -- eso permitía que cualquiera con un UUID de tenant se
    uniera a una organización ajena y hasta se autoasignara admin.
    Ahora la ÚNICA forma de entrar a un tenant EXISTENTE es canjeando
    una invitación creada por un admin de ese tenant: el email, el rol
    y el tenant_id del usuario resultante salen de esta tabla, nunca
    del body que manda el cliente en /register/invite.

    Solo se persiste el hash (sha256) del token -- igual que los
    tokens legacy en api/v1/auth.py -- para que una fuga de la base de
    datos no entregue invitaciones canjeables directamente.
    """
    __tablename__ = "invitations"

    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    invited_by: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default=InvitationStatus.PENDING, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_invitations_tenant_email_status", "tenant_id", "email", "status"),
    )
