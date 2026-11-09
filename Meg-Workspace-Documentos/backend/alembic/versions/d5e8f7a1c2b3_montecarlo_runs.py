"""Monte Carlo SaaS run persistence.

Revision ID: d5e8f7a1c2b3
Revises: c74195263279
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "d5e8f7a1c2b3"
down_revision: Union[str, None] = "c74195263279"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "monte_carlo_runs",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("creado_por_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actualizado_por_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("expediente_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("presupuesto_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("programa_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("progreso", sa.Integer(), nullable=False),
        sa.Column("iteraciones", sa.Integer(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("presupuesto_base", sa.Numeric(20, 6), nullable=False),
        sa.Column("presupuesto_maximo", sa.Numeric(20, 6), nullable=False),
        sa.Column("plazo_base_dias", sa.Integer(), nullable=True),
        sa.Column("plazo_maximo_dias", sa.Integer(), nullable=True),
        sa.Column("variables", postgresql.JSONB(), nullable=False),
        sa.Column("configuracion", postgresql.JSONB(), nullable=False),
        sa.Column("resultado", postgresql.JSONB(), nullable=True),
        sa.Column("error_codigo", sa.String(length=120), nullable=True),
        sa.Column("error_mensaje", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_ms", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["creado_por_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actualizado_por_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["expediente_id"], ["expedientes_obra.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["presupuesto_id"], ["presupuestos.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["programa_id"], ["programas_obra.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("task_id", name="uq_monte_carlo_task_id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_monte_carlo_tenant_idempotency"),
    )
    op.create_index("ix_monte_carlo_runs_tenant_id", "monte_carlo_runs", ["tenant_id"])
    op.create_index("ix_monte_carlo_runs_task_id", "monte_carlo_runs", ["task_id"])
    op.create_index("ix_monte_carlo_runs_estado", "monte_carlo_runs", ["estado"])
    op.create_index("ix_monte_carlo_runs_expediente_id", "monte_carlo_runs", ["expediente_id"])
    op.create_index("ix_monte_carlo_runs_presupuesto_id", "monte_carlo_runs", ["presupuesto_id"])
    op.create_index("ix_monte_carlo_runs_programa_id", "monte_carlo_runs", ["programa_id"])
    op.create_index(
        "ix_monte_carlo_tenant_estado_created",
        "monte_carlo_runs",
        ["tenant_id", "estado", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_monte_carlo_tenant_estado_created", table_name="monte_carlo_runs")
    for idx in (
        "ix_monte_carlo_runs_programa_id",
        "ix_monte_carlo_runs_presupuesto_id",
        "ix_monte_carlo_runs_expediente_id",
        "ix_monte_carlo_runs_estado",
        "ix_monte_carlo_runs_task_id",
        "ix_monte_carlo_runs_tenant_id",
    ):
        op.drop_index(idx, table_name="monte_carlo_runs")
    op.drop_table("monte_carlo_runs")
