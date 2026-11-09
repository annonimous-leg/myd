from __future__ import annotations

from datetime import datetime
from uuid import UUID as UUIDType

from sqlalchemy import CheckConstraint, DateTime, Boolean, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.types import UUID
from app.models.base import AuditMixin, Base, TenantMixin, UUIDMixin


class ProcurementJob(Base, UUIDMixin, TenantMixin, AuditMixin):
    __tablename__ = "procurement_jobs"

    tender_id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING", index=True)
    task_id: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    claim_token: Mapped[UUIDType | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_procurement_jobs_tenant_id"),
        UniqueConstraint("tenant_id", "tender_id", "kind", "idempotency_key", name="uq_procurement_job_idempotency"),
        Index("idx_procurement_job_tenant_status", "tenant_id", "status"),
        Index("ix_procurement_job_claims", "status", "lease_expires_at"),
        CheckConstraint("attempt >= 0", name="ck_procurement_job_nonnegative_attempt"),
        ForeignKeyConstraint(["tenant_id", "tender_id"], ["tender_packages.tenant_id", "tender_packages.id"], ondelete="CASCADE"),
    )


class ProcurementIdempotency(Base, UUIDMixin, TenantMixin):
    __tablename__ = "procurement_idempotency"

    key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    job_id: Mapped[UUIDType] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "key", name="uq_procurement_idempotency_tenant_key"),
        ForeignKeyConstraint(["tenant_id", "job_id"], ["procurement_jobs.tenant_id", "procurement_jobs.id"], ondelete="CASCADE"),
    )


class ProcurementStorageIntent(Base, UUIDMixin, TenantMixin):
    __tablename__ = "procurement_storage_intents"

    job_id: Mapped[UUIDType | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    bucket: Mapped[str] = mapped_column(String(120), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_type: Mapped[str] = mapped_column(String(160), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING", index=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[UUIDType | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "bucket", "storage_path", "content_hash", name="uq_procurement_storage_intent"),
        ForeignKeyConstraint(["tenant_id", "job_id"], ["procurement_jobs.tenant_id", "procurement_jobs.id"], ondelete="RESTRICT"),
    )
