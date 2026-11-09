"""Procurement claims owned by the proposal preparation domain."""
from alembic import op
import sqlalchemy as sa

revision = "20261008_procurement_fencing"
down_revision = "20261007_montecarlo_fencing"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("procurement_jobs", sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("procurement_jobs", sa.Column("claim_token", sa.Uuid(), nullable=True))
    op.add_column("procurement_jobs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    # Legacy workers cannot have a token. Allow their old hard timeout to pass,
    # then recover normally. Drain old workers before deploying new workers.
    op.execute(sa.text("""UPDATE procurement_jobs SET lease_expires_at =
        COALESCE(started_at + interval '1920 seconds',
                 CURRENT_TIMESTAMP + interval '1920 seconds') WHERE status = 'RUNNING'"""))
    op.create_check_constraint("ck_procurement_job_nonnegative_attempt", "procurement_jobs", "attempt >= 0")
    op.create_index("ix_procurement_job_claims", "procurement_jobs", ["status", "lease_expires_at"])


def downgrade():
    op.drop_index("ix_procurement_job_claims", table_name="procurement_jobs")
    op.drop_constraint("ck_procurement_job_nonnegative_attempt", "procurement_jobs", type_="check")
    op.drop_column("procurement_jobs", "lease_expires_at")
    op.drop_column("procurement_jobs", "claim_token")
    op.drop_column("procurement_jobs", "attempt")
