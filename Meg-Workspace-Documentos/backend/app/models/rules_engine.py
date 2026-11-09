# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Rules Engine - Motor de reglas de negocio.
Reglas por ley, por tipo de procedimiento y por entidad.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import uuid4

from sqlalchemy import UniqueConstraint, String, Text, ForeignKey, Index, DateTime, Boolean, Integer
from app.db.types import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, TenantMixin
from enum import Enum


class TipoRegla(str, Enum):
    """Tipos/categorías de regla de negocio disponibles (ver
    ReglaNegocio.categoria). RESTAURADO: app/models/__init__.py ya
    importaba esta clase, pero nunca se había definido aquí -- mismo
    patrón de import roto que ValidacionPropuesta en app/models/validador.py."""
    NORMATIVO = "NORMATIVO"
    FINANCIERO = "FINANCIERO"
    TECNICO = "TECNICO"
    DOCUMENTAL = "DOCUMENTAL"
    TEMPORAL = "TEMPORAL"


class ReglaNegocio(Base, UUIDMixin, TenantMixin):
    """Regla de negocio parametrizable del sistema.

    Define condiciones, validaciones y acciones automáticas
    basadas en el contexto del expediente.
    """
    __tablename__ = "reglas_negocio"

    # Identificación
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    codigo: Mapped[str] = mapped_column(String(50), nullable=False, index=True, unique=False)

    # Categoría
    categoria: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # NORMATIVO, FINANCIERO, TECNICO, DOCUMENTAL, TEMPORAL

    # Ámbito de aplicación
    tipo_procedimiento: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # Si null, aplica a todos

    # Condición (JSON Logic)
    condicion: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Ejemplo: {
    #   "and": [
    #     {">": [{"var": "monto_contrato"}, 1000000]},
    #     {"==": [{"var": "tipo_procedimiento"}, "LICITACION_PUBLICA"]}
    #   ]
    # }

    # Acción cuando la condición se cumple
    accion: Mapped[str] = mapped_column(String(50), nullable=False)
    # PERMITIR, BLOQUEAR, ADVERTIR, REQUERIR_APROBACION, NOTIFICAR

    # Parámetros de la acción
    parametros_accion: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Ejemplo: {"mensaje": "Monto excede umbral", "nivel": "ALTO", "notificar_a": ["director"]}

    # Severidad
    severidad: Mapped[str] = mapped_column(String(20), default="MEDIA", nullable=False)
    # ALTA, MEDIA, BAJA

    # Estado
    activa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Prioridad (para orden de evaluación)
    prioridad: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    # Vigencia
    fecha_vigencia: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    fecha_expiracion: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Metadatos
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    creado_por_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "codigo", name="uq_regla_codigo_tenant"),
        Index("ix_reglas_activa_categoria", "activa", "categoria"),
        Index("ix_reglas_codigo", "codigo"),
        Index("ix_reglas_prioridad", "prioridad"),
    )


class EjecucionRegla(Base, UUIDMixin, TenantMixin):
    """Registro de ejecución de una regla de negocio.

    Guarda el resultado de evaluar una regla sobre un expediente específico.
    """
    __tablename__ = "ejecucion_reglas"

    regla_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reglas_negocio.id", ondelete="CASCADE"), nullable=False
    )

    expediente_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expedientes_obra.id", ondelete="CASCADE"), nullable=False
    )

    # Contexto de evaluación
    contexto: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Los valores de las variables en el momento de la evaluación

    # Resultado
    resultado: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # True = condición cumplida, False = no cumplida

    # Acción ejecutada
    accion_ejecutada: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Mensaje generado
    mensaje: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Estado
    estado: Mapped[str] = mapped_column(String(50), default="EJECUTADA", nullable=False)
    # EJECUTADA, PENDIENTE, FALLIDA

    __table_args__ = (
        Index("ix_ejecucion_regla_exp", "regla_id", "expediente_id"),
        Index("ix_ejecucion_estado", "estado"),
    )