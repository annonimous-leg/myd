"""Restore a controlled backup in isolation and prove preservation across upgrade.

Never connects to a source installation. The target must be newly provisioned,
empty, named megalodon_rehearsal_*, and have no application writers. Reports are
private and never contain row values or connection credentials. This is evidence
for a database rehearsal, not certification of a deployed recovery or its RPO.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import psycopg2
from psycopg2 import sql
from sqlalchemy.engine import make_url

from scripts.postgres_backup import BackupInputError, connection, digest, restore

HISTORICAL = "20260914_workspace_bridge_tenant"
from scripts.migration_head import application_head

HEAD = application_head()
# Additive tables introduced after the supported historical revisions. They
# must exist after upgrade and must remain empty unless the source backup
# already contained them; historical rows are never synthesized by migration.
ADDITIVE_EMPTY_TABLES = frozenset({
    "series_indices_costos",
    "observaciones_indices_costos",
    "vinculos_indices_insumos",
    "retiros_indices_costos",
    "cargas_indices_costos",
    "trabajos_proceso",
    "ocr_jobs",
    "catalogo_importaciones",
    "catalogo_registros",
    "estimaciones_parametricas",
    "dibujos_bim",
})


def expected_added_tables(source_tables):
    """Return reviewed additive tables absent from the source backup."""
    return ADDITIVE_EMPTY_TABLES.difference(source_tables)


# Only migrations in this explicitly reviewed interval are supported.
RENAMES = {"catalog_terms": {"created_by_id": "creado_por_id",
                            "updated_by_id": "actualizado_por_id"}}
UTC_COLUMNS = {
    "tezcatlipoca_users": ("created_at", "last_login"),
    "user_sessions": ("created_at", "expires_at", "last_active"),
    "snapshots": ("created_at",),
    "tunnels": ("created_at", "expires_at", "closed_at"),
    "dead_drops": ("created_at", "expires_at"),
    "api_logs": ("timestamp",),
    "token_blacklist": ("expires_at", "revoked_at"),
    "system_settings": ("created_at", "updated_at"),
}
ROOT = Path(__file__).resolve().parents[1]


def migration_contract(filename):
    """Read trusted, frozen configuration; never invoke migration DDL here."""
    path = ROOT / "alembic" / "versions" / filename
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expected_templates_expression():
    first = migration_contract("20260914_requirement_source_extraction.py")
    profiles = migration_contract("20260914_dependency_extraction_profiles.py")
    structure = migration_contract("20260914_structural_source_tables_relations.py")
    cases = []
    for code, dependency in profiles.DEPENDENCY.items():
        payload = profiles.build(dependency)
        payload.update(table_rules=structure.TABLE_RULES, relations=structure.RELATIONS, structural_trace=True)
        cases.append(sql.SQL("WHEN tenant_id IS NULL AND active=true AND code={} THEN "
                             "jsonb_set(COALESCE(templates, '{{}}'::jsonb), '{{requirement_extraction}}', {}::jsonb, true)")
                     .format(sql.Literal(code), sql.Literal(json.dumps(payload))))
    # The first migration also initializes empty extraction config on active
    # tenant profiles. Later migrations only overwrite the global profiles.
    cases.append(sql.SQL("WHEN active=true AND code IN ('MX-FED-OBRA','MX-FED-CONAGUA-OBRA',"
                         "'MX-FED-SICT-OBRA','MX-LOCAL-STATE-OBRA','MX-FED-ADQ') AND "
                         "COALESCE(templates->'requirement_extraction', '{{}}'::jsonb) IN ('{{}}'::jsonb,'null'::jsonb) "
                         "THEN jsonb_set(COALESCE(templates, '{{}}'::jsonb), '{{requirement_extraction}}', {}::jsonb, true)")
                 .format(sql.Literal(json.dumps({"source_roles": first.CONFIG["source_roles"]}))))
    return sql.SQL("(CASE {} ELSE templates END)").format(sql.SQL(" ").join(cases))


def require(condition, message):
    if not condition:
        raise BackupInputError(message)


def validate_target(value):
    url = make_url(value)
    require(url.drivername in {"postgresql", "postgresql+asyncpg", "postgresql+psycopg2", "postgresql+psycopg"},
            "PostgreSQL rehearsal target required")
    require(bool(re.fullmatch(r"megalodon_rehearsal_[a-z0-9_]+", url.database or "")),
            "Target must be a dedicated megalodon_rehearsal_* database")
    # Normalize the dialect for Alembic's async environment; credentials remain
    # in the environment, never command arguments or reports.
    return url.set(drivername="postgresql+asyncpg").render_as_string(hide_password=False)


@contextmanager
def read_snapshot(uri, env):
    # Pass the explicit passfile to the driver, without changing global os.environ.
    with psycopg2.connect(uri, passfile=env.get("PGPASSFILE", "")) as conn:
        conn.set_session(isolation_level="REPEATABLE READ", readonly=True)
        with conn.cursor() as cursor:
            cursor.execute("SET LOCAL timezone TO 'UTC'")
            cursor.execute("SET LOCAL extra_float_digits TO 3")
            cursor.execute("SET LOCAL DateStyle TO 'ISO, YMD'")
            cursor.execute("SET LOCAL bytea_output TO 'hex'")
        yield conn


def inventory(conn):
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod)
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_attribute a ON a.attrelid=c.oid
            WHERE n.nspname='public' AND c.relkind IN ('r','p')
              AND c.relname <> 'alembic_version' AND a.attnum>0 AND NOT a.attisdropped
            ORDER BY c.relname COLLATE "C", a.attnum
        """)
        result = {}
        for table, column, kind in cursor:
            result.setdefault(table, []).append((column, kind))
        cursor.execute("SELECT version_num FROM public.alembic_version")
        versions = cursor.fetchall()
        require(len(versions) == 1, "Exactly one recorded Alembic revision required")
        return result, versions[0][0]


def projection_query(table, columns, migrated=False, source_transforms=False, historical_profile_ids=None,
                     recover_lost_jobs=False, has_jobs=False):
    expressions = []
    for original, kind in columns:
        name = RENAMES.get(table, {}).get(original, original) if migrated else original
        expression = sql.Identifier(name)
        if (migrated and table == 'observaciones_indices_costos' and original == 'valor'
                and kind == 'numeric(18,8)'):
            # Widening appends decimal zeros; compare the original column's
            # exact scale without changing or rounding any historical value.
            expression = sql.SQL('{}::numeric(18,8)').format(expression)
        if migrated and table == 'insumos' and original == 'cantidad' and kind == 'numeric(18,4)':
            # The catalogue migration appends zero decimals to historical
            # consumption. The post-upgrade guard below rejects any invented
            # extra fractional digits before this canonical comparison.
            expression = sql.SQL('{}::numeric(18,4)').format(expression)
        if source_transforms and table == "jurisdiction_profiles" and original == "templates":
            expression = expected_templates_expression()
        legacy_jobs = {'modelos_bim':('BIM_IFC','estado_procesamiento','error_procesamiento'),
                       'generaciones_bim_4d5d':('BIM_4D','estado','error'),
                       'analisis_clash':('BIM_CLASH','estado','error')}
        if recover_lost_jobs and table in legacy_jobs:
            kind, state, error = legacy_jobs[table]
            if original in (state, error):
                missing = (sql.SQL('NOT EXISTS (SELECT 1 FROM trabajos_proceso j WHERE j.entidad_id={}.id AND j.tipo={})')
                           .format(sql.Identifier(table),sql.Literal(kind)) if has_jobs else sql.SQL('true'))
                replacement = ('ERROR' if original == state else
                    'Trabajo anterior sin orden durable. Revise los parámetros y vuelva a solicitarlo.')
                expression = sql.SQL("CASE WHEN {} IN ('PENDIENTE','EN_PROCESO') AND {} THEN {} ELSE {} END").format(
                    sql.Identifier(state),missing,sql.Literal(replacement),expression)
        if (not migrated and original in UTC_COLUMNS.get(table, ())
                and kind == "timestamp without time zone"):
            expression = sql.SQL("({} AT TIME ZONE 'UTC')").format(expression)
        # PostgreSQL text preserves decimal scale and EWKB geometry. JSON is
        # only the unambiguous row envelope; the report receives hashes alone.
        expressions.append(sql.SQL("{}::text AS {}").format(expression, sql.Identifier(original)))
    where = sql.SQL("")
    if historical_profile_ids is not None and table == "jurisdiction_profiles":
        where = sql.SQL("WHERE id=ANY({}::uuid[])").format(sql.Literal(historical_profile_ids))
    return sql.SQL("""
        SELECT row_to_json(p)::text FROM (SELECT {} FROM {} {}) p
        ORDER BY row_to_json(p)::text COLLATE "C"
    """).format(sql.SQL(", ").join(expressions), sql.Identifier("public", table), where)


def fingerprints(conn, tables, migrated=False, source_transforms=False, historical_profile_ids=None,
                 recover_lost_jobs=False):
    result = {}
    for number, (table, columns) in enumerate(tables.items()):
        h, count = hashlib.sha256(), 0
        # A server cursor streams the sorted rows; memory is bounded even for a
        # real historical database. Duplicate rows participate in the digest.
        with conn.cursor(name=f"rehearsal_rows_{number}") as cursor:
            cursor.itersize = 1000
            cursor.execute(projection_query(table, columns, migrated, source_transforms, historical_profile_ids,
                                            recover_lost_jobs, 'trabajos_proceso' in tables))
            for (row,) in cursor:
                h.update(row.encode("utf-8") + b"\n")
                count += 1
        result[table] = {"rows": count, "historical_columns_sha256": h.hexdigest()}
    return result


def compare(before, after):
    require(before == after, "Historical row preservation failed; keep target isolated for investigation")


def verify_new_configuration(conn, profile_ids, private_profile_existed):
    """Check every deterministic field of the two documented migration seeds."""
    bridge = migration_contract("20260914_bridge_field_contracts.py")
    with conn.cursor() as cursor:
        cursor.execute("SELECT tenant_id, version, is_active, fields, creado_por_id, actualizado_por_id, "
                       "created_at=updated_at AND created_at IS NOT NULL FROM public.bridge_field_contracts")
        rows = cursor.fetchall()
        require(len(rows) == 1 and rows[0] == (None, 1, True, bridge._DEFAULT_FIELDS, None, None, True),
                "Unexpected seeded bridge configuration")
        cursor.execute("SELECT tenant_id, code, authority, government_level, matter, portal_code, "
                       "profile_version, ruleset, active, templates FROM public.jurisdiction_profiles "
                       "WHERE NOT(id=ANY(%s::uuid[]))", (profile_ids,))
        rows = cursor.fetchall()
        require(len(rows) == (0 if private_profile_existed else 1), "Unexpected inserted jurisdiction profiles")
        if rows:
            profiles = migration_contract("20260914_dependency_extraction_profiles.py")
            structure = migration_contract("20260914_structural_source_tables_relations.py")
            payload = profiles.build(profiles.DEPENDENCY["MX-PRIVATE-OBRA"])
            payload.update(table_rules=structure.TABLE_RULES, relations=structure.RELATIONS, structural_trace=True)
            require(rows[0] == (None, "MX-PRIVATE-OBRA", "PRIVADA", "PRIVATE", "PRIVATE_WORKS", "INTERNAL",
                                1, {}, True, {"requirement_extraction": payload}),
                    "Unexpected seeded private profile")


def checked_command(command, env, label):
    # Tool logs/tracebacks can contain private values. Only a sanitized failure
    # leaves this process. The retained target enables local investigation.
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
    require(result.returncode == 0, f"{label} failed; target retained for private investigation")


def run_rehearsal(backup, uri, env):
    started = time.monotonic()
    restore_started = time.monotonic()
    restore(uri, env, backup)
    restore_seconds = time.monotonic() - restore_started
    with read_snapshot(uri, env) as conn:
        tables, revision = inventory(conn)
        require(revision in {HISTORICAL, '20260930_identity_authority', '20261001_indices_materiales',
                            '20261001_indices_revision', '20261006_bim_integridad',
                            '20261006_trabajos_durables', HEAD},
                "Backup revision outside the reviewed migration interval")
        before = fingerprints(conn, tables)
        expected = (fingerprints(conn, tables, source_transforms=revision == HISTORICAL,
                                 recover_lost_jobs=True) if revision != HEAD else before)
        with conn.cursor() as cursor:
            cursor.execute("SELECT id::text FROM public.jurisdiction_profiles ORDER BY id")
            profile_ids = [row[0] for row in cursor]
            cursor.execute("SELECT EXISTS(SELECT 1 FROM public.jurisdiction_profiles "
                           "WHERE tenant_id IS NULL AND code='MX-PRIVATE-OBRA')")
            private_profile_existed = cursor.fetchone()[0]
    upgrade_started = time.monotonic()
    checked_command([sys.executable, "-m", "alembic", "upgrade", HEAD], os.environ.copy(), "Historical upgrade")
    upgrade_seconds = time.monotonic() - upgrade_started
    with read_snapshot(uri, env) as conn:
        current, target = inventory(conn)
        expected_added = expected_added_tables(tables)
        expected_tables = set(tables) | expected_added
        if revision == HISTORICAL:
            expected_tables.add("bridge_field_contracts")
        require(target == HEAD and set(current) == expected_tables, "Unexpected revision or historical table changes")
        for table in expected_added:
            with conn.cursor() as cursor:
                cursor.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier('public', table)))
                require(cursor.fetchone()[0] == 0, 'Historical upgrade must not invent observations, mappings or durable jobs')
        if ('cantidad', 'numeric(18,4)') in tables.get('insumos', []):
            with conn.cursor() as cursor:
                cursor.execute('SELECT count(*) FROM insumos WHERE cantidad <> round(cantidad, 4)')
                require(cursor.fetchone()[0] == 0, 'Historical upgrade invented extra consumption decimals')
        after = fingerprints(conn, tables, migrated=revision != HEAD,
                             historical_profile_ids=profile_ids if revision == HISTORICAL else None)
        compare(expected, after)
        if revision == HISTORICAL:
            verify_new_configuration(conn, profile_ids, private_profile_existed)
    checked_command([sys.executable, "-m", "scripts.verify_migrated_schema"], os.environ.copy(), "Migrated schema check")
    return {"status": "database_rehearsal_passed", "source_revision": revision,
            "target_revision": target, "backup_sha256": digest(backup),
            "tables": before, "expected_migrated_historical_columns": expected,
            "tables_verified": len(before),
            "rows_verified": sum(t["rows"] for t in before.values()),
            "historical_values_preserved": True,
            "documented_configuration_transforms_verified": revision == HISTORICAL,
            "timings_seconds": {"restore": round(restore_seconds, 3),
                                "upgrade": round(upgrade_seconds, 3),
                                "database_rehearsal_total": round(time.monotonic() - started, 3)},
            "production_deployment_certified": False, "rpo_seconds": None, "production_rto_seconds": None,
            "remaining": ["representativeness of supplied historical data", "cluster roles and runtime grants",
                          "external artifacts and storage references", "JWT key rotation after recovery",
                          "deployed application flows", "measured production RPO/RTO"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        os.environ["DATABASE_URL"] = validate_target(os.environ["DATABASE_URL"])
        require(args.backup.is_file(), "Controlled backup file required")
        # Reserve the report before any database write; never overwrite an old
        # report, supplied backup, symlink or unrelated file.
        with args.report.open("x", encoding="utf-8") as report:
            os.chmod(args.report, 0o600)
            try:
                with connection() as (uri, env):
                    result = run_rehearsal(args.backup, uri, env)
                result["completed_at_utc"] = datetime.now(UTC).isoformat()
                report.write(json.dumps(result, indent=2) + "\n")
                report.flush()
                os.fsync(report.fileno())
            except Exception:
                report.write(json.dumps({"status": "failed", "production_deployment_certified": False,
                                         "target_retained": True}) + "\n")
                raise
    except BackupInputError as exc:
        raise SystemExit(str(exc)) from None
    except Exception:
        raise SystemExit("Historical rehearsal failed; inspect the isolated target privately") from None
    print("Database rehearsal passed; private report written. Production GO remains unproven.")


if __name__ == "__main__":
    main()
