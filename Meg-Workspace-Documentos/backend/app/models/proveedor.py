# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Modelos de proveedores, licitantes y contratistas.
"""
from enum import Enum
from uuid import uuid4
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, Boolean, ForeignKey, Index
from app.db.types import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, TenantMixin, AuditMixin

if TYPE_CHECKING:
    from app.models.compliance import Sancion
    from app.models.contrato import Contrato
    from app.models.licitacion import Proposicion


class TipoPersona(str, Enum):
    FISICA = "FISICA"
    MORAL = "MORAL"
    CONSORCIO = "CONSORCIO"


class EstadoProveedor(str, Enum):
    ACTIVO = "ACTIVO"
    INACTIVO = "INACTIVO"
    BLOQUEADO = "BLOQUEADO"
    SANCIONADO = "SANCIONADO"


class Proveedor(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Proveedor / licitante / contratista."""
    __tablename__ = "proveedores"
    __table_args__ = (Index("uq_proveedores_tenant_rfc", "tenant_id", "rfc", unique=True),)

    tipo_persona: Mapped[TipoPersona] = mapped_column(String(50), nullable=False)
    rfc: Mapped[str] = mapped_column(String(13), nullable=False)
    razon_social: Mapped[str] = mapped_column(String(500), nullable=False)
    nombre_comercial: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Contacto
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telefono: Mapped[str | None] = mapped_column(String(50), nullable=True)
    direccion: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Estado
    estado: Mapped[EstadoProveedor] = mapped_column(String(50), default=EstadoProveedor.ACTIVO, index=True)

    # Documentos fiscales
    constancia_fiscal: Mapped[str | None] = mapped_column(String(500), nullable=True)
    acta_constitutiva: Mapped[str | None] = mapped_column(String(500), nullable=True)
    poder_notarial: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Capacidades
    capacidad_ejecucion: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    especialidades: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Relaciones
    representantes: Mapped[list["RepresentanteLegal"]] = relationship("RepresentanteLegal", back_populates="proveedor")
    proposiciones: Mapped[list["Proposicion"]] = relationship("Proposicion", back_populates="proveedor")
    sanciones: Mapped[list["Sancion"]] = relationship("Sancion", back_populates="proveedor")
    contratos: Mapped[list["Contrato"]] = relationship("Contrato", back_populates="proveedor")


class RepresentanteLegal(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Representante legal de un proveedor."""
    __tablename__ = "representantes_legales"

    proveedor_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("proveedores.id", ondelete="CASCADE"), nullable=False
    )

    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    curp: Mapped[str | None] = mapped_column(String(18), nullable=True)
    rfc: Mapped[str | None] = mapped_column(String(13), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telefono: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # e.firma
    efirma_serial: Mapped[str | None] = mapped_column(String(255), nullable=True)
    efirma_vigencia_inicio: Mapped[str | None] = mapped_column(String(10), nullable=True)
    efirma_vigencia_fin: Mapped[str | None] = mapped_column(String(10), nullable=True)
    efirma_activa: Mapped[bool] = mapped_column(default=False)

    proveedor: Mapped["Proveedor"] = relationship("Proveedor", back_populates="representantes")
