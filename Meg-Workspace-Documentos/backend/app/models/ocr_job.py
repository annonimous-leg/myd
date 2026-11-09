from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID as UUIDType

from sqlalchemy import DateTime, ForeignKeyConstraint, BigInteger, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.types import JSONB, UUID
from app.models.base import AuditMixin, Base, TenantMixin, UUIDMixin


class OCRJobStatus(str, Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class OCRJob(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Ejecución OCR durable, propiedad exclusiva del dominio OCR."""

    __tablename__ = "ocr_jobs"

    task_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)

    presupuesto_id: Mapped[UUIDType | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    status: Mapped[str] = mapped_column(String(24), nullable=False, default=OCRJobStatus.PENDING.value, index=True)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claim_token: Mapped[str | None] = mapped_column(String(36), nullable=True)

    result: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_ocr_jobs_tenant_id"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_ocr_jobs_tenant_idempotency"),
        Index("ix_ocr_jobs_tenant_status_created", "tenant_id", "status", "created_at"),
        ForeignKeyConstraint(
            ["tenant_id", "presupuesto_id"],
            ["presupuestos.tenant_id", "presupuestos.id"],
            name="fk_ocr_job_tenant_presupuesto",
        ),
    )
