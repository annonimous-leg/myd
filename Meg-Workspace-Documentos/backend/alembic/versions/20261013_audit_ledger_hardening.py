"""Make audit ledger append-only and serialize each evidence chain.

Revision ID: 20261013_audit_ledger_hardening
Revises: 20261013_costeo_integral
"""
from alembic import op
import sqlalchemy as sa


revision = "20261013_audit_ledger_hardening"
down_revision = "20261013_costeo_integral"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "audit_ledger",
        sa.Column("hash_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint(
        "ck_audit_hash_version",
        "audit_ledger",
        "hash_version IN (1, 2)",
    )

    op.execute("""
    CREATE FUNCTION audit_ledger_guard_insert() RETURNS trigger
    LANGUAGE plpgsql AS $$
    DECLARE
        expected_prev varchar(64);
        chain_key text;
    BEGIN
        chain_key := NEW.tenant_id::text || '|' || NEW.entidad_tipo || '|' || NEW.entidad_id;
        PERFORM pg_advisory_xact_lock(hashtextextended(chain_key, 0));

        SELECT hash_registro INTO expected_prev
        FROM audit_ledger
        WHERE tenant_id = NEW.tenant_id
          AND entidad_tipo = NEW.entidad_tipo
          AND entidad_id = NEW.entidad_id
        ORDER BY created_at DESC, id DESC
        LIMIT 1;

        IF expected_prev IS DISTINCT FROM NEW.hash_previo THEN
            RAISE EXCEPTION 'La cadena de auditoría requiere el predecesor vigente'
                USING ERRCODE = '23514';
        END IF;
        IF NEW.hash_registro !~ '^[0-9a-f]{64}$' THEN
            RAISE EXCEPTION 'Hash de auditoría inválido'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END $$;
    """)

    op.execute("""
    CREATE FUNCTION audit_ledger_immutable() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'La bitácora de auditoría es inmutable'
            USING ERRCODE = '23514';
    END $$;
    """)

    op.execute("""
    CREATE TRIGGER tr_audit_ledger_chain
    BEFORE INSERT ON audit_ledger
    FOR EACH ROW EXECUTE FUNCTION audit_ledger_guard_insert()
    """)
    op.execute("""
    CREATE TRIGGER tr_audit_ledger_immutable
    BEFORE UPDATE OR DELETE ON audit_ledger
    FOR EACH ROW EXECUTE FUNCTION audit_ledger_immutable()
    """)
    op.execute("""
    CREATE TRIGGER tr_audit_ledger_no_truncate
    BEFORE TRUNCATE ON audit_ledger
    FOR EACH STATEMENT EXECUTE FUNCTION audit_ledger_immutable()
    """)


def downgrade():
    raise RuntimeError(
        "Migración forward-only: no retirar garantías de inmutabilidad de auditoría"
    )
