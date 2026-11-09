"""Domain-local durable OCR jobs.

Revision ID: 20261007_ocr_jobs
Revises: 20261006_intentos_trabajo
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261007_ocr_jobs"
down_revision = "20261006_intentos_trabajo"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ocr_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("creado_por_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actualizado_por_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("task_id", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("content_type", sa.String(160), nullable=True),
        sa.Column("storage_path", sa.String(1000), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("presupuesto_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claim_token", sa.String(36), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error_code", sa.String(120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["creado_por_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actualizado_por_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "presupuesto_id"],
            ["presupuestos.tenant_id", "presupuestos.id"],
            name="fk_ocr_job_tenant_presupuesto",
        ),
        sa.UniqueConstraint("task_id", name="uq_ocr_jobs_task_id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_ocr_jobs_tenant_id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_ocr_jobs_tenant_idempotency"),
    )
    op.create_index("ix_ocr_jobs_tenant_id", "ocr_jobs", ["tenant_id"])
    op.create_index("ix_ocr_jobs_creado_por_id", "ocr_jobs", ["creado_por_id"])
    op.create_index("ix_ocr_jobs_task_id", "ocr_jobs", ["task_id"])
    op.create_index("ix_ocr_jobs_presupuesto_id", "ocr_jobs", ["presupuesto_id"])
    op.create_index("ix_ocr_jobs_status", "ocr_jobs", ["status"])
    op.create_index(
        "ix_ocr_jobs_tenant_status_created",
        "ocr_jobs",
        ["tenant_id", "status", "created_at"],
    )


def downgrade():
    op.drop_table("ocr_jobs")
