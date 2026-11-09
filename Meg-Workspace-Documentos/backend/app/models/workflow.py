# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Workflow / Orquestador de estados y transiciones.
Estados, transiciones, aprobaciones, tareas, timers, SLA.
"""
from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import UniqueConstraint, String, Text, ForeignKey, Index, DateTime, Integer
from app.db.types import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, TenantMixin, AuditMixin


class EstadoTarea(str, Enum):
    PENDIENTE = "PENDIENTE"
    EN_PROGRESO = "EN_PROGRESO"
    COMPLETADA = "COMPLETADA"
    CANCELADA = "CANCELADA"
    ESCALADA = "ESCALADA"


class TransicionWorkflow(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Transición válida entre estados de un expediente."""
    __tablename__ = "transiciones_workflow"

    tipo_procedimiento: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    estado_origen: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    estado_destino: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Condiciones
    requiere_aprobacion: Mapped[bool] = mapped_column(default=False)
    requiere_rol: Mapped[str | None] = mapped_column(String(50), nullable=True)
    condicion_regla: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Acciones automáticas
    acciones_auto: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # SLA
    sla_horas: Mapped[int | None] = mapped_column(nullable=True)
    recordatorio_horas: Mapped[int | None] = mapped_column(nullable=True)

    activa: Mapped[bool] = mapped_column(default=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "tipo_procedimiento", "estado_origen", "estado_destino", name="uq_transicionworkflow_tenant"),
        Index("ix_transicion_proc", "tipo_procedimiento", "estado_origen", "estado_destino"),
    )


class TareaWorkflow(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Tarea asignada en un workflow."""
    __tablename__ = "tareas_workflow"

    expediente_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expedientes_obra.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asignado_a_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    titulo: Mapped[str] = mapped_column(String(500), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    estado: Mapped[EstadoTarea] = mapped_column(String(50), default=EstadoTarea.PENDIENTE, index=True)

    # Fechas
    fecha_vencimiento: Mapped[str | None] = mapped_column(String(10), nullable=True)
    fecha_completada: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # SLA
    sla_horas: Mapped[int | None] = mapped_column(nullable=True)
    horas_transcurridas: Mapped[int] = mapped_column(default=0)

    # Datos
    datos: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class EstadoWorkflow(str, Enum):
    ACTIVO = "ACTIVO"
    COMPLETADO = "COMPLETADO"
    CANCELADO = "CANCELADO"
    PAUSADO = "PAUSADO"


class EstadoPasoWorkflow(str, Enum):
    PENDIENTE = "PENDIENTE"
    EN_PROGRESO = "EN_PROGRESO"
    COMPLETADO = "COMPLETADO"
    VENCIDO = "VENCIDO"
    OMITIDO = "OMITIDO"


class Workflow(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Instancia de un flujo configurable de pasos con condiciones
    dinámicas evaluables por transición (ver app.modules.workflow.engine.
    MotorWorkflow). RESTAURADO: app/modules/workflow/engine.py ya
    importaba Workflow/WorkflowPaso/WorkflowTransicion/WorkflowCondicion,
    pero nunca se habían definido -- mismo patrón de import roto que
    ValidacionPropuesta.

    No sustituye a TransicionWorkflow/TareaWorkflow (arriba): ese es un
    catálogo ligero de transiciones de ESTADO válidas por tipo de
    procedimiento con tareas simples; este modelo es para flujos ad-hoc
    con sus propios pasos y condiciones (p. ej. una cadena de aprobación
    de contrato con montos/roles que se evalúan dinámicamente).
    """
    __tablename__ = "workflows"

    expediente_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expedientes_obra.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # p. ej. "APROBACION_CONTRATO", "REVISION_EXPEDIENTE", "CIERRE_FINIQUITO"

    estado: Mapped[str] = mapped_column(String(20), default=EstadoWorkflow.ACTIVO.value, nullable=False, index=True)
    paso_actual_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_pasos.id", ondelete="SET NULL"), nullable=True
    )

    pasos: Mapped[list["WorkflowPaso"]] = relationship(
        "WorkflowPaso", back_populates="workflow", cascade="all, delete-orphan",
        foreign_keys="WorkflowPaso.workflow_id",
    )


class WorkflowPaso(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Paso concreto dentro de un Workflow."""
    __tablename__ = "workflow_pasos"

    workflow_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    orden: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    responsable_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    estado: Mapped[str] = mapped_column(
        String(20), default=EstadoPasoWorkflow.PENDIENTE.value, nullable=False, index=True
    )
    fecha_limite: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workflow: Mapped["Workflow"] = relationship(
        "Workflow", back_populates="pasos", foreign_keys=[workflow_id],
    )

    __table_args__ = (
        Index("ix_workflow_paso_workflow_orden", "workflow_id", "orden"),
    )


class WorkflowTransicion(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Transición posible entre dos WorkflowPaso de un mismo Workflow, con
    condiciones dinámicas evaluables (ver WorkflowCondicion). No
    confundir con TransicionWorkflow (arriba, catálogo de transiciones de
    ESTADO por tipo de procedimiento): esta es entre PASOS de un Workflow
    ad-hoc concreto."""
    __tablename__ = "workflow_transiciones"

    workflow_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    paso_origen_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_pasos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    paso_destino_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_pasos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nombre: Mapped[str] = mapped_column(String(100), default="Continuar", nullable=False)

    __table_args__ = (
        Index("ix_workflow_transicion_origen_destino", "paso_origen_id", "paso_destino_id"),
    )


class WorkflowCondicion(Base, UUIDMixin, TenantMixin):
    """Condición dinámica que debe cumplirse para que una WorkflowTransicion
    sea válida (ver MotorWorkflow.evaluar_condicion / OperadorCondicion en
    app.modules.workflow.engine: ==, !=, >, >=, <, <=, contains,
    startswith, endswith, in, is_empty, is_not_empty)."""
    __tablename__ = "workflow_condiciones"

    transicion_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_transiciones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campo: Mapped[str] = mapped_column(String(255), nullable=False)
    # Notación de punto sobre el contexto evaluado, p. ej. "presupuesto.monto_total"
    operador: Mapped[str] = mapped_column(String(20), nullable=False)
    valor_referencia: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    obligatoria: Mapped[bool] = mapped_column(default=True, nullable=False)
    orden: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
