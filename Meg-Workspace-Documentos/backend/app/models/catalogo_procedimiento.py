# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Catálogo de Procedimientos de Contratación.
Tipos de procedimientos según la LAASSP y normativa aplicable.
"""
from datetime import datetime
from typing import Optional, List
from uuid import uuid4

from sqlalchemy import String, Text, ForeignKey, Index, DateTime, Boolean, Numeric, Integer
from app.db.types import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, TenantMixin
from enum import Enum


class TipoProcedimiento(str, Enum):
    """Tipos de procedimientos de contratación."""
    LICITACION_PUBLICA = "LICITACION_PUBLICA"
    INVITACION_TRES = "INVITACION_TRES"
    ADJUDICACION_DIRECTA = "ADJUDICACION_DIRECTA"
    OBRA_PUBLICA = "OBRA_PUBLICA"
    ADQUISICIONES = "ADQUISICIONES"
    ARRENDAMIENTOS = "ARRENDAMIENTOS"
    SERVICIOS = "SERVICIOS"
    CONCESION = "CONCESION"
    ALIANZA_PUBLICO_PRIVADA = "ALIANZA_PUBLICO_PRIVADA"
    CONTRATO_INTEGRAL = "CONTRATO_INTEGRAL"


class CatalogoProcedimiento(Base, UUIDMixin, TenantMixin):
    """Catálogo de tipos de procedimientos de contratación pública."""
    __tablename__ = "catalogo_procedimientos"

    # Identificación
    clave: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Descripción
    descripcion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    objetivo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Umbrales económicos (según LAASSP)
    monto_minimo: Mapped[Optional[float]] = mapped_column(Numeric(15, 2), nullable=True)
    monto_maximo: Mapped[Optional[float]] = mapped_column(Numeric(15, 2), nullable=True)

    # Requisitos
    requisitos_participacion: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # Ejemplo: ["constancia_fiscal", "experiencia_3_anos", "capacidad_financiera"]

    documentos_requeridos: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # Ejemplo: ["propuesta_tecnica", "propuesta_economica", "garantia_seriedad"]

    # Etapas del procedimiento
    etapas: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # Ejemplo: [
    #   {"orden": 1, "nombre": "Convocatoria", "duracion_dias": 5},
    #   {"orden": 2, "nombre": "Junta Aclaraciones", "duracion_dias": 3},
    #   {"orden": 3, "nombre": "Recepción Propuestas", "duracion_dias": 15},
    #   {"orden": 4, "nombre": "Apertura", "duracion_dias": 1},
    #   {"orden": 5, "nombre": "Evaluación", "duracion_dias": 10},
    #   {"orden": 6, "nombre": "Fallo", "duracion_dias": 5},
    # ]

    # Plazos
    plazo_minimo_dias: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    plazo_maximo_dias: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Vigencia
    vigente: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fecha_vigencia: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Base legal
    base_legal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    articulos_aplicables: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # Metadatos
    palabras_clave: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_cat_proc_clave_tipo", "clave", "tipo"),
        Index("ix_cat_proc_vigente", "vigente"),
    )