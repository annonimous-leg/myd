"""Add deterministic rule execution provenance."""

from alembic import op
import sqlalchemy as sa
from app.db.types import UUID, JSONB

revision = "20260826_tender_rule_execution_provenance"
down_revision = "20260826_tender_rule_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tender_rule_executions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("creado_por_id", UUID(as_uuid=True), nullable=True),
        sa.Column("actualizado_por_id", UUID(as_uuid=True), nullable=True),
        sa.Column("tender_id", UUID(as_uuid=True), sa.ForeignKey("tender_packages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("validation_run_id", UUID(as_uuid=True), sa.ForeignKey("tender_validation_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("rule_definition_id", UUID(as_uuid=True), sa.ForeignKey("tender_rule_definitions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("compiled_hash", sa.String(64), nullable=False),
        sa.Column("input_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("hit_policy", sa.String(20), nullable=False),
        sa.Column("selected_row_ids", JSONB, nullable=False),
        sa.Column("evaluated_conditions", JSONB, nullable=False),
        sa.Column("result", JSONB, nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
    )
    op.create_index("idx_tender_rule_execution_lookup", "tender_rule_executions", ["tenant_id", "tender_id", "rule_definition_id", "created_at"])


def downgrade():
    op.drop_index("idx_tender_rule_execution_lookup", table_name="tender_rule_executions")
    op.drop_table("tender_rule_executions")
