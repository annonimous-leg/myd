"""OpenL-inspired versioned rule lifecycle for tender requirements.

Adds a separate rule artifact/version layer without replacing TenderRequirement.
"""
from alembic import op
import sqlalchemy as sa
from app.db.types import UUID, JSONB

revision = "20260826_tender_rule_lifecycle"
down_revision = "20260826_procurement_validation_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tender_rule_definitions",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", UUID(), nullable=False),
        sa.Column("tenant_id", UUID(), nullable=False),
        sa.Column("tender_id", UUID(), nullable=False),
        sa.Column("requirement_id", UUID(), nullable=False),
        sa.Column("code", sa.String(120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(30), nullable=False, server_default="ACTIVE"),
        sa.Column("definition", JSONB(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("test_cases", JSONB(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("compiled_hash", sa.String(64), nullable=True),
        sa.Column("source_reference", JSONB(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("activated_at", sa.String(40), nullable=True),
        sa.Column("retired_at", sa.String(40), nullable=True),
        sa.Column("creado_por_id", UUID(), nullable=True),
        sa.Column("actualizado_por_id", UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tender_id"], ["tender_packages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requirement_id"], ["tender_requirements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["creado_por_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actualizado_por_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "tender_id", "code", "version", name="uq_tender_rule_definition_version"),
    )
    op.create_index(
        "idx_tender_rule_definition_active",
        "tender_rule_definitions",
        ["tenant_id", "tender_id", "code", "status"],
    )
    op.add_column(
        "tender_requirements",
        sa.Column("rule_definition_id", UUID(), nullable=True),
    )
    op.create_index("ix_tender_requirements_rule_definition_id", "tender_requirements", ["rule_definition_id"])
    op.create_foreign_key(
        "fk_tender_requirements_rule_definition",
        "tender_requirements",
        "tender_rule_definitions",
        ["rule_definition_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_tender_requirements_rule_definition", "tender_requirements", type_="foreignkey")
    op.drop_index("ix_tender_requirements_rule_definition_id", table_name="tender_requirements")
    op.drop_column("tender_requirements", "rule_definition_id")
    op.drop_index("idx_tender_rule_definition_active", table_name="tender_rule_definitions")
    op.drop_table("tender_rule_definitions")
