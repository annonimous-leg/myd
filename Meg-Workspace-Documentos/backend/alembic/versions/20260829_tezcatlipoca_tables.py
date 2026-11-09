"""Create the embedded subsystem tables before its audit tenant migration.

Tezcatlipoca uses its own metadata; both registries are now included in
Alembic autogenerate. Creation precedes f4c2d7e9a1b6, which alters api_logs.
No application create_all is required for a fresh installation.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260829_tezcatlipoca_tables"
down_revision = "d5e8f7a1c2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    if "tezcatlipoca_users" not in existing:
        op.create_table(
            "tezcatlipoca_users",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("username", sa.String(50), nullable=False),
            sa.Column("password_hash", sa.String(255), nullable=False),
            sa.Column("tier", sa.String(20), server_default="restricted"),
            sa.Column("created_at", sa.DateTime, nullable=True),
            sa.Column("last_login", sa.DateTime, nullable=True),
            sa.Column("is_active", sa.Boolean, server_default=sa.true()),
            sa.Column("api_calls_today", sa.Integer, server_default="0"),
            sa.Column("api_calls_total", sa.Integer, server_default="0"),
            sa.Column("megalodon_user_id", sa.String(36), nullable=True),
            sa.Column("tenant_id", sa.String(36), nullable=True),
            sa.UniqueConstraint("username", name="uq_tezcatlipoca_users_username"),
            sa.UniqueConstraint("megalodon_user_id", name="uq_tezcatlipoca_users_megalodon_user_id"),
        )
        op.create_index("ix_tezcatlipoca_users_id", "tezcatlipoca_users", ["id"])
        op.create_index("ix_tezcatlipoca_users_username", "tezcatlipoca_users", ["username"])
        op.create_index("ix_tezcatlipoca_users_megalodon_user_id", "tezcatlipoca_users", ["megalodon_user_id"])
        op.create_index("ix_tezcatlipoca_users_tenant_id", "tezcatlipoca_users", ["tenant_id"])

    if "user_sessions" not in existing:
        op.create_table(
            "user_sessions",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer, nullable=False),
            sa.Column("session_token", sa.String(255), nullable=False),
            sa.Column("jti", sa.String(255), nullable=False),
            sa.Column("ip_address", sa.String(45), nullable=True),
            sa.Column("user_agent", sa.String(500), nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=True),
            sa.Column("expires_at", sa.DateTime, nullable=False),
            sa.Column("last_active", sa.DateTime, nullable=True),
            sa.Column("is_active", sa.Boolean, server_default=sa.true()),
            sa.UniqueConstraint("session_token", name="uq_user_sessions_session_token"),
        )
        op.create_index("ix_user_sessions_id", "user_sessions", ["id"])
        op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
        op.create_index("ix_user_sessions_session_token", "user_sessions", ["session_token"])

    if "snapshots" not in existing:
        op.create_table(
            "snapshots",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("user_id", sa.Integer, nullable=True),
            sa.Column("tenant_id", sa.String(36), nullable=True),
            sa.Column("layers", sa.JSON, nullable=True),
            sa.Column("viewport", sa.JSON, nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=True),
        )
        op.create_index("ix_snapshots_id", "snapshots", ["id"])
        op.create_index("ix_snapshots_tenant_id", "snapshots", ["tenant_id"])

    if "tunnels" not in existing:
        op.create_table(
            "tunnels",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(36), nullable=False),
            sa.Column("owner_user_id", sa.Integer, nullable=False),
            sa.Column("owner_username", sa.String(255), nullable=True),
            sa.Column("destination", sa.String(512), nullable=False),
            sa.Column("encryption", sa.String(50), server_default="aes-256-gcm"),
            sa.Column("status", sa.String(20), server_default="active"),
            sa.Column("bytes_transferred", sa.Integer, server_default="0"),
            sa.Column("packets", sa.Integer, server_default="0"),
            sa.Column("latency_ms", sa.Float, nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=True),
            sa.Column("expires_at", sa.DateTime, nullable=False),
            sa.Column("closed_at", sa.DateTime, nullable=True),
        )
        op.create_index("ix_tunnels_tenant_id", "tunnels", ["tenant_id"])

    if "dead_drops" not in existing:
        op.create_table(
            "dead_drops",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("tenant_id", sa.String(36), nullable=False),
            sa.Column("owner_user_id", sa.Integer, nullable=False),
            sa.Column("owner_username", sa.String(255), nullable=True),
            sa.Column("encrypted_payload", sa.LargeBinary, nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=True),
            sa.Column("expires_at", sa.DateTime, nullable=False),
            sa.Column("max_reads", sa.Integer, server_default="1"),
            sa.Column("reads", sa.Integer, server_default="0"),
            sa.Column("status", sa.String(20), server_default="active"),
        )
        op.create_index("ix_dead_drops_tenant_id", "dead_drops", ["tenant_id"])

    if "api_logs" not in existing:
        # Se crea ya con tenant_id incluido -- lo que antes agregaba
        # f4c2d7e9a1b6_tez_audit_tenant_scope.py vía ALTER condicional
        # sobre una tabla que, en una base nueva, nunca existió. Esa
        # migración sigue siendo un no-op inofensivo después de esta.
        op.create_table(
            "api_logs",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer, nullable=True),
            sa.Column("tenant_id", sa.String(36), nullable=True),
            sa.Column("endpoint", sa.String(255), nullable=False),
            sa.Column("method", sa.String(10), nullable=False),
            sa.Column("status_code", sa.Integer, nullable=True),
            sa.Column("response_time_ms", sa.Float, nullable=True),
            sa.Column("ip_address", sa.String(45), nullable=True),
            sa.Column("user_agent", sa.String(500), nullable=True),
            sa.Column("timestamp", sa.DateTime, nullable=True),
        )
        op.create_index("ix_api_logs_id", "api_logs", ["id"])
        op.create_index("ix_api_logs_tenant_id", "api_logs", ["tenant_id"])

    if "token_blacklist" not in existing:
        op.create_table(
            "token_blacklist",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("token_jti", sa.String(255), nullable=False),
            sa.Column("expires_at", sa.DateTime, nullable=False),
            sa.Column("revoked_at", sa.DateTime, nullable=True),
            sa.UniqueConstraint("token_jti", name="uq_token_blacklist_token_jti"),
        )
        op.create_index("ix_token_blacklist_id", "token_blacklist", ["id"])
        op.create_index("ix_token_blacklist_token_jti", "token_blacklist", ["token_jti"])

    if "system_settings" not in existing:
        op.create_table(
            "system_settings",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.String(36), nullable=True),
            sa.Column("key", sa.String(255), nullable=False),
            sa.Column("value", sa.JSON, nullable=False),
            sa.Column("created_at", sa.DateTime, nullable=True),
            sa.Column("updated_at", sa.DateTime, nullable=True),
        )
        op.create_index("ix_system_settings_id", "system_settings", ["id"])
        op.create_index("ix_system_settings_tenant_id", "system_settings", ["tenant_id"])
        op.create_index("ix_system_settings_key", "system_settings", ["key"])


def downgrade() -> None:
    for table in (
        "system_settings", "token_blacklist", "api_logs", "dead_drops",
        "tunnels", "snapshots", "user_sessions", "tezcatlipoca_users",
    ):
        op.drop_table(table)
