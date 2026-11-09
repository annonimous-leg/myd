from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.db.types import JSONB, UUID
from app.models.base import AuditMixin, Base, TenantMixin, UUIDMixin


class EstadoMonteCarlo(str, Enum):
    PENDIENTE = "PENDIENTE"
    ENCOLADO = "ENCOLADO"
    EN_PROCESO = "EN_PROCESO"
    COMPLETADO = "COMPLETADO"
    ERROR = "ERROR"
    CANCELADO = "CANCELADO"


class MonteCarloRun(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Ejecución persistente y auditable de una simulación Monte Carlo.

    La corrida es un agregado SaaS: pertenece a tenant, usuario, y
    opcionalmente a expediente/presupuesto/programa. El resultado completo se
    persiste para reproducibilidad y auditoría; Celery es el ejecutor, no la
    fuente de verdad del historial.
    """

    __tablename__ = "monte_carlo_runs"

    task_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    expediente_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expedientes_obra.id", ondelete="SET NULL"), nullable=True, index=True
    )
    presupuesto_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("presupuestos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    programa_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("programas_obra.id", ondelete="SET NULL"), nullable=True, index=True
    )

    estado: Mapped[str] = mapped_column(String(20), default=EstadoMonteCarlo.PENDIENTE.value, nullable=False, index=True)
    progreso: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    iteraciones: Mapped[int] = mapped_column(Integer, nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)

    presupuesto_base: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False)
    presupuesto_maximo: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False)
    plazo_base_dias: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    plazo_maximo_dias: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    variables: Mapped[list] = mapped_column(JSONB, nullable=False)
    configuracion: Mapped[dict] = mapped_column(JSONB, nullable=False)
    resultado: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    error_codigo: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    error_mensaje: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Per-run fencing. A redelivered or expired worker must never mutate the
    # result of a newer claim, even when both share the same Celery task_id.
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    execution_token: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_monte_carlo_tenant_idempotency"),
        Index("ix_monte_carlo_tenant_estado_created", "tenant_id", "estado", "created_at"),
    )
