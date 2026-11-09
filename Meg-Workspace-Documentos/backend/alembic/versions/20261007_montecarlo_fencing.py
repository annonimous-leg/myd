"""Fenced Monte Carlo worker claims, maintained within its own domain."""
from alembic import op
import sqlalchemy as sa

revision = "20261007_montecarlo_fencing"
down_revision = "20261007_partida_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "monte_carlo_runs",
        sa.Column("attempt", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "monte_carlo_runs",
        sa.Column("execution_token", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "monte_carlo_runs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Historical EN_PROCESO rows may still belong to an earlier worker
    # version. Allow the old hard limit + grace before reclaiming them.
    op.execute(sa.text("""
        UPDATE monte_carlo_runs
        SET lease_expires_at = COALESCE(
            started_at + INTERVAL '1320 seconds',
            NOW() + INTERVAL '1320 seconds'
        )
        WHERE estado = 'EN_PROCESO'
    """))
    op.create_check_constraint(
        "ck_montecarlo_nonnegative_attempt",
        "monte_carlo_runs",
        "attempt >= 0",
    )
    op.create_index(
        "ix_montecarlo_claims",
        "monte_carlo_runs",
        ["estado", "lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_montecarlo_claims", table_name="monte_carlo_runs")
    op.drop_constraint(
        "ck_montecarlo_nonnegative_attempt",
        "monte_carlo_runs",
        type_="check",
    )
    op.drop_column("monte_carlo_runs", "lease_expires_at")
    op.drop_column("monte_carlo_runs", "execution_token")
    op.drop_column("monte_carlo_runs", "attempt")
