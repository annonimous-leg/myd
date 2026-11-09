# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Modelos de catálogo de Análisis de Precios Unitarios (APU).
"""
from enum import Enum
from uuid import uuid4

from sqlalchemy import UniqueConstraint, String, Numeric, ForeignKey, ForeignKeyConstraint, Index, Text
from app.db.types import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, TenantMixin, AuditMixin


class TipoConceptoAPU(str, Enum):
    CONCEPTO = "CONCEPTO"
    MATERIAL = "MATERIAL"
    MANO_OBRA = "MANO_OBRA"
    MAQUINARIA = "MAQUINARIA"
    HERRAMIENTA = "HERRAMIENTA"
    SUBCONTRATO = "SUBCONTRATO"
    INDIRECTO = "INDIRECTO"


class UnidadMedida(str, Enum):
    M2 = "m2"
    M3 = "m3"
    ML = "ml"
    KG = "kg"
    TON = "ton"
    PZA = "pza"
    JGO = "jgo"
    HR = "hr"
    DIA = "dia"
    SEM = "sem"
    MES = "mes"
    LOT = "lot"
    GLB = "glb"
    M = "m"
    L = "l"
    PZ = "pz"
    SR = "sr"
    MOV = "mov"


class CatalogoAPU(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Catálogo maestro de conceptos de APU."""
    __tablename__ = "catalogos_apu"

    clave: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    tipo: Mapped[TipoConceptoAPU] = mapped_column(String(50), nullable=False)
    unidad: Mapped[UnidadMedida] = mapped_column(String(20), nullable=False)
    precio_unitario: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)

    # Metadatos del catálogo fuente
    fuente: Mapped[str] = mapped_column(String(100), nullable=False)  # CFE, CMIC, CONAGA, etc.
    vigencia_inicio: Mapped[str | None] = mapped_column(String(10), nullable=True)  # YYYY-MM-DD
    vigencia_fin: Mapped[str | None] = mapped_column(String(10), nullable=True)
    zona_economica: Mapped[str | None] = mapped_column(String(100), nullable=True)
    estado: Mapped[str | None] = mapped_column(String(100), nullable=True)
    incluye_iva: Mapped[bool] = mapped_column(default=False)

    # Desglose del APU (materiales, mano de obra, maquinaria)
    desglose: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    registro_importado_id: Mapped[object | None] = mapped_column(UUID(as_uuid=True), nullable=True, unique=True)
    origen: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relaciones
    precios_asignados: Mapped[list["PrecioUnitarioAsignado"]] = relationship(
        "PrecioUnitarioAsignado", back_populates="concepto"
    )

    __table_args__ = (
        ForeignKeyConstraint(['registro_importado_id', 'tenant_id'], ['catalogo_registros.id', 'catalogo_registros.tenant_id']),
        UniqueConstraint("tenant_id", "clave", "fuente", "zona_economica", name="uq_catalogo_apu_tenant_clave_fuente_zona"),
        Index("ix_catalogo_apu_clave_fuente", "clave", "fuente", "zona_economica"),
    )


class PrecioUnitarioAsignado(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Precio unitario asignado a un expediente/presupuesto específico."""
    __tablename__ = "precios_unitarios_asignados"

    concepto_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("catalogos_apu.id", ondelete="CASCADE"), nullable=False
    )
    expediente_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expedientes_obra.id", ondelete="CASCADE"), nullable=True
    )
    presupuesto_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("presupuestos.id", ondelete="CASCADE"), nullable=True
    )
    cantidad: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    precio_asignado: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    importe: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)

    concepto: Mapped["CatalogoAPU"] = relationship("CatalogoAPU", back_populates="precios_asignados")
