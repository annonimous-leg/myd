from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260914_workspace_bridge_tenant"
down_revision = "20260914_workspace_bridge_versioning"
branch_labels = None
depends_on = None


def upgrade():
    uuid = postgresql.UUID(as_uuid=True)
    jsonb = postgresql.JSONB()
    op.create_table(
        "tender_licitacion_bridges",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", uuid, primary_key=True), sa.Column("tenant_id", uuid, nullable=False),
        sa.Column("creado_por_id", uuid, nullable=True), sa.Column("actualizado_por_id", uuid, nullable=True),
        sa.Column("tender_package_id", uuid, nullable=False), sa.Column("licitacion_id", uuid, nullable=False),
        sa.Column("expediente_id", uuid, nullable=False), sa.Column("relationship_type", sa.String(40), nullable=False, server_default="PRIMARY"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("contract_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("field_mapping", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_tender_revision", sa.Integer()), sa.Column("last_licitacion_version", sa.Integer()),
        sa.Column("conflict_policy", sa.String(40), nullable=False, server_default="FAIL_CLOSED"),
        sa.ForeignKeyConstraint(["tenant_id", "tender_package_id"], ["tender_packages.tenant_id", "tender_packages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id", "licitacion_id"], ["licitaciones.tenant_id", "licitaciones.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id", "expediente_id"], ["expedientes_obra.tenant_id", "expedientes_obra.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "tender_package_id", "licitacion_id", name="uq_tender_licitacion_bridge"),
    )
    op.create_index("idx_tender_bridge_tenant_active", "tender_licitacion_bridges", ["tenant_id", "active"])

    op.create_table(
        "tender_documents",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", uuid, primary_key=True), sa.Column("tenant_id", uuid, nullable=False),
        sa.Column("creado_por_id", uuid, nullable=True), sa.Column("actualizado_por_id", uuid, nullable=True),
        sa.Column("tender_id", uuid, nullable=False), sa.Column("artifact_code", sa.String(120), nullable=False),
        sa.Column("name", sa.String(500), nullable=False), sa.Column("media_type", sa.String(120), nullable=False, server_default="text/plain"),
        sa.Column("content_text", sa.Text(), nullable=False, server_default=""), sa.Column("content_model", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT"), sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("tender_revision", sa.Integer(), nullable=False), sa.Column("generated_from_revision", sa.Integer()), sa.Column("generated_model_hash", sa.String(64)),
        sa.Column("human_modified", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_evidence_ids", jsonb, nullable=False, server_default=sa.text("'[]'::jsonb")), sa.Column("requirement_ids", jsonb, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("data_dependencies", jsonb, nullable=False, server_default=sa.text("'[]'::jsonb")), sa.Column("warnings", jsonb, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("last_conflict", jsonb), sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["tenant_id", "tender_id"], ["tender_packages.tenant_id", "tender_packages.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_tender_document_tenant_id"),
        sa.UniqueConstraint("tenant_id", "tender_id", "artifact_code", "version", name="uq_tender_document_version"),
    )
    op.create_table(
        "tender_document_revisions",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", uuid, primary_key=True), sa.Column("tenant_id", uuid, nullable=False),
        sa.Column("document_id", uuid, nullable=False), sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(40), nullable=False), sa.Column("content_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("content_model", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("tender_revision", sa.Integer(), nullable=False),
        sa.Column("source_model_hash", sa.String(64)), sa.Column("human_modified", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("metadata", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.ForeignKeyConstraint(["tenant_id", "document_id"], ["tender_documents.tenant_id", "tender_documents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "document_id", "version", name="uq_tender_document_revision"),
    )


def downgrade():
    op.drop_table("tender_document_revisions")
    op.drop_table("tender_documents")
    op.drop_index("idx_tender_bridge_tenant_active", table_name="tender_licitacion_bridges")
    op.drop_table("tender_licitacion_bridges")
