"""Add tenant scope to persistent notification logs."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "ff2a1b3c4d5e"
down_revision = "f4c2d7e9a1b6"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("notification_logs")}
    if "tenant_id" not in columns:
        op.add_column("notification_logs", sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_index("ix_notification_logs_tenant_id", "notification_logs", ["tenant_id"], unique=False)
        op.create_foreign_key("fk_notification_logs_tenant_id_tenants", "notification_logs", "tenants", ["tenant_id"], ["id"], ondelete="CASCADE")
        # No safe deterministic tenant can be inferred from historical notification logs.
        # Keep those rows but make them non-addressable by tenant-scoped reads.
        op.execute("UPDATE notification_logs SET estado='LEGACY_UNSCOPED' WHERE tenant_id IS NULL")


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("notification_logs")}
    if "tenant_id" in columns:
        op.drop_constraint("fk_notification_logs_tenant_id_tenants", "notification_logs", type_="foreignkey")
        op.drop_index("ix_notification_logs_tenant_id", table_name="notification_logs")
        op.drop_column("notification_logs", "tenant_id")
