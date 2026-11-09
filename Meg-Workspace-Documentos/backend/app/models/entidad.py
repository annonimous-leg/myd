# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Modelos de entidades, dependencias y unidades administrativas.
"""
from uuid import uuid4

from sqlalchemy import String, Text, ForeignKey, Index
from app.db.types import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, AuditMixin


class Entidad(Base, UUIDMixin, AuditMixin):
    """Entidad / Dependencia / Organismo."""
    __tablename__ = "entidades"

    clave: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(500), nullable=False)
    nombre_corto: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # FEDERAL, ESTATAL, MUNICIPAL, ORGANISMO

    # Contacto
    direccion: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telefono: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Configuración
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    branding: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relaciones
    unidades: Mapped[list["UnidadAdministrativa"]] = relationship("UnidadAdministrativa", back_populates="entidad")


class UnidadAdministrativa(Base, UUIDMixin, AuditMixin):
    """Unidad administrativa / área requirente / área contratante."""
    __tablename__ = "unidades_administrativas"

    entidad_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entidades.id", ondelete="CASCADE"), nullable=False, index=True
    )

    clave: Mapped[str] = mapped_column(String(50), nullable=False)
    nombre: Mapped[str] = mapped_column(String(500), nullable=False)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # REQUIRENTE, CONTRATANTE, CONTROL

    responsable_nombre: Mapped[str | None] = mapped_column(String(255), nullable=True)
    responsable_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    entidad: Mapped["Entidad"] = relationship("Entidad", back_populates="unidades")

    __table_args__ = (
        Index("ix_unidad_entidad_clave", "entidad_id", "clave", unique=True),
    )
