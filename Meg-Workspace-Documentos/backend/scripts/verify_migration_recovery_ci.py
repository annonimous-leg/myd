"""Exercise populated historical upgrades and real PostgreSQL backup/restore.

Synthetic fixtures are confined to a dedicated disposable CI service. This is
not a production migration command, and a passing report does not certify a
customer database, its credentials, role grants, or external artifact storage.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import geoalchemy2  # noqa: F401 -- register PostGIS reflection types
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from scripts.migration_head import application_head

HISTORICAL = "20260914_workspace_bridge_tenant"
HEAD = application_head()
OWNED = ("presupuestos", "partidas", "conceptos", "insumos",
         "programas_obra", "actividades_programa")
TABLES = ("tenants", "users", "expedientes_obra", *OWNED,
          "catalog_terms", "webhook_eventos_procesados", "tezcatlipoca_users", "snapshots",
          "levantamientos", "puntos_topograficos", "proveedores")
INSTANT = datetime(2026, 9, 14, 12, 34, 56, 123456, tzinfo=UTC)
NAIVE = INSTANT.replace(tzinfo=None)
D = Decimal


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def normalize(value):
    if isinstance(value, datetime):
        # Historical Tez timestamps explicitly represented UTC without tzinfo.
        return value.replace(tzinfo=UTC).isoformat() if value.tzinfo is None else value.astimezone(UTC).isoformat()
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize(v) for v in value]
    return value


def snapshot(engine):
    with engine.connect() as conn:
        result = {}
        for name in TABLES:
            table = sa.Table(name, sa.MetaData(), autoload_with=conn)
            columns = [sa.func.ST_AsEWKT(c).label(c.name) if c.name == "geom" else c for c in table.columns]
            result[name] = [normalize(dict(row)) for row in conn.execute(
                sa.select(*columns).order_by(*table.primary_key.columns)).mappings()]
        result["revision"] = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
        return result


def schema_signature(engine):
    with engine.connect() as conn:
        inspector = sa.inspect(conn)
        return {
            name: {
                "columns": [(c["name"], str(c["type"]), c["nullable"], str(c["default"]))
                            for c in inspector.get_columns(name)],
                "foreign_keys": inspector.get_foreign_keys(name),
                "unique": inspector.get_unique_constraints(name),
                "indexes": inspector.get_indexes(name),
                "checks": inspector.get_check_constraints(name),
            }
            for name in sorted(inspector.get_table_names())
        }


def migrate(target, expected_failure=None, downgrade=False):
    command = [sys.executable, "-m", "alembic", "downgrade" if downgrade else "upgrade", target]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if expected_failure:
        if result.returncode == 0 or expected_failure not in result.stderr:
            # Bounded diagnostics from this disposable CI database only.
            # Do not hide an earlier guard behind the precision assertion.
            diagnostic = (result.stdout + "\n" + result.stderr)[-12000:]
            database_url = os.environ.get("DATABASE_URL", "")
            if database_url:
                diagnostic = diagnostic.replace(database_url, "[DATABASE_URL]")
                password = sa.engine.make_url(database_url).password
                if password:
                    diagnostic = diagnostic.replace(password, "[REDACTED]")
            raise RuntimeError(
                f"Migration {command[-2:]} returned {result.returncode}; "
                f"expected rejection containing {expected_failure!r}.\n{diagnostic}"
            )
    elif result.returncode:
        # CI fixtures only; never run against customer credentials/data.
        sys.stderr.write(result.stderr)
        raise RuntimeError("Migration failed")


def seed(engine):
    graph = []
    with engine.begin() as conn:
        def insert(table_name, **values):
            table = sa.Table(table_name, sa.MetaData(), autoload_with=conn)
            return conn.execute(table.insert().values(**values).returning(table.c.id)).scalar_one()

        for number in (1, 2):
            tenant, user, expediente, presupuesto, partida, concepto, insumo, programa, actividad = [uuid4() for _ in range(9)]
            insert("tenants", id=tenant, name=f"CI historical tenant {number}", slug=f"ci-history-{number}",
                   is_active=True, plan="free")
            insert("users", id=user, tenant_id=tenant, email=f"history-{number}@fixture.invalid",
                   hashed_password="disabled-ci-fixture-no-login", full_name="CI historical author",
                   role="admin", is_active=True, is_verified=True)
            insert("expedientes_obra", id=expediente, tenant_id=tenant, identificador="SHARED-ID",
                   titulo="Historical fixture", organo="CI", unidad_administrativa="CI",
                   serie_documental="CI", subserie_documental="CI", tipo_contrato="PRECIOS_UNITARIOS",
                   estado="INICIADO", clasificacion="PUBLICO", creado_por_id=user)
            insert("presupuestos", id=presupuesto, expediente_id=expediente, identificador="SHARED-BUDGET",
                   nombre="Historical explicit cost", monto_directo=D("1234.56"), monto_indirecto=D("123.46"),
                   monto_utilidad=D("135.80"), monto_impuesto=D("239.01"), monto_total=D("1732.83"),
                   moneda="MXN", factor_indirecto=D("0.1000"), factor_utilidad=D("0.1000"),
                   factor_impuesto=D("0.1600"), zona_economica="CENTRO", estado="BORRADOR",
                   metadatos={"provenance": "synthetic historical fixture", "unicode": "México"},
                   creado_por_id=user, actualizado_por_id=user, created_at=INSTANT, updated_at=INSTANT)
            insert("partidas", id=partida, presupuesto_id=presupuesto, numero=1, descripcion="CI line",
                   unidad="m3", cantidad=D("2.0000"), precio_unitario=D("617.28"), importe=D("1234.56"))
            insert("conceptos", id=concepto, partida_id=partida, clave="CI-CONCEPT", descripcion="CI concept",
                   unidad="m3", cantidad=D("2.0000"), costo_directo_unitario=D("617.28"))
            insert("insumos", id=insumo, concepto_id=concepto, clave="CI-RESOURCE", descripcion="CI resource",
                   tipo="MATERIAL", unidad="m3",
                   # The second tenant exercises the full historical integer
                   # range, independently of the costing workflow fixture.
                   cantidad=D("2.0000") if number == 1 else D("99999999999999.9999"), precio_unitario=D("617.28"),
                   importe=D("1234.56"), rendimiento=D("1.0000"))
            insert("programas_obra", id=programa, expediente_id=expediente, identificador="SHARED-SCHEDULE",
                   nombre="CI schedule", fecha_inicio_plan=INSTANT, duracion_plan_dias=2, estado="BORRADOR")
            insert("actividades_programa", id=actividad, programa_id=programa, identificador="CI-A",
                   nombre="CI activity", wbs_codigo="1", wbs_nivel=1, duracion=D("2.00"), tipo="TAREA",
                   costo_presupuestado=D("1234.56"), costo_real=D("0.00"), porcentaje_avance=D("0.00"),
                   holgura_total=D("0.00"), holgura_libre=D("0.00"), en_ruta_critica=True)
            term = insert("catalog_terms", id=uuid4(), tenant_id=tenant, domain="ci", code="SHARED-TERM",
                          label="Historical term", created_by_id=user, updated_by_id=user)
            tez = insert("tezcatlipoca_users", username=f"ci-history-{number}",
                         password_hash="disabled-ci-fixture-no-login", tenant_id=str(tenant),
                         megalodon_user_id=str(user), created_at=NAIVE, last_login=NAIVE)
            insert("snapshots", name="CI historical snapshot", user_id=tez, tenant_id=str(tenant),
                   layers={"fixture": True}, viewport={"longitude": -99.1}, created_at=NAIVE)
            survey = insert("levantamientos", id=uuid4(), expediente_id=expediente,
                            identificador="CI-SURVEY", nombre="CI topography", tipo="TOPOGRAFICO",
                            estado="BORRADOR", crs="EPSG:6362", srid=6362, creado_por_id=user)
            insert("puntos_topograficos", id=uuid4(), levantamiento_id=survey, identificador="CI-POINT",
                   x=D("500000.123456"), y=D("2100000.654321"), z=D("2234.567890"), precision_xy=D("0.0010"),
                   geom=sa.func.ST_GeomFromEWKT("SRID=6362;POINT Z(500000.123456 2100000.654321 2234.56789)"))
            graph.append({"tenant": tenant, "user": user, "term": term,
                          **dict(zip(OWNED, (presupuesto, partida, concepto, insumo, programa, actividad), strict=True))})
        insert("webhook_eventos_procesados", id=uuid4(), proveedor="stripe",
               evento_id="ci-historical-event", procesado_en=INSTANT)
    return graph


def verify_upgrade(before, after, graph):
    expected = json.loads(json.dumps(before))
    expected["revision"] = HEAD
    for name in OWNED:
        by_id = {str(g[name]): str(g["tenant"]) for g in graph}
        for row in expected[name]:
            row["tenant_id"] = by_id[row["id"]]
            if name == "presupuestos":
                row.update(
                    factor_riesgo=None,
                    monto_riesgo=None,
                    factor_financiamiento="0.0000",
                    factor_cargos_adicionales="0.0000",
                    monto_financiamiento="0.00",
                    monto_cargos_adicionales="0.00",
                )
            if name == "partidas":
                row["metadatos"] = {}
            if name == "insumos":
                # Historical costs have no fabricated index provenance.
                row["actualizacion_precio"] = None
                # Widening preserves the value, appending exactly two zero
                # decimals; compare PostgreSQL's exact text representation.
                row['cantidad'] = format(Decimal(row['cantidad']), '.6f')
    for row in expected["users"]:
        row["auth_version"] = 0
    for row in expected["catalog_terms"]:
        row["creado_por_id"] = row.pop("created_by_id")
        row["actualizado_por_id"] = row.pop("updated_by_id")
    for row in expected["webhook_eventos_procesados"]:
        row["created_at"] = row["updated_at"] = row["procesado_en"]
    require(expected == after, "Upgrade changed historical values beyond the documented transformations")


def verify_constraints(engine, graph):
    # Execute cross-tenant writes and require PostgreSQL itself to reject them.
    with engine.connect() as conn:
        for name in OWNED:
            transaction = conn.begin_nested()
            try:
                conn.execute(sa.text(f"UPDATE {name} SET tenant_id=:tenant WHERE id=:id"),
                             {"tenant": graph[1]["tenant"], "id": graph[0][name]})
            except IntegrityError as exc:
                require(exc.orig.pgcode == "23503", f"Unexpected constraint failure in {name}")
            else:
                raise RuntimeError(f"Cross-tenant ownership was accepted in {name}")
            finally:
                transaction.rollback()


def main():
    if os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("ENVIRONMENT") != "staging":
        raise SystemExit("This command seeds fixtures only in dedicated disposable CI staging")
    container = os.environ["MIGRATION_CI_CONTAINER"]
    url = sa.engine.make_url(os.environ["DATABASE_URL"])
    require(url.host in ("localhost", "127.0.0.1") and url.database == "migration_history_ci",
            "Dedicated local CI database required")
    engine = sa.create_engine(url.set(drivername="postgresql+psycopg2"))
    checks = []
    try:
        with engine.begin() as conn:
            require(not sa.inspect(conn).has_table("alembic_version"), "CI database must be fresh")
            conn.execute(sa.text("ALTER DATABASE migration_history_ci SET timezone TO 'America/Mexico_City'"))
        engine.dispose()
        migrate(HISTORICAL)
        graph = seed(engine)
        # An unresolved historical author must abort the entire upgrade, not
        # invent a user, drop attribution, or leave half-applied migrations.
        with engine.begin() as conn:
            conn.execute(sa.text("UPDATE catalog_terms SET created_by_id=:bad WHERE id=:id"),
                         {"bad": uuid4(), "id": graph[0]["term"]})
        invalid = snapshot(engine)
        invalid_schema = schema_signature(engine)
        migrate("head", expected_failure="fk_catalog_terms_creado_por_id")
        require(snapshot(engine) == invalid and schema_signature(engine) == invalid_schema,
                "Failed historical upgrade did not roll back schema and data atomically")
        checks.append("Unresolved historical authors reject upgrade with complete transaction rollback")
        with engine.begin() as conn:
            conn.execute(sa.text("UPDATE catalog_terms SET created_by_id=:author WHERE id=:id"),
                         {"author": graph[0]["user"], "id": graph[0]["term"]})
        historical = snapshot(engine)
        # Exercise the operator command with an actual custom-format dump of
        # the populated historical schema. It must inspect every public table,
        # not merely the selected fixture graph compared below.
        with tempfile.TemporaryDirectory(prefix="meg-historical-rehearsal-") as directory:
            backup_env = dict(os.environ, BACKUP_DIR=directory)
            result = subprocess.run(["bash", "scripts/backup_postgres.sh"], env=backup_env,
                                    capture_output=True, text=True, timeout=120, check=True)
            historical_backup = Path(result.stdout.strip())
            subprocess.run(["docker", "exec", container, "createdb", "-U", url.username,
                            "-T", "template0", "megalodon_rehearsal_ci"], check=True, timeout=30)
            rehearsal_env = dict(os.environ, DATABASE_URL=url.set(database="megalodon_rehearsal_ci").render_as_string(hide_password=False))
            report_path = Path(directory) / "historical-report.json"
            subprocess.run([sys.executable, "-m", "scripts.rehearse_historical_backup",
                            "--backup", str(historical_backup), "--report", str(report_path)],
                           env=rehearsal_env, check=True, timeout=180)
            rehearsal_report = json.loads(report_path.read_text())
            require(rehearsal_report["historical_values_preserved"] and
                    rehearsal_report["tables_verified"] > len(TABLES),
                    "Operator rehearsal did not compare all public historical tables")
            require(report_path.stat().st_mode & 0o077 == 0, "Rehearsal report is not private")
            require(snapshot(engine) == historical, "Rehearsal modified the source database")
        checks.append("Operator rehearsal restores an historical dump, upgrades its isolated copy and fingerprints all public tables")
        # Exercise the precision guard before the later forward-only audit
        # migration. A downgrade from HEAD cannot reach the catalogue guard.
        migrate("20261013_costeo_integral")
        with engine.begin() as conn:
            conn.execute(sa.text('UPDATE insumos SET cantidad=0.227273 WHERE id=:id'), {'id': graph[0]['insumos']})
        precision_snapshot, precision_schema = snapshot(engine), schema_signature(engine)
        migrate('20261008_topografia_evidencia', expected_failure='seis decimales', downgrade=True)
        require(snapshot(engine) == precision_snapshot and schema_signature(engine) == precision_schema,
                'Rejected catalogue downgrade changed consumption or schema')
        with engine.begin() as conn:
            conn.execute(sa.text('UPDATE insumos SET cantidad=2.000000 WHERE id=:id'), {'id': graph[0]['insumos']})
        checks.append('Six-decimal consumption rejects a lossy downgrade without changing data or schema')
        # Test the supplier downgrade guard before the later audit migration adds a newer
        # forward-only barrier; otherwise that newer barrier masks the supplier guard.
        migrate("20261014_proveedor_tenant")
        # An RFC identifies a supplier independently inside each organization.
        provider_ids = [uuid4(), uuid4()]
        with engine.begin() as conn:
            providers = sa.Table("proveedores", sa.MetaData(), autoload_with=conn)
            for row, provider_id in zip(graph, provider_ids, strict=True):
                conn.execute(providers.insert().values(id=provider_id, tenant_id=row["tenant"],
                    tipo_persona="MORAL", rfc="COS260101A12", razon_social="CI tenant-scoped supplier",
                    estado="ACTIVO", creado_por_id=row["user"], actualizado_por_id=row["user"]))
        provider_snapshot, provider_schema = snapshot(engine), schema_signature(engine)
        migrate("20261014_documental_review", expected_failure="restaurar RFC global", downgrade=True)
        require(snapshot(engine) == provider_snapshot and schema_signature(engine) == provider_schema,
                "Rejected RFC downgrade changed tenant supplier data or unique indexes")
        with engine.begin() as conn:
            conn.execute(providers.delete().where(providers.c.id.in_(provider_ids)))
        migrate("20261014_documental_review", downgrade=True)
        checks.append("Tenant RFC uniqueness supports shared suppliers and rejects a lossy downgrade transactionally")
        migrate("head")
        verify_upgrade(historical, snapshot(engine), graph)
        with engine.connect() as conn:
            for table, fields in (("tezcatlipoca_users", ("created_at", "last_login")),
                                  ("snapshots", ("created_at",))):
                columns = {c["name"]: c for c in sa.inspect(conn).get_columns(table)}
                require(all(columns[field]["type"].timezone for field in fields),
                        "Historical Tez UTC timestamps were not migrated to timezone-aware types")
        checks.append("Populated historical upgrade preserves decimal costs, UTC instants, authors and ownership")
        verify_constraints(engine, graph)
        checks.append("PostgreSQL rejects cross-tenant writes across all six budget/schedule tables")
        with engine.begin() as conn:
            conn.execute(sa.text("UPDATE users SET auth_version=7"))
        current, schema = snapshot(engine), schema_signature(engine)
        migrate("20260930_tez_timestamps", expected_failure="integridad y retención de auditoría", downgrade=True)
        require(snapshot(engine) == current and schema_signature(engine) == schema,
                "Rejected identity downgrade changed authority or migration state")
        checks.append("Current audit-chain barrier blocks rollback across older identity revisions without resetting session versions")
        from scripts.verify_migrated_schema import verify
        with engine.connect() as conn:
            verify(conn)
        with tempfile.TemporaryDirectory(prefix="meg-recovery-") as directory:
            backup_env = dict(os.environ, BACKUP_DIR=directory)
            result = subprocess.run(["bash", "scripts/backup_postgres.sh"], env=backup_env,
                                    capture_output=True, text=True, timeout=120, check=True)
            backup = Path(result.stdout.strip())
            require(backup.stat().st_mode & 0o077 == 0, "Backup is not private")
            subprocess.run(["docker", "exec", container, "createdb", "-U", url.username,
                            "-T", "template0", "migration_restore_ci"], check=True, timeout=30)
            restore_env = dict(os.environ, BACKUP_FILE=str(backup), DATABASE_URL=
                               url.set(database="migration_restore_ci").render_as_string(hide_password=False))
            def restore(expected_failure=None):
                result = subprocess.run(["bash", "scripts/restore_postgres.sh"], env=restore_env,
                                        capture_output=True, text=True, timeout=120)
                if expected_failure:
                    require(result.returncode != 0 and expected_failure in result.stderr,
                            "Operational restore did not reject the expected unsafe input")
                elif result.returncode:
                    sys.stderr.write(result.stderr)
                    raise RuntimeError("Operational restore failed")
            checksum = Path(str(backup) + ".sha256")
            original_checksum = checksum.read_text()
            checksum.unlink()
            restore(expected_failure="checksum file required")
            checksum.write_text("0" * 64 + "  " + backup.name + "\n")
            restore(expected_failure="checksum mismatch")
            checksum.write_text(original_checksum)
            # A routine/domain alone used to pass the relations-only empty
            # database check. Neither may survive a supposedly clean recovery.
            empty_target = sa.create_engine(engine.url.set(database="migration_restore_ci"))
            try:
                for create, drop in (
                    ("CREATE FUNCTION public.recovery_foreign_function() RETURNS int LANGUAGE sql AS 'SELECT 1'",
                     "DROP FUNCTION public.recovery_foreign_function()"),
                    ("CREATE DOMAIN public.recovery_foreign_domain AS text",
                     "DROP DOMAIN public.recovery_foreign_domain"),
                    ("CREATE SCHEMA recovery_foreign_schema", "DROP SCHEMA recovery_foreign_schema"),
                ):
                    with empty_target.begin() as conn:
                        conn.execute(sa.text(create))
                    restore(expected_failure="empty isolated database")
                    with empty_target.begin() as conn:
                        conn.execute(sa.text(drop))
            finally:
                empty_target.dispose()
            restore()
            restored = sa.create_engine(engine.url.set(database="migration_restore_ci"))
            try:
                require(snapshot(restored) == current and schema_signature(restored) == schema,
                        "Backup restore changed data, schema, constraints or revocation epochs")
                restore(expected_failure="empty isolated database")
                require(snapshot(restored) == current and schema_signature(restored) == schema,
                        "Rejected overwrite changed the recovered installation")
                verify_constraints(restored, graph)
                with restored.connect() as conn:
                    verify(conn)
                    require(conn.execute(sa.text("SELECT PostGIS_Version()")).scalar_one(), "PostGIS unavailable")
                    # Restored serial sequences must advance beyond existing IDs.
                    for table in ("tezcatlipoca_users", "snapshots"):
                        maximum = conn.execute(sa.text(f"SELECT max(id) FROM {table}")).scalar_one()
                        next_id = conn.execute(sa.text(
                            "SELECT nextval(pg_get_serial_sequence(:table, 'id'))"), {"table": table}).scalar_one()
                        require(next_id > maximum, f"Restored sequence collides in {table}")
            finally:
                restored.dispose()
        checks.append("Operational backup/restore preserves data, schema, 3D PostGIS geometry, sequences and revocation epochs")
        checks.append("Operational restore rejects missing/bad checksums and nonempty targets without overwriting data")
        report = {"passed": checks, "source_revision": HISTORICAL, "target_revision": HEAD,
                  "operator_rehearsal": {key: rehearsal_report[key] for key in (
                      "source_revision", "target_revision", "tables_verified", "rows_verified",
                      "historical_values_preserved", "documented_configuration_transforms_verified",
                      "timings_seconds", "production_deployment_certified")},
                  "fixtures": "synthetic populated historical data in two tenants",
                  "owned_rows": sum(len(current[t]) for t in OWNED),
                  "data_sha256": hashlib.sha256(json.dumps(current, sort_keys=True).encode()).hexdigest(),
                  "production_deployment_certified": False,
                  "excluded": ["customer database snapshot", "role/ACL provisioning", "external storage recovery", "RPO/RTO"]}
        Path("migration-recovery-report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
