"""Store embedded subsystem instants as timezone-aware UTC values.

Historical defaults wrote UTC without a zone. Interpret existing naive values
as UTC explicitly, independent of the database session timezone.
"""
from alembic import op
import sqlalchemy as sa

revision = '20260930_tez_timestamps'
down_revision = '20260930_model_audit_fields'
branch_labels = None
depends_on = None

COLUMNS = {
    'tezcatlipoca_users': ('created_at', 'last_login'),
    'user_sessions': ('created_at', 'expires_at', 'last_active'),
    'snapshots': ('created_at',),
    'tunnels': ('created_at', 'expires_at', 'closed_at'),
    'dead_drops': ('created_at', 'expires_at'),
    'api_logs': ('timestamp',),
    'token_blacklist': ('expires_at', 'revoked_at'),
    'system_settings': ('created_at', 'updated_at'),
}


def upgrade():
    for table, columns in COLUMNS.items():
        for column in columns:
            op.alter_column(table, column, existing_type=sa.DateTime(timezone=False),
                            type_=sa.DateTime(timezone=True), postgresql_using=f"{column} AT TIME ZONE 'UTC'")


def downgrade():
    for table, columns in COLUMNS.items():
        for column in columns:
            op.alter_column(table, column, existing_type=sa.DateTime(timezone=True),
                            type_=sa.DateTime(timezone=False), postgresql_using=f"{column} AT TIME ZONE 'UTC'")
