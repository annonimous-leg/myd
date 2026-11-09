"""Durable procurement preparation run/stage trace and review gate state."""
from alembic import op
import sqlalchemy as sa
from app.db.types import UUID, JSONB

revision = "20260826_procurement_preparation_runs"
down_revision = "20260811_procurement_prr_close"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tender_packages", sa.Column("review_state", sa.String(50), nullable=True))
    op.create_table(
        "tender_preparation_runs",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", UUID(), nullable=False),
        sa.Column("tenant_id", UUID(), nullable=False),
        sa.Column("tender_id", UUID(), nullable=False),
        sa.Column("correlation_id", sa.String(120), nullable=False),
        sa.Column("pipeline_version", sa.String(80), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("current_stage", sa.String(80), nullable=True),
        sa.Column("failure_code", sa.String(120), nullable=True),
        sa.Column("failure_detail", sa.Text(), nullable=True),
        sa.Column("started_at", sa.String(40), nullable=True),
        sa.Column("finished_at", sa.String(40), nullable=True),
        sa.Column("creado_por_id", UUID(), nullable=True),
        sa.Column("actualizado_por_id", UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tender_id"], ["tender_packages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["creado_por_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actualizado_por_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("idx_tender_preparation_run_tenant_tender", "tender_preparation_runs", ["tenant_id", "tender_id", "created_at"])
    op.create_index("idx_tender_preparation_run_correlation", "tender_preparation_runs", ["tenant_id", "correlation_id"])
    op.create_table(
        "tender_preparation_stage_runs",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", UUID(), nullable=False),
        sa.Column("tenant_id", UUID(), nullable=False),
        sa.Column("preparation_run_id", UUID(), nullable=False),
        sa.Column("stage", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("input_refs", JSONB(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("output_refs", JSONB(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("rule_version", sa.String(120), nullable=True),
        sa.Column("engine_version", sa.String(120), nullable=True),
        sa.Column("error_code", sa.String(120), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("started_at", sa.String(40), nullable=True),
        sa.Column("finished_at", sa.String(40), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["preparation_run_id"], ["tender_preparation_runs.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_tender_stage_run_tenant_run_stage", "tender_preparation_stage_runs", ["tenant_id", "preparation_run_id", "stage"])


def downgrade() -> None:
    op.drop_index("idx_tender_stage_run_tenant_run_stage", table_name="tender_preparation_stage_runs")
    op.drop_table("tender_preparation_stage_runs")
    op.drop_index("idx_tender_preparation_run_correlation", table_name="tender_preparation_runs")
    op.drop_index("idx_tender_preparation_run_tenant_tender", table_name="tender_preparation_runs")
    op.drop_table("tender_preparation_runs")
    op.drop_column("tender_packages", "review_state")
