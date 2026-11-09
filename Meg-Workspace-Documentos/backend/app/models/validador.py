# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Validador - Motor de validación de expedientes.
Validaciones automáticas de requisitos, documentos, montos, plazos.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import uuid4

from sqlalchemy import String, Text, ForeignKey, Index, DateTime, Boolean, Integer
from app.db.types import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, TenantMixin, AuditMixin
from enum import Enum


class TipoValidacion(str, Enum):
    """Tipos de validaciones disponibles."""
    DOCUMENTAL = "DOCUMENTAL"
    FINANCIERA = "FINANCIERA"
    TECNICA = "TECNICA"
    TEMPORAL = "TEMPORAL"
    NORMATIVA = "NORMATIVA"
    INTEGRIDAD = "INTEGRIDAD"


class EstadoValidacion(str, Enum):
    """Estados de una validación."""
    PENDIENTE = "PENDIENTE"
    EN_PROCESO = "EN_PROCESO"
    APROBADA = "APROBADA"
    RECHAZADA = "RECHAZADA"
    CON_OBSERVACIONES = "CON_OBSERVACIONES"


class ValidacionExpediente(Base, UUIDMixin, TenantMixin):
    """Validación de un expediente.

    Agrupa múltiples checks de validación aplicados a un expediente.
    """
    __tablename__ = "validaciones_expediente"

    expediente_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expedientes_obra.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Tipo y descripción
    tipo: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Estado
    estado: Mapped[str] = mapped_column(String(50), default="PENDIENTE", nullable=False)

    # Resultados detallados
    resultados: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # Ejemplo: [
    #   {"check": "Documentos completos", "estado": "APROBADO", "detalle": "12/12 documentos presentes"},
    #   {"check": "Monto dentro de umbral", "estado": "APROBADO", "detalle": "$45M dentro de límite"},
    #   {"check": "Plazo razonable", "estado": "RECHAZADO", "detalle": "365 días excede estándar de 180"},
    # ]

    # Observaciones
    observaciones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Ejecutor
    ejecutado_por_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    fecha_ejecucion: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Score de validación (0-100)
    score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_validacion_expediente_tipo", "expediente_id", "tipo"),
        Index("ix_validacion_estado", "estado"),
    )


class ValidacionPropuesta(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Historical evidence of diagnostics and documented reviewer attestations.

    A declared-input diagnostic never establishes signature or file integrity.
    Entries with estado=REVISION_DOCUMENTAL record the approve command, actor,
    checked document hashes and reviewer conclusions. Licitation evaluation and
    award remain the authority for admission and selection.
    """
    __tablename__ = "validaciones_propuesta"

    expediente_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expedientes_obra.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Diagnostics may exist before a proposition; formal review always links it.
    proposicion_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("proposiciones.id", ondelete="SET NULL"), nullable=True, index=True
    )

    rfc_empresa: Mapped[Optional[str]] = mapped_column(String(13), nullable=True, index=True)

    # Diagnostic: SOLVENTE | DESCALIFICADO. Reviewer attestation: REVISION_DOCUMENTAL.
    estado: Mapped[str] = mapped_column(String(30), nullable=False, default="SOLVENTE", index=True)

    # Bitácora completa devuelta por el motor: lista de
    # {"id_regla", "seccion", "estatus" (PASA/FALLA/NO_APLICA),
    #  "valor_detectado", "valor_esperado", "evidencia"}
    bitacora_evaluacion: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # Payload completo recibido para esta corrida (trazabilidad/reproducibilidad).
    datos_entrada: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_validacion_propuesta_expediente", "expediente_id", "estado"),
        Index("ix_validacion_propuesta_proposicion", "proposicion_id"),
    )


class CheckValidacion(Base, UUIDMixin, TenantMixin):
    """Check individual de validación.

    Un check es una validación atómica que puede ser reutilizada
    en múltiples validaciones de expediente.
    """
    __tablename__ = "checks_validacion"

    # Identificación
    codigo: Mapped[str] = mapped_column(String(50), nullable=False, index=True, unique=True)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Categoría
    categoria: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # DOCUMENTAL, FINANCIERA, TECNICA, TEMPORAL, NORMATIVA

    # Lógica de validación
    logica: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Ejemplo: {
    #   "tipo": "documento_existe",
    #   "parametros": {"tipo_documento": "CONVOCATORIA", "requerido": true}
    # }
    # O:
    # {
    #   "tipo": "rango_numerico",
    #   "parametros": {"campo": "monto_contrato", "min": 0, "max": 100000000}
    # }

    # Mensajes
    mensaje_exito: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    mensaje_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Severidad
    severidad: Mapped[str] = mapped_column(String(20), default="MEDIA", nullable=False)
    # BLOQUEANTE, ALTA, MEDIA, BAJA, INFORMATIVA

    # Estado
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Orden de ejecución
    orden: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("ix_checks_categoria_activo", "categoria", "activo"),
        Index("ix_checks_orden", "orden"),
    )