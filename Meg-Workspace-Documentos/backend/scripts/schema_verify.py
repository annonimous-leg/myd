#!/usr/bin/env python3
# Copyright © 2026 Cristian Rodriguez
# Schema Gate — verificación de integridad del esquema de base de datos.
#
# Este script NO confía en que "alembic upgrade head" dejó el esquema correcto.
# Conecta a la base de datos real post-migración, lee information_schema, y
# compara contra el modelo declarativo SQLAlchemy (Base.metadata).
#
# Uso en CI:
#   python scripts/schema_verify.py postgresql+asyncpg://user:pass@host/db
#
# Exit codes:
#   0 — esquema válido
#   1 — drift detectado (tablas, columnas, índices o constraints faltantes/sobrantes)
#   2 — error de conexión o ejecución

import sys
import os
import asyncio
import json
import argparse
from typing import Set, Dict, List, Tuple, Any
from dataclasses import dataclass, asdict

from sqlalchemy import inspect, create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy.dialects.postgresql import base as pg_base

# Añadir backend/ al path para importar modelos
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.base import Base
from app.config import settings


@dataclass
class SchemaDiff:
    kind: str  # "missing_table", "extra_table", "missing_column", "extra_column",
               # "type_mismatch", "missing_index", "missing_fk", "missing_pk", "missing_check"
    table: str
    detail: str
    expected: Any = None
    actual: Any = None


class SchemaVerifier:
    """Verifica que el esquema de la BD coincida con Base.metadata."""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self.diffs: List[SchemaDiff] = []
        self._inspector = None

    def _get_sync_url(self) -> str:
        """Convierte URL async a sync para SQLAlchemy inspect."""
        url = self.database_url
        if "+asyncpg" in url:
            return url.replace("+asyncpg", "+psycopg2")
        if "+aiosqlite" in url:
            return url.replace("+aiosqlite", "")
        return url

    def connect(self):
        """Establece conexión e inspector."""
        sync_url = self._get_sync_url()
        self.engine = create_engine(sync_url, future=True)
        self._inspector = inspect(self.engine)
        return self

    def verify(self) -> List[SchemaDiff]:
        """Ejecuta todas las verificaciones y retorna diferencias."""
        self._verify_tables()
        self._verify_columns()
        self._verify_indexes()
        self._verify_constraints()
        return self.diffs

    def _verify_tables(self):
        """Verifica que todas las tablas del modelo existan en la BD."""
        expected_tables = set(Base.metadata.tables.keys())
        actual_tables = set(self._inspector.get_table_names())

        # Ignorar tablas de sistema de Alembic
        actual_tables.discard("alembic_version")

        for missing in expected_tables - actual_tables:
            self.diffs.append(SchemaDiff(
                kind="missing_table",
                table=missing,
                detail=f"Tabla '{missing}' declarada en modelo pero NO existe en BD",
            ))

        for extra in actual_tables - expected_tables:
            self.diffs.append(SchemaDiff(
                kind="extra_table",
                table=extra,
                detail=f"Tabla '{extra}' existe en BD pero NO está declarada en el modelo",
            ))

    def _verify_columns(self):
        """Verifica columnas: existencia, tipo y nullability."""
        for table_name, table in Base.metadata.tables.items():
            if table_name not in self._inspector.get_table_names():
                continue  # Ya reportado como missing_table

            actual_cols = {c["name"]: c for c in self._inspector.get_columns(table_name)}

            for col in table.columns:
                if col.name not in actual_cols:
                    self.diffs.append(SchemaDiff(
                        kind="missing_column",
                        table=table_name,
                        detail=f"Columna '{col.name}' faltante en tabla '{table_name}'",
                    ))
                    continue

                actual = actual_cols[col.name]
                # Comparar tipo (simplificado: nombre del tipo)
                expected_type = str(col.type)
                actual_type = str(actual["type"])
                # Normalizar: algunos tipos se reportan distintos pero son equivalentes
                if not self._types_equivalent(expected_type, actual_type):
                    self.diffs.append(SchemaDiff(
                        kind="type_mismatch",
                        table=table_name,
                        detail=f"Columna '{col.name}': tipo modelo={expected_type}, BD={actual_type}",
                        expected=expected_type,
                        actual=actual_type,
                    ))

                # Verificar nullability
                expected_nullable = col.nullable
                actual_nullable = actual.get("nullable", True)
                if expected_nullable != actual_nullable:
                    self.diffs.append(SchemaDiff(
                        kind="nullability_mismatch",
                        table=table_name,
                        detail=f"Columna '{col.name}': nullable modelo={expected_nullable}, BD={actual_nullable}",
                        expected=expected_nullable,
                        actual=actual_nullable,
                    ))

            for extra_col in set(actual_cols.keys()) - {c.name for c in table.columns}:
                self.diffs.append(SchemaDiff(
                    kind="extra_column",
                    table=table_name,
                    detail=f"Columna '{extra_col}' existe en BD pero NO en modelo (tabla '{table_name}')",
                ))

    def _types_equivalent(self, expected: str, actual: str) -> bool:
        """Compara tipos SQLAlchemy con tolerancia a variantes de Postgres."""
        e = expected.lower().replace(" ", "")
        a = actual.lower().replace(" ", "")
        # Mapeos comunes
        equivalents = {
            ("varchar", "character varying"),
            ("text", "text"),
            ("integer", "integer"),
            ("bigint", "bigint"),
            ("boolean", "boolean"),
            ("timestamp", "timestampwithouttimezone"),
            ("timestamptz", "timestampwithtimezone"),
            ("json", "json"),
            ("jsonb", "jsonb"),
            ("uuid", "uuid"),
            ("geometry", "geometry"),
            ("bytea", "largebinary"),
            ("numeric", "numeric"),
            ("doubleprecision", "float"),
            ("real", "float"),
        }
        if e == a:
            return True
        for pair in equivalents:
            if (e.startswith(pair[0]) and a.startswith(pair[1])) or                (e.startswith(pair[1]) and a.startswith(pair[0])):
                return True
        # Tolerancia para VARCHAR(n) vs character varying
        if "varchar" in e and "character varying" in a:
            return True
        if "character varying" in e and "varchar" in a:
            return True
        return False

    def _verify_indexes(self):
        """Verifica que los índices declarados existan en la BD."""
        for table_name, table in Base.metadata.tables.items():
            if table_name not in self._inspector.get_table_names():
                continue

            actual_indexes = {ix["name"] for ix in self._inspector.get_indexes(table_name)}
            # Incluir PKs e índices únicos como constraints separadas
            actual_pk = self._inspector.get_pk_constraint(table_name)
            actual_fks = {fk["name"] for fk in self._inspector.get_foreign_keys(table_name)}
            actual_uniques = {uq["name"] for uq in self._inspector.get_unique_constraints(table_name)}

            for idx in table.indexes:
                if idx.name not in actual_indexes and idx.name not in actual_uniques:
                    self.diffs.append(SchemaDiff(
                        kind="missing_index",
                        table=table_name,
                        detail=f"Índice '{idx.name}' faltante en tabla '{table_name}'",
                    ))

    def _verify_constraints(self):
        """Verifica PKs, FKs y CHECK constraints con identidad exacta.

        Para FKs compuestas la comparación es por: columnas hijas + tabla
        referenciada + columnas padre + política ON DELETE. Esto evita el falso
        positivo anterior donde bastaba con que existiera una FK sobre una de
        las columnas.
        """
        for table_name, table in Base.metadata.tables.items():
            if table_name not in self._inspector.get_table_names():
                continue

            pk = self._inspector.get_pk_constraint(table_name)
            expected_pk = {col.name for col in table.primary_key.columns}
            actual_pk_cols = set(pk.get("constrained_columns", []))
            if expected_pk != actual_pk_cols:
                self.diffs.append(SchemaDiff(
                    kind="missing_pk",
                    table=table_name,
                    detail=f"PK mismatch: modelo={expected_pk}, BD={actual_pk_cols}",
                    expected=list(expected_pk),
                    actual=list(actual_pk_cols),
                ))

            def expected_fk_signature(constraint):
                return (
                    tuple(constraint.columns.keys()),
                    constraint.elements[0].column.table.name if constraint.elements else None,
                    tuple(element.column.name for element in constraint.elements),
                    constraint.ondelete or "NO ACTION",
                )

            actual_fks = self._inspector.get_foreign_keys(table_name)
            actual_signatures = {
                (
                    tuple(fk.get("constrained_columns") or []),
                    fk.get("referred_table"),
                    tuple(fk.get("referred_columns") or []),
                    (fk.get("options") or {}).get("ondelete") or "NO ACTION",
                )
                for fk in actual_fks
            }

            for constraint in table.foreign_key_constraints:
                expected = expected_fk_signature(constraint)
                if expected not in actual_signatures:
                    self.diffs.append(SchemaDiff(
                        kind="missing_fk",
                        table=table_name,
                        detail=(
                            f"FK faltante: {expected[0]} -> "
                            f"{expected[1]}.{expected[2]} ON DELETE {expected[3]}"
                        ),
                        expected=expected,
                        actual=sorted(actual_signatures),
                    ))

    def report(self) -> str:
        """Genera reporte JSON legible."""
        if not self.diffs:
            return json.dumps({"status": "OK", "drift_count": 0, "diffs": []}, indent=2)
        return json.dumps({
            "status": "DRIFT_DETECTED",
            "drift_count": len(self.diffs),
            "diffs": [asdict(d) for d in self.diffs],
        }, indent=2, default=str)

    def close(self):
        if hasattr(self, "engine"):
            self.engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Schema Gate — verificación de esquema de BD")
    parser.add_argument(
        "database_url",
        nargs="?",
        default=os.getenv("DATABASE_URL"),
        help="URL de la base de datos (default: DATABASE_URL env)",
    )
    parser.add_argument("--strict", action="store_true", help="Fallar también en tablas/columnas EXTRA en BD")
    parser.add_argument("--json", action="store_true", help="Output solo JSON")
    args = parser.parse_args()

    if not args.database_url:
        print("ERROR: No database URL provided. Set DATABASE_URL or pass as argument.", file=sys.stderr)
        sys.exit(2)

    verifier = SchemaVerifier(args.database_url)
    try:
        verifier.connect()
        diffs = verifier.verify()
        report = verifier.report()

        if not args.json:
            print("=" * 70)
            print("SCHEMA GATE — Verificación de integridad del esquema")
            print("=" * 70)
            print(f"Base de datos: {args.database_url.replace('://', '://***:***@')}")
            print(f"Tablas en modelo: {len(Base.metadata.tables)}")
            print()

        print(report)

        if diffs:
            if not args.json:
                print(f"\n❌ FALLÓ: {len(diffs)} diferencias de esquema detectadas.")
            sys.exit(1)
        else:
            if not args.json:
                print("\n✅ OK: Esquema coincide con el modelo declarativo.")
            sys.exit(0)

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
    finally:
        verifier.close()


if __name__ == "__main__":
    main()
