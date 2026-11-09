# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Catálogo Jurídico.
Leyes, reglamentos, criterios, manuales, anexos, formatos.
"""
from datetime import datetime
from typing import Optional, List
from uuid import uuid4

from sqlalchemy import String, Text, ForeignKey, Index, DateTime, Boolean, Integer
from app.db.types import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, TenantMixin
from enum import Enum


class TipoNorma(str, Enum):
    """Tipos de normas jurídicas."""
    LEY = "LEY"
    REGLAMENTO = "REGLAMENTO"
    DECRETO = "DECRETO"
    ACUERDO = "ACUERDO"
    CRITERIO = "CRITERIO"
    MANUAL = "MANUAL"
    FORMATO = "FORMATO"
    ANEXO = "ANEXO"
    CIRCULAR = "CIRCULAR"
    NORMATIVA = "NORMATIVA"


class CatalogoJuridico(Base, UUIDMixin, TenantMixin):
    """Catálogo de normas jurídicas aplicables a la contratación pública."""
    __tablename__ = "catalogo_juridico"

    # Identificación
    clave: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Descripción
    descripcion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resumen: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Referencias legales
    articulos_relevantes: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # Ejemplo: [{"articulo": "42", "fraccion": "I", "texto": "..."}]

    # Aplicabilidad
    ambito_aplicacion: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # federal, estatal, municipal, interno

    # Vigencia
    fecha_publicacion: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    fecha_vigencia: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    fecha_modificacion: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    vigente: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Documento de referencia
    documento_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Relaciones
    # Reglas de cumplimiento asociadas
    reglas: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # Ejemplo: [{"condicion": "monto > 1000000", "obligacion": "licitacion_publica"}]

    # Metadatos
    palabras_clave: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_cat_juridico_clave_tipo", "clave", "tipo"),
        Index("ix_cat_juridico_vigente", "vigente"),
    )


class ReglaCatalogoJuridico(Base, UUIDMixin, TenantMixin):
    """Reglas de cumplimiento derivadas del catálogo jurídico."""
    __tablename__ = "reglas_cumplimiento_catalogo"

    catalogo_juridico_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("catalogo_juridico.id", ondelete="CASCADE"), nullable=False
    )

    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Condición lógica (JSON Logic o similar)
    condicion: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Ejemplo: {"and": [{"var": "monto"}, {">": [{"var": "monto"}, 1000000]}]}

    # Severidad
    severidad: Mapped[str] = mapped_column(String(20), nullable=False, default="MEDIA")
    # ALTA, MEDIA, BAJA

    # Aplicable a
    tipo_procedimiento: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # licitacion_publica, invitacion, adjudicacion_directa, etc.

    # Estado
    activa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relación
    catalogo: Mapped["CatalogoJuridico"] = relationship("CatalogoJuridico", backref="reglas_cumplimiento")
