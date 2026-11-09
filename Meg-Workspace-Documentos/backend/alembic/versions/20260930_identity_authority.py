"""Invalidate sessions transactionally when identity authority changes."""
from alembic import op
import sqlalchemy as sa

revision = "20260930_identity_authority"
down_revision = "20260930_tez_timestamps"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("auth_version", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    # Resetting these counters on a later upgrade can resurrect revoked JWTs.
    # Reject before any DDL: recovery must preserve authority or rotate signing
    # keys after restoring a verified backup in an isolated environment.
    raise RuntimeError(
        "Identity authority migration is forward-only: auth_version must not be "
        "discarded. Restore a verified backup offline and rotate JWT signing "
        "keys before reopening traffic, or deploy a forward repair."
    )
