# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Modelos de licitaciones y procedimientos de contratación pública.
Máquina de estados con transiciones legales forzadas (LAASSP / LOPSRM).
"""
from enum import Enum
from uuid import uuid4
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, Numeric, ForeignKey, Index, DateTime, Integer, Boolean, UniqueConstraint, text
from app.db.types import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, TenantMixin, AuditMixin

if TYPE_CHECKING:
    from app.models.contrato import Contrato
    from app.models.expediente import ExpedienteObra
    from app.models.proveedor import Proveedor


class TipoProcedimiento(str, Enum):
    LICITACION_PUBLICA = "LICITACION_PUBLICA"
    INVITACION_TRES = "INVITACION_A_CUANDO_MENOS_TRES"
    ADJUDICACION_DIRECTA = "ADJUDICACION_DIRECTA"
    OBRA_PUBLICA = "OBRA_PUBLICA"
    ADQUISICION = "ADQUISICION"
    ARRENDAMIENTO = "ARRENDAMIENTO"
    SERVICIO = "SERVICIO"


class EstadoLicitacion(str, Enum):
    """Máquina de estados legal. Transiciones forzadas por ley."""
    # Fase 1: Planeación
    PLANEACION = "PLANEACION"
    # Fase 2: Investigación de mercado
    INVESTIGACION_MERCADO = "INVESTIGACION_MERCADO"
    # Fase 3: Selección de procedimiento (automática por ley)
    SELECCION_PROCEDIMIENTO = "SELECCION_PROCEDIMIENTO"
    # Fase 4: Convocatoria
    CONVOCATORIA = "CONVOCATORIA"
    # Fase 5: Junta de aclaraciones
    JUNTA_ACLARACIONES = "JUNTA_ACLARACIONES"
    # Fase 6: Recepción de propuestas
    RECEPCION_PROPUESTAS = "RECEPCION_PROPUESTAS"
    # Fase 7: Apertura
    APERTURA = "APERTURA"
    # Fase 8: Evaluación
    EVALUACION = "EVALUACION"
    # Fase 9: Dictamen y fallo
    FALLO = "FALLO"
    # Fase 10: Adjudicación
    ADJUDICACION = "ADJUDICACION"
    # Fase 11: Contrato
    CONTRATO = "CONTRATO"
    # Estados finales
    DESIERTA = "DESIERTA"
    CANCELADA = "CANCELADA"
    CERRADA = "CERRADA"


class TipoEvaluacion(str, Enum):
    LEGAL = "LEGAL"
    TECNICA = "TECNICA"
    ECONOMICA = "ECONOMICA"


class ResultadoEvaluacion(str, Enum):
    APROBADA = "APROBADA"
    RECHAZADA = "RECHAZADA"
    OBSERVADA = "OBSERVADA"
    DESISTIDA = "DESISTIDA"


class Licitacion(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Procedimiento de licitación / contratación pública con máquina de estados."""
    __tablename__ = "licitaciones"

    expediente_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expedientes_obra.id", ondelete="CASCADE"), nullable=False, index=True
    )

    folio: Mapped[str] = mapped_column(String(100), unique=False, nullable=False, index=True)
    # Contexto raíz de dependencia: acompaña elaboración/evaluación y evita mezclar criterios.
    jurisdiction_code: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    tipo_procedimiento: Mapped[TipoProcedimiento] = mapped_column(String(50), nullable=False)
    estado: Mapped[EstadoLicitacion] = mapped_column(String(50), default=EstadoLicitacion.PLANEACION, index=True)

    # Datos de convocatoria
    objeto: Mapped[str] = mapped_column(Text, nullable=False)
    monto_estimado: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    plazo_dias: Mapped[int | None] = mapped_column(nullable=True)

    # Fechas clave legales
    fecha_convocatoria: Mapped[str | None] = mapped_column(String(10), nullable=True)
    fecha_junta_aclaraciones: Mapped[str | None] = mapped_column(String(10), nullable=True)
    fecha_apertura: Mapped[str | None] = mapped_column(String(10), nullable=True)
    fecha_fallo: Mapped[str | None] = mapped_column(String(10), nullable=True)
    fecha_adjudicacion: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Reglas de participación y bases
    reglas_participacion: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    bases: Mapped[str | None] = mapped_column(Text, nullable=True)
    bases_version: Mapped[int] = mapped_column(Integer, default=1)
    bases_congeladas: Mapped[bool] = mapped_column(Boolean, default=False)

    # Matriz de evaluación
    matriz_evaluacion: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    dictamen: Mapped[str | None] = mapped_column(Text, nullable=True)
    fallo_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Resultado del selector de procedimiento (motor jurídico)
    justificacion_procedimiento: Mapped[str | None] = mapped_column(Text, nullable=True)
    presupuesto_dependencia_miles: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)

    # Investigación de mercado
    investigacion_mercado: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __mapper_args__ = {"version_id_col": row_version, "version_id_generator": lambda v: (v or 0) + 1}

    # Relaciones
    expediente: Mapped["ExpedienteObra"] = relationship("ExpedienteObra", back_populates="licitaciones")
    juntas_aclaraciones: Mapped[list["JuntaAclaracion"]] = relationship("JuntaAclaracion", back_populates="licitacion", cascade="all, delete-orphan")
    proposiciones: Mapped[list["Proposicion"]] = relationship("Proposicion", back_populates="licitacion", cascade="all, delete-orphan")
    evaluaciones: Mapped[list["EvaluacionLicitacion"]] = relationship("EvaluacionLicitacion", back_populates="licitacion", cascade="all, delete-orphan")
    contrato: Mapped["Contrato"] = relationship("Contrato", back_populates="licitacion", uselist=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_licitaciones_tenant_id"),
        UniqueConstraint("expediente_id", "folio", name="uq_licitacion_expediente_folio"),
    )


class JuntaAclaracion(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Junta de aclaraciones con trazabilidad legal."""
    __tablename__ = "juntas_aclaraciones"

    licitacion_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("licitaciones.id", ondelete="CASCADE"), nullable=False, index=True
    )

    fecha: Mapped[str] = mapped_column(String(10), nullable=False)
    acta: Mapped[str | None] = mapped_column(Text, nullable=True)
    preguntas_respuestas: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    cambios_bases: Mapped[str | None] = mapped_column(Text, nullable=True)
    numero_junta: Mapped[int] = mapped_column(Integer, default=1)

    # Legal: solicitudes deben presentarse con >=24h de anticipación
    fecha_limite_solicitudes: Mapped[str | None] = mapped_column(String(10), nullable=True)

    licitacion: Mapped["Licitacion"] = relationship("Licitacion", back_populates="juntas_aclaraciones")


class Proposicion(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Proposición / oferta recibida."""
    __tablename__ = "proposiciones"

    licitacion_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("licitaciones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    proveedor_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("proveedores.id", ondelete="RESTRICT"), nullable=False
    )

    monto: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    plazo_dias: Mapped[int] = mapped_column(nullable=False)
    sobres_digitales: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Validación legal
    firma_valida: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    integridad_valida: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    cumplimiento_documental: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    verificacion_documental: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Resultado
    estado: Mapped[str] = mapped_column(String(50), default="RECIBIDA")  # RECIBIDA, ADMITIDA, DESECHADA
    motivo_desecho: Mapped[str | None] = mapped_column(Text, nullable=True)

    licitacion: Mapped["Licitacion"] = relationship("Licitacion", back_populates="proposiciones")
    proveedor: Mapped["Proveedor"] = relationship("Proveedor", back_populates="proposiciones")


class EvaluacionLicitacion(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Evaluación legal, técnica o económica de una proposición."""
    __tablename__ = "evaluaciones_licitacion"

    licitacion_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("licitaciones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    proposicion_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("proposiciones.id", ondelete="CASCADE"), nullable=False
    )

    tipo: Mapped[TipoEvaluacion] = mapped_column(String(50), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    resultado: Mapped[ResultadoEvaluacion] = mapped_column(String(50), nullable=False)
    puntaje: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    dictamen: Mapped[str | None] = mapped_column(Text, nullable=True)
    criterios: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    evaluador_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    licitacion: Mapped["Licitacion"] = relationship("Licitacion", back_populates="evaluaciones")

    __table_args__ = (
        Index("uq_evaluacion_revision", "licitacion_id", "proposicion_id", "tipo", "revision",
              unique=True, postgresql_where=text("revision > 0"), sqlite_where=text("revision > 0")),
    )
