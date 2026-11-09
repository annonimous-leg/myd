"""Add tenant context to Tezcatlipoca API audit logs."""
from alembic import op
import sqlalchemy as sa

revision = "f4c2d7e9a1b6"
down_revision = "20260829_tezcatlipoca_tables"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("api_logs")}
    if "tenant_id" not in columns:
        op.add_column("api_logs", sa.Column("tenant_id", sa.String(length=36), nullable=True))
        op.create_index("ix_api_logs_tenant_id", "api_logs", ["tenant_id"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("api_logs")}
    if "tenant_id" in columns:
        op.drop_index("ix_api_logs_tenant_id", table_name="api_logs")
        op.drop_column("api_logs", "tenant_id")
