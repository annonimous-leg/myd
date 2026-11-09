"""Pin approvals to exact originals and protect their audit records in PostgreSQL.

Existing approvals are deliberately NOT backfilled: their real reviewed bytes
cannot be reconstructed after the fact. A new revision/reapproval is required.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261109_approved_artifact_bytes"
down_revision = "20261105_bim_drawing_pdf"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tender_approvals", sa.Column("artifact_manifest_hash", sa.String(64), nullable=True))
    op.add_column("tender_approvals", sa.Column("artifact_manifest", JSONB(), nullable=True))
    op.create_check_constraint(
        "ck_tender_approval_sha256_format", "tender_approvals",
        "artifact_manifest_hash IS NULL OR artifact_manifest_hash ~ '^[0-9a-f]{64}$'",
    )
    op.execute("""
        CREATE FUNCTION megalodon_guard_approved_decision() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.decision = 'APPROVED' THEN
            RAISE EXCEPTION 'An approved decision is immutable: create a new tender revision'
              USING ERRCODE = 'integrity_constraint_violation';
          END IF;
          IF TG_OP = 'UPDATE' THEN RETURN NEW; END IF;
          RETURN OLD;
        END $$;
    """)
    op.execute("""
        CREATE TRIGGER trg_approved_decision_immutable
        BEFORE UPDATE OR DELETE ON tender_approvals
        FOR EACH ROW EXECUTE FUNCTION megalodon_guard_approved_decision();
    """)
    op.execute("""
        CREATE FUNCTION megalodon_guard_approved_artifact_original() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE pinned BOOLEAN;
        BEGIN
          IF TG_OP = 'UPDATE' AND
             OLD.tender_id IS NOT DISTINCT FROM NEW.tender_id AND
             OLD.tenant_id IS NOT DISTINCT FROM NEW.tenant_id AND
             OLD.artifact_code IS NOT DISTINCT FROM NEW.artifact_code AND
             OLD.version IS NOT DISTINCT FROM NEW.version AND
             OLD.media_type IS NOT DISTINCT FROM NEW.media_type AND
             OLD.storage_path IS NOT DISTINCT FROM NEW.storage_path AND
             OLD.content_hash IS NOT DISTINCT FROM NEW.content_hash AND
             OLD.source_model_hash IS NOT DISTINCT FROM NEW.source_model_hash AND
             (OLD.metadata->'signature_required') IS NOT DISTINCT FROM (NEW.metadata->'signature_required') AND
             (OLD.metadata->'submission_eligible') IS NOT DISTINCT FROM (NEW.metadata->'submission_eligible') AND
             (OLD.metadata->'reference_only') IS NOT DISTINCT FROM (NEW.metadata->'reference_only') THEN
            RETURN NEW;
          END IF;
          SELECT EXISTS (
            SELECT 1 FROM tender_approvals a
            WHERE a.tenant_id = OLD.tenant_id AND a.tender_id = OLD.tender_id
              AND a.decision = 'APPROVED'
              AND a.artifact_manifest->'artifacts' @>
                  jsonb_build_array(jsonb_build_object('id', OLD.id::text))
          ) INTO pinned;
          IF pinned THEN
            RAISE EXCEPTION 'Original artifact approved by a human cannot be replaced or deleted'
              USING ERRCODE = 'integrity_constraint_violation';
          END IF;
          IF TG_OP = 'UPDATE' THEN RETURN NEW; END IF;
          RETURN OLD;
        END $$;
    """)
    op.execute("""
        CREATE TRIGGER trg_approved_artifact_original_immutable
        BEFORE UPDATE OR DELETE ON tender_artifacts
        FOR EACH ROW EXECUTE FUNCTION megalodon_guard_approved_artifact_original();
    """)


def downgrade():
    # Never silently discard approved fingerprints or the audit safeguard.
    result = op.get_bind().execute(sa.text(
        "SELECT 1 FROM tender_approvals WHERE artifact_manifest_hash IS NOT NULL LIMIT 1"
    )).first()
    if result:
        raise RuntimeError("Migración forward-only: existen aprobaciones fijadas por hash")
    op.execute("DROP TRIGGER IF EXISTS trg_approved_artifact_original_immutable ON tender_artifacts")
    op.execute("DROP FUNCTION IF EXISTS megalodon_guard_approved_artifact_original()")
    op.execute("DROP TRIGGER IF EXISTS trg_approved_decision_immutable ON tender_approvals")
    op.execute("DROP FUNCTION IF EXISTS megalodon_guard_approved_decision()")
    op.drop_constraint("ck_tender_approval_sha256_format", "tender_approvals", type_="check")
    op.drop_column("tender_approvals", "artifact_manifest")
    op.drop_column("tender_approvals", "artifact_manifest_hash")
