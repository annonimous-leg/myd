"""Read-only inventory for an existing Supabase/PostgreSQL database.

This command uses DATABASE_URL (the runtime DML identity), never the DDL
migration credential. It executes SET TRANSACTION READ ONLY before inspecting
schema/data metadata and never prints prices, customer rows, or connection URLs.
Run from backend/: python -m scripts.supabase_preflight
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlsplit

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


CATALOG_TABLES = (
    "catalogos_apu",
    "conceptos_catalogo",
    "insumos_catalogo",
    "catalogo_fuentes",
    "catalogo_importaciones",
    "catalogo_registros",
    "precios_unitarios_asignados",
)

NATURAL_KEYS = {
    "catalogos_apu": ("tenant_id", "clave", "fuente", "zona_economica"),
    "conceptos_catalogo": ("clave", "fuente_id", "zona_economica"),
    "insumos_catalogo": ("clave", "fuente_id", "zona_economica", "tipo"),
    "catalogo_registros": ("importacion_id", "tabla", "entidad_id"),
}

PRICE_COLUMNS = {
    "catalogos_apu": "precio_unitario",
    "conceptos_catalogo": "precio_unitario",
    "insumos_catalogo": "precio_unitario",
    "precios_unitarios_asignados": "precio_asignado",
}

SOURCE_GROUPS = {
    "catalogos_apu": (
        "SELECT COALESCE(fuente, '[sin fuente]') AS source, COUNT(*)::bigint AS records, "
        "MIN(NULLIF(vigencia_inicio, '')) AS earliest_valid_from, "
        "MAX(NULLIF(vigencia_fin, '')) AS latest_valid_to "
        "FROM public.catalogos_apu GROUP BY COALESCE(fuente, '[sin fuente]') ORDER BY source"
    ),
    "conceptos_catalogo": (
        "SELECT COALESCE(f.nombre, '[fuente sin nombre]') AS source, "
        "COUNT(*)::bigint AS records, MIN(NULLIF(f.vigencia_inicio, '')) AS earliest_valid_from, "
        "MAX(NULLIF(f.vigencia_fin, '')) AS latest_valid_to "
        "FROM public.conceptos_catalogo AS item "
        "LEFT JOIN public.catalogo_fuentes AS f ON f.id = item.fuente_id "
        "GROUP BY COALESCE(f.nombre, '[fuente sin nombre]') ORDER BY source"
    ),
    "insumos_catalogo": (
        "SELECT COALESCE(f.nombre, '[fuente sin nombre]') AS source, "
        "COUNT(*)::bigint AS records, MIN(NULLIF(f.vigencia_inicio, '')) AS earliest_valid_from, "
        "MAX(NULLIF(f.vigencia_fin, '')) AS latest_valid_to "
        "FROM public.insumos_catalogo AS item "
        "LEFT JOIN public.catalogo_fuentes AS f ON f.id = item.fuente_id "
        "GROUP BY COALESCE(f.nombre, '[fuente sin nombre]') ORDER BY source"
    ),
    "catalogo_registros": (
        "SELECT COALESCE(fuente_id, '[sin fuente]') AS source, "
        "COUNT(*)::bigint AS records, NULL::text AS earliest_valid_from, "
        "NULL::text AS latest_valid_to FROM public.catalogo_registros "
        "GROUP BY COALESCE(fuente_id, '[sin fuente]') ORDER BY source"
    ),
}


def expected_alembic_heads() -> list[str]:
    """Resolve the repository's migration heads without connecting to the DB."""
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    return sorted(ScriptDirectory.from_config(config).get_heads())


async def _columns(connection: AsyncConnection, table: str) -> set[str]:
    rows = await connection.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :table"
        ),
        {"table": table},
    )
    return {str(row[0]) for row in rows}


async def collect_preflight(
    connection: AsyncConnection,
    *,
    expected_heads: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Collect metadata/counts inside a PostgreSQL read-only transaction."""
    if connection.dialect.name != "postgresql":
        raise RuntimeError("Supabase preflight requires a PostgreSQL connection")

    # Must be the first statement in the transaction. PostgreSQL rejects all
    # writes and DDL for the remainder of this transaction.
    await connection.execute(text("SET TRANSACTION READ ONLY"))

    identity = (
        await connection.execute(
            text(
                "SELECT current_database() AS database_name, "
                "current_user AS database_role, "
                "current_setting('server_version') AS server_version"
            )
        )
    ).mappings().one()

    table_rows = (
        await connection.execute(
            text(
                "SELECT table_schema, table_name FROM information_schema.tables "
                "WHERE table_type = 'BASE TABLE' "
                "AND table_schema NOT IN ('pg_catalog', 'information_schema') "
                "AND table_schema NOT LIKE 'pg_toast%' "
                "ORDER BY table_schema, table_name"
            )
        )
    ).mappings().all()
    existing_tables = {
        str(row["table_name"]) for row in table_rows if row["table_schema"] == "public"
    }
    schemas = sorted({str(row["table_schema"]) for row in table_rows})
    candidate_markers = ("price", "precio", "cost", "costo", "catalog", "catalogo", "apu", "insumo", "tarifa")
    catalog_candidates = []
    for row in table_rows:
        schema_name, table_name = str(row["table_schema"]), str(row["table_name"])
        folded = f"{schema_name}.{table_name}".casefold()
        if not any(marker in folded for marker in candidate_markers):
            continue
        can_select = bool(
            await connection.scalar(
                text(
                    "SELECT has_table_privilege("
                    "current_user, "
                    "format('%I.%I', CAST(:schema_name AS text), CAST(:table_name AS text)), "
                    "'SELECT')"
                ),
                {"schema_name": schema_name, "table_name": table_name},
            )
        )
        quoted_name = await connection.scalar(
            text(
                "SELECT format('%I.%I', CAST(:schema_name AS text), CAST(:table_name AS text))"
            ),
            {"schema_name": schema_name, "table_name": table_name},
        )
        row_count = None
        if can_select:
            row_count = int(await connection.scalar(text(f"SELECT COUNT(*) FROM {quoted_name}")) or 0)
        catalog_candidates.append(
            {
                "schema": schema_name,
                "table": table_name,
                "select_allowed": can_select,
                "row_count": row_count,
            }
        )

    extension_rows = await connection.execute(
        text("SELECT extname, extversion FROM pg_extension ORDER BY extname")
    )
    extensions = {str(row[0]): str(row[1]) for row in extension_rows}

    applied_revisions: list[str] = []
    if "alembic_version" in existing_tables:
        revision_rows = await connection.execute(
            text("SELECT version_num FROM public.alembic_version ORDER BY version_num")
        )
        applied_revisions = [str(row[0]) for row in revision_rows]
    expected = sorted(str(head) for head in (expected_heads or []))
    migrations = {
        "applied_revisions": applied_revisions,
        "expected_heads": expected,
        "at_expected_head": bool(expected) and applied_revisions == expected,
        "revision_table_present": "alembic_version" in existing_tables,
    }

    catalog: dict[str, Any] = {}
    for table in CATALOG_TABLES:
        present = table in existing_tables
        entry: dict[str, Any] = {"present": present, "row_count": None}
        if not present:
            catalog[table] = entry
            continue

        # Identifiers come only from the fixed allow-list above.
        quoted_table = f'public."{table}"'
        row_count = await connection.scalar(text(f"SELECT COUNT(*) FROM {quoted_table}"))
        entry["row_count"] = int(row_count or 0)

        columns = await _columns(connection, table)
        key_columns = NATURAL_KEYS.get(table)
        if key_columns and set(key_columns).issubset(columns):
            group = ", ".join(
                f'COALESCE("{column}"::text, \'<NULL>\')' for column in key_columns
            )
            duplicate_count = await connection.scalar(
                text(
                    f"SELECT COUNT(*) FROM (SELECT 1 FROM {quoted_table} "
                    f"GROUP BY {group} HAVING COUNT(*) > 1) AS duplicate_keys"
                )
            )
            entry["duplicate_natural_key_groups"] = int(duplicate_count or 0)
        elif key_columns:
            entry["duplicate_natural_key_groups"] = None
            entry["duplicate_check"] = "required_columns_missing"

        price_column = PRICE_COLUMNS.get(table)
        if price_column and price_column in columns:
            quoted_column = f'"{price_column}"'
            bad_prices = await connection.scalar(
                text(
                    f"SELECT COUNT(*) FROM {quoted_table} "
                    f"WHERE {quoted_column} IS NULL OR {quoted_column} <= 0"
                )
            )
            entry["null_or_nonpositive_price_rows"] = int(bad_prices or 0)

        source_query = SOURCE_GROUPS.get(table)
        source_requirements = {
            "catalogos_apu": {"fuente", "vigencia_inicio", "vigencia_fin"},
            "conceptos_catalogo": {"fuente_id"},
            "insumos_catalogo": {"fuente_id"},
            "catalogo_registros": {"fuente_id"},
        }
        if table in {"conceptos_catalogo", "insumos_catalogo"} and "catalogo_fuentes" not in existing_tables:
            source_query = (
                f"SELECT COALESCE(fuente_id::text, '[sin fuente]') AS source, "
                f"COUNT(*)::bigint AS records, NULL::text AS earliest_valid_from, "
                f"NULL::text AS latest_valid_to FROM public.{table} "
                f"GROUP BY COALESCE(fuente_id::text, '[sin fuente]') ORDER BY source"
            )
        required_columns = source_requirements.get(table, set())
        if table in {"conceptos_catalogo", "insumos_catalogo"} and source_query and "catalogo_fuentes" in existing_tables:
            required_columns = required_columns | {"id"}
            source_columns = await _columns(connection, "catalogo_fuentes")
            if not {"id", "nombre", "vigencia_inicio", "vigencia_fin"}.issubset(source_columns):
                source_query = None
        if source_query and required_columns.issubset(columns):
            source_rows = (await connection.execute(text(source_query))).mappings().all()
            entry["source_distribution"] = [
                {
                    "source": str(row["source"]),
                    "records": int(row["records"]),
                    "earliest_valid_from": row["earliest_valid_from"],
                    "latest_valid_to": row["latest_valid_to"],
                }
                for row in source_rows
            ]
        elif table in SOURCE_GROUPS:
            entry["source_distribution"] = None
            entry["source_distribution_check"] = "required_columns_missing"
        catalog[table] = entry

    present_catalog_tables = [name for name in CATALOG_TABLES if name in existing_tables]
    table_literals = ", ".join("'" + name + "'" for name in present_catalog_tables)
    if present_catalog_tables:
        rls_rows = (
            await connection.execute(
                text(
                    "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, "
                    "COUNT(DISTINCT p.oid)::int AS policy_count "
                    "FROM pg_class AS c JOIN pg_namespace AS n ON n.oid = c.relnamespace "
                    "LEFT JOIN pg_policy AS p ON p.polrelid = c.oid "
                    f"WHERE n.nspname = 'public' AND c.relname IN ({table_literals}) "
                    "GROUP BY c.relname, c.relrowsecurity, c.relforcerowsecurity "
                    "ORDER BY c.relname"
                )
            )
        ).mappings().all()
        rls = {
            str(row["relname"]): {
                "enabled": bool(row["relrowsecurity"]),
                "forced": bool(row["relforcerowsecurity"]),
                "policy_count": int(row["policy_count"]),
            }
            for row in rls_rows
        }
        grant_rows = (
            await connection.execute(
                text(
                    "SELECT table_name, grantee, privilege_type "
                    "FROM information_schema.role_table_grants "
                    "WHERE table_schema = 'public' "
                    f"AND table_name IN ({table_literals}) "
                    "AND grantee IN ('anon', 'authenticated') "
                    "ORDER BY grantee, table_name, privilege_type"
                )
            )
        ).mappings().all()
        public_api_grants = [
            {
                "table": str(row["table_name"]),
                "role": str(row["grantee"]),
                "privilege": str(row["privilege_type"]),
            }
            for row in grant_rows
        ]
        index_rows = (
            await connection.execute(
                text(
                    "SELECT tablename, indexname FROM pg_indexes "
                    f"WHERE schemaname = 'public' AND tablename IN ({table_literals}) "
                    "ORDER BY tablename, indexname"
                )
            )
        ).mappings().all()
        indexes: dict[str, list[str]] = {table: [] for table in present_catalog_tables}
        for row in index_rows:
            indexes[str(row["tablename"])].append(str(row["indexname"]))
    else:
        rls, public_api_grants, indexes = {}, [], {}

    schema_privileges = (
        await connection.execute(
            text(
                "SELECT has_schema_privilege(current_user, 'public', 'CREATE') AS can_create_public_objects, "
                "has_database_privilege(current_user, current_database(), 'CREATE') AS can_create_database_objects"
            )
        )
    ).mappings().one()

    return {
        "read_only": True,
        "count_semantics": (
            "Counts reflect rows visible to current_user. PostgreSQL row-level security may filter them; "
            "compare with an independently authorized inventory before treating a low/zero count as absence."
        ),
        "database": {
            "name": str(identity["database_name"]),
            "role": str(identity["database_role"]),
            "server_version": str(identity["server_version"]),
        },
        "extensions": extensions,
        "schemas": schemas,
        "alembic": migrations,
        "catalog": {
            "candidate_tables_across_schemas": catalog_candidates,
            # Counts are intentionally separate: source records, projections,
            # imports and assigned prices are different entities, not additive.
            "tables": catalog,
            "unique_and_nonunique_indexes": indexes,
        },
        "security": {
            "row_level_security": rls,
            "anon_authenticated_table_grants": public_api_grants,
            "runtime_role_can_create_public_objects": bool(schema_privileges["can_create_public_objects"]),
            "runtime_role_can_create_database_objects": bool(schema_privileges["can_create_database_objects"]),
        },
        "preservation": {
            "writes_performed": False,
            "prices_reimported": False,
            "rows_or_objects_exported": False,
        },
        "manual_checks_required": [
            "Confirm Data API is disabled for domain tables in Supabase project settings.",
            "Confirm the DDL role and DML role point to the same intended Supabase project/database.",
            "Verify a restorable database backup and Storage-object backup before any migration.",
            "Compare these independent table counts with the existing 23,000-price inventory before importing anything.",
        ],
    }


async def collect_storage_preflight(
    *,
    supabase_url: str | None,
    service_key: str | None,
    buckets: dict[str, str],
) -> dict[str, Any]:
    """Verify configured private Storage buckets using read-only bucket listing."""
    if not supabase_url and not service_key:
        return {"status": "NOT_CONFIGURED", "checked": False}
    if not supabase_url or not service_key:
        return {"status": "CONFIGURATION_INCOMPLETE", "checked": False}

    parsed = urlsplit(supabase_url.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return {"status": "UNSAFE_PROJECT_URL", "checked": False}

    import httpx

    endpoint = supabase_url.rstrip("/") + "/storage/v1/bucket"
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            response = await client.get(
                endpoint,
                headers={
                    "apikey": service_key,
                    "Authorization": f"Bearer {service_key}",
                },
            )
    except Exception as exc:
        # The exception text may include a URL; preserve only its type.
        return {"status": "UNREACHABLE", "checked": True, "error_type": type(exc).__name__}

    if response.status_code != 200:
        return {
            "status": "HTTP_ERROR",
            "checked": True,
            "http_status": int(response.status_code),
        }
    try:
        rows = response.json()
    except ValueError:
        return {"status": "INVALID_RESPONSE", "checked": True}
    if not isinstance(rows, list):
        return {"status": "INVALID_RESPONSE", "checked": True}

    actual = {
        str(row.get("name")): bool(row.get("public"))
        for row in rows
        if isinstance(row, dict) and row.get("name")
    }
    expected = {str(name): str(bucket) for name, bucket in buckets.items()}
    found = {
        key: {
            "name": bucket,
            "exists": bucket in actual,
            "public": actual.get(bucket) if bucket in actual else None,
        }
        for key, bucket in expected.items()
    }
    missing = [value for value in expected.values() if value not in actual]
    public = [value for value in expected.values() if actual.get(value) is True]
    return {
        "status": "READY" if not missing and not public else "REQUIRES_ATTENTION",
        "checked": True,
        "expected_buckets": found,
        "missing_buckets": missing,
        "public_buckets": public,
    }


async def run_preflight() -> dict[str, Any]:
    from app.config import settings
    from app.models.base import engine

    try:
        async with engine.connect() as connection:
            async with connection.begin():
                report = await collect_preflight(
                    connection,
                    expected_heads=expected_alembic_heads(),
                )
        report["storage"] = await collect_storage_preflight(
            supabase_url=settings.SUPABASE_URL,
            service_key=settings.SUPABASE_SERVICE_KEY,
            buckets={
                "bim": settings.SUPABASE_BUCKET_BIM,
                "documents": settings.SUPABASE_BUCKET_DOCUMENTOS,
                "exports": settings.SUPABASE_BUCKET_EXPORTS,
            },
        )
        return report
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-head",
        action="store_true",
        help="Exit with status 3 unless the database is already at the repository Alembic head.",
    )
    args = parser.parse_args()
    try:
        report = asyncio.run(run_preflight())
    except Exception as exc:  # Do not emit driver exceptions that may include DSN data.
        print(
            json.dumps(
                {
                    "status": "ERROR",
                    "error_type": type(exc).__name__,
                    "message": "Preflight failed. Check the secure deployment logs; connection strings are not printed.",
                },
                indent=2,
            )
        )
        return 2

    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    if args.require_head and not report["alembic"]["at_expected_head"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
