# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Planeación del Expediente.
Necesidad, justificación, objetivo, presupuesto estimado, calendario, riesgos.
"""
from datetime import datetime
from typing import Optional, List
from uuid import uuid4

from sqlalchemy import String, Text, ForeignKey, Index, DateTime, Boolean, Numeric, Integer
from app.db.types import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, TenantMixin


class PlaneacionExpediente(Base, UUIDMixin, TenantMixin):
    """Planeación de un expediente de contratación.

    Contiene la justificación, necesidad, objetivos, presupuesto estimado,
    calendario preliminar y riesgos iniciales del proyecto.
    """
    __tablename__ = "planeacion_expediente"

    # Relación con expediente
    expediente_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expedientes_obra.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Necesidad
    necesidad: Mapped[str] = mapped_column(Text, nullable=False)
    justificacion: Mapped[str] = mapped_column(Text, nullable=False)
    objetivo: Mapped[str] = mapped_column(Text, nullable=False)

    # Alcance
    alcance: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    entregables: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # Ejemplo: ["obra_construida", "planos_asbuilt", "manuales_operacion"]

    # Presupuesto estimado
    presupuesto_estimado: Mapped[Optional[float]] = mapped_column(Numeric(15, 2), nullable=True)
    fuente_financiamiento: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # federal, estatal, municipal, propios, mixto

    # Calendario preliminar
    fecha_inicio_esperada: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    fecha_fin_esperada: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duracion_estimada_dias: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Calendario detallado
    hitos_planeacion: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # Ejemplo: [
    #   {"nombre": "Elaboración de bases", "inicio": "2026-01-01", "fin": "2026-01-15"},
    #   {"nombre": "Publicación de convocatoria", "inicio": "2026-01-20", "fin": "2026-01-25"},
    # ]

    # Riesgos iniciales
    riesgos: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # Ejemplo: [
    #   {"riesgo": "Incremento de precios de materiales", "probabilidad": "ALTA", "impacto": "ALTO", "mitigacion": "..."},
    # ]

    # Aprobaciones
    aprobado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fecha_aprobacion: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    aprobado_por_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Estado de la planeación
    estado: Mapped[str] = mapped_column(String(50), default="BORRADOR", nullable=False)
    # BORRADOR, EN_REVISION, APROBADO, RECHAZADO

    # Observaciones
    observaciones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_planeacion_expediente", "expediente_id"),
        Index("ix_planeacion_estado", "estado"),
    )
