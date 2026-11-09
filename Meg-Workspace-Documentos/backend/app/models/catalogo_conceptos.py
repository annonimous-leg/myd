# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Modelos para catálogos de precios unitarios reales (CFE, CMIC, CONAGA, etc.).
Estas tablas se alimentan vía ETL desde Supabase.
"""
from enum import Enum
from uuid import uuid4

from sqlalchemy import String, Text, Numeric, ForeignKey, Index
from app.db.types import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, AuditMixin


class TipoCatalogo(str, Enum):
    CFE = "CFE"
    CMIC = "CMIC"
    CONAGA = "CONAGA"
    SCT = "SCT"
    PEMEX = "PEMEX"
    CUSTOM = "CUSTOM"


class CatalogoFuente(Base, UUIDMixin, AuditMixin):
    """Fuente / origen de un catálogo de precios."""
    __tablename__ = "catalogo_fuentes"

    nombre: Mapped[str] = mapped_column(String(100), nullable=False)  # CFE, CMIC, CONAGA
    tipo: Mapped[TipoCatalogo] = mapped_column(String(50), nullable=False, index=True)
    vigencia_inicio: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    vigencia_fin: Mapped[str] = mapped_column(String(10), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    url_fuente: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    moneda: Mapped[str | None] = mapped_column(String(3), nullable=True)
    moneda_evidencia: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    activo: Mapped[bool] = mapped_column(default=True)


class ConceptoCatalogo(Base, UUIDMixin, AuditMixin):
    """Concepto de trabajo de un catálogo real."""
    __tablename__ = "conceptos_catalogo"

    fuente_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("catalogo_fuentes.id", ondelete="CASCADE"), nullable=False, index=True
    )

    clave: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    descripcion_larga: Mapped[str | None] = mapped_column(Text, nullable=True)
    unidad: Mapped[str] = mapped_column(String(20), nullable=False)
    precio_unitario: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)

    # Zonificación
    zona_economica: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    estado: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Flags
    incluye_iva: Mapped[bool] = mapped_column(default=False)
    activo: Mapped[bool] = mapped_column(default=True)

    # Desglose APU (si aplica)
    desglose: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Metadatos de extracción
    pagina_origen: Mapped[int | None] = mapped_column(nullable=True)
    hash_linea: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_concepto_clave_fuente_zona", "clave", "fuente_id", "zona_economica", unique=True),
        Index("ix_concepto_busqueda", "descripcion"),  # Para búsqueda full-text
    )


class InsumoCatalogo(Base, UUIDMixin, AuditMixin):
    """Insumo desglosado: material, mano de obra, maquinaria, salario profesional."""
    __tablename__ = "insumos_catalogo"

    fuente_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("catalogo_fuentes.id", ondelete="CASCADE"), nullable=False, index=True
    )

    clave: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # MATERIAL, MANO_OBRA, MAQUINARIA, SALARIO_PROFESIONAL
    unidad: Mapped[str] = mapped_column(String(20), nullable=False)
    precio_unitario: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)

    # Específicos por tipo
    categoria: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Ej: "Hormigón", "Acero", "Operador"
    subcategoria: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Zonificación
    zona_economica: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    estado: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    incluye_iva: Mapped[bool] = mapped_column(default=False)
    activo: Mapped[bool] = mapped_column(default=True)

    __table_args__ = (
        Index("ix_insumo_clave_fuente_zona", "clave", "fuente_id", "zona_economica", "tipo", unique=True),
    )
