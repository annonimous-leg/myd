"""Enforce v2 audit evidence, monotonic chain time, and retention-safe foreign keys."""
from alembic import op
import sqlalchemy as sa

revision = "20261028_audit_chain_guard"
down_revision = "20261014_proveedor_tenant"
branch_labels = None
depends_on = None


def upgrade():
    # Keep the database default at v1 so older app instances that do not know
    # about hash_version fail closed. The v2 writer explicitly sets 2.
    op.alter_column(
        "audit_ledger",
        "hash_version",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default="1",
    )

    # Append-only evidence must not be mutated or removed by FK SET NULL/CASCADE.
    bind = op.get_bind()
    foreign_keys = sa.inspect(bind).get_foreign_keys("audit_ledger")
    fk_specs = (
        ("user_id", "users", "fk_audit_ledger_user_id_restrict"),
        ("tenant_id", "tenants", "fk_audit_ledger_tenant_id_restrict"),
    )
    for column, target_table, replacement_name in fk_specs:
        matches = [
            fk for fk in foreign_keys
            if fk.get("constrained_columns") == [column]
            and fk.get("referred_table") == target_table
        ]
        if len(matches) != 1 or not matches[0].get("name"):
            raise RuntimeError(
                f"Se esperaba una clave foránea única para audit_ledger.{column}"
            )
        current = matches[0]
        options = current.get("options") or {}
        if current.get("name") == replacement_name and str(options.get("ondelete", "")).upper() == "RESTRICT":
            continue
        op.drop_constraint(current["name"], "audit_ledger", type_="foreignkey")
        op.create_foreign_key(
            replacement_name,
            "audit_ledger",
            target_table,
            [column],
            ["id"],
            ondelete="RESTRICT",
        )

    # The existing trigger remains attached to this replaced function.
    op.execute("""
    CREATE OR REPLACE FUNCTION audit_ledger_guard_insert() RETURNS trigger
    LANGUAGE plpgsql AS $$
    DECLARE
        expected_prev varchar(64);
        expected_prev_created_at timestamptz;
        chain_key text;
    BEGIN
        chain_key := NEW.tenant_id::text || '|' || NEW.entidad_tipo || '|' || NEW.entidad_id;
        PERFORM pg_advisory_xact_lock(hashtextextended(chain_key, 0));

        SELECT hash_registro, created_at
        INTO expected_prev, expected_prev_created_at
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
        IF expected_prev IS NOT NULL AND NEW.created_at <= expected_prev_created_at THEN
            RAISE EXCEPTION 'La marca de tiempo debe avanzar respecto del predecesor'
                USING ERRCODE = '23514';
        END IF;
        IF NEW.hash_registro !~ '^[0-9a-f]{64}$' THEN
            RAISE EXCEPTION 'Hash de auditoría inválido'
                USING ERRCODE = '23514';
        END IF;
        IF NEW.hash_version <> 2 THEN
            RAISE EXCEPTION 'Las nuevas entradas deben usar hash_version 2'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END $$;
    """)


def downgrade():
    raise RuntimeError(
        "Migración forward-only: no retirar garantías de integridad y retención de auditoría"
    )
