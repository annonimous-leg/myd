"""The Supabase preflight is exercised against disposable PostgreSQL in CI."""
from __future__ import annotations

import pytest

from app.models.base import engine
from scripts.supabase_preflight import collect_preflight, expected_alembic_heads


@pytest.mark.asyncio
async def test_catalog_preflight_reports_existing_tables_without_writing():
    async with engine.connect() as connection:
        async with connection.begin():
            report = await collect_preflight(
                connection,
                expected_heads=expected_alembic_heads(),
            )

    assert report["read_only"] is True
    assert "row-level security may filter" in report["count_semantics"]
    assert report["preservation"] == {
        "writes_performed": False,
        "prices_reimported": False,
        "rows_or_objects_exported": False,
    }
    assert report["database"]["server_version"]
    assert report["alembic"]["revision_table_present"] is True
    assert report["alembic"]["at_expected_head"] is True
    tables = report["catalog"]["tables"]
    assert set(tables) == {
        "catalogos_apu",
        "conceptos_catalogo",
        "insumos_catalogo",
        "catalogo_fuentes",
        "catalogo_importaciones",
        "catalogo_registros",
        "precios_unitarios_asignados",
    }
    # Counts remain per table; the preflight never adds projections, raw
    # import records and assigned budget prices into one misleading total.
    for table in ("catalogos_apu", "conceptos_catalogo", "insumos_catalogo"):
        assert isinstance(tables[table]["row_count"], int)
        assert tables[table]["row_count"] >= 0
    assert "row_level_security" in report["security"]
    assert "anon_authenticated_table_grants" in report["security"]
    assert isinstance(report["schemas"], list)
    candidates = report["catalog"]["candidate_tables_across_schemas"]
    assert all({"schema", "table", "select_allowed", "row_count"} <= set(row) for row in candidates)
    assert {row["table"] for row in candidates} >= {
        "catalogos_apu",
        "conceptos_catalogo",
        "insumos_catalogo",
    }
