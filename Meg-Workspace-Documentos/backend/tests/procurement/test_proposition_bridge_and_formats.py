"""Tests for the DB-driven format boundary and real budget bridge."""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.errors import MegalodonException
from app.engines.costos.parametros import FuenteParametrosCosteo, ParametrosCosteoSnapshot
from app.engines.procurement.compiler import ProcurementArtifactCompiler
from app.engines.procurement.format_field_map import normalize_format_code
from app.engines.procurement.proposition_bridge import build_economic_block


def test_format_normalization_has_no_dependency_mapping():
    assert normalize_format_code("formato 12") == "FORMATO_12"
    assert normalize_format_code("FORMA E-7") == "FORMA_E-7"
    assert normalize_format_code("ECO.03") == "ECO.3"
    # Unknown codes remain unknown instead of silently selecting another dependency.
    assert normalize_format_code("CFE-AT-999") == "CFE-AT-999"


def test_compiler_allowlist_rejects_unknown_db_algorithm():
    compiler = ProcurementArtifactCompiler()
    try:
        compiler.compile_from_binding({"format_code": "X", "compiler": "compile_cfe_magic"}, {})
    except ValueError as exc:
        assert "no permitido" in str(exc)
    else:
        raise AssertionError("Un compiler desconocido no debe ejecutarse desde DB")


def test_compiler_binding_executes_real_algorithm():
    compiler = ProcurementArtifactCompiler()
    content = compiler.compile_from_binding(
        {"format_code": "ECO.1", "compiler": "compile_proposal_letter_xlsx", "title": "Carta"},
        {"facts": {"authority": "CONAGUA", "object": "PTAR", "procedure_type": "LICITACION_PUBLICA"},
         "economic": {"budget_total": 1000}},
    )
    assert content[:2] == b"PK"


def test_build_economic_block_from_presupuesto_tree():
    insumo = SimpleNamespace(clave="M1", descripcion="Cemento", tipo="MATERIAL", unidad="kg", cantidad=Decimal("10"), precio_unitario=Decimal("5"), rendimiento=1)
    concepto = SimpleNamespace(clave="C1", descripcion="Concreto", unidad="m3", cantidad=Decimal("1"), insumos=[insumo])
    partida = SimpleNamespace(numero=1, descripcion="Losa", unidad="m2", cantidad=Decimal("100"), precio_unitario=Decimal("50"), importe=Decimal("5000"), conceptos=[concepto])
    parametros = ParametrosCosteoSnapshot(
        Decimal("0.15"), Decimal("0.10"), Decimal("0.16"), Decimal("0"),
        FuenteParametrosCosteo.CONVOCATORIA, "AE-05, página 12",
    )
    pres = SimpleNamespace(id="00000000-0000-0000-0000-000000000001", identificador="PRE-TEST-001", nombre="Obra test", partidas=[partida], monto_total=Decimal("5800"), monto_directo=Decimal("5000"), monto_indirecto=Decimal("750"), monto_utilidad=Decimal("50"), monto_riesgo=Decimal("0"), monto_impuesto=Decimal("0"), factor_indirecto=Decimal("0.15"), factor_utilidad=Decimal("0.10"), factor_impuesto=Decimal("0.16"), factor_riesgo=Decimal("0"), metadatos={"parametros_costeo": parametros.to_dict()}, plazo_dias=180, moneda="MXN")
    eco = build_economic_block(pres)
    assert eco["budget_total"] == 5800.0
    assert len(eco["partidas"]) == 1
    assert eco["partidas"][0]["importe"] == 5000.0
    assert eco["partidas"][0]["conceptos"][0]["insumos"][0]["importe"] == 50.0
    assert eco["indirects"]["amount"] == 750.0
    assert eco["factor_riesgo"] == 0.0
    assert eco["source"] == "CONVOCATORIA:AE-05, página 12"


def test_build_economic_block_rejects_untraceable_historical_budget():
    pres = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001", identificador="PRE-HISTORICO",
        nombre="Histórico", partidas=[SimpleNamespace(numero=1, conceptos=[])],
        factor_indirecto=Decimal("0.15"), factor_utilidad=Decimal("0.10"),
        factor_impuesto=Decimal("0.16"), factor_riesgo=None, metadatos={},
    )
    with pytest.raises(MegalodonException, match="Regularícelo"):
        build_economic_block(pres)


def test_format_catalog_is_loaded_from_selected_profile_db():
    import asyncio

    from app.engines.procurement.format_field_map import load_format_catalog

    class _Result:
        def scalars(self):
            return self
        def all(self):
            return []

    class _DB:
        async def scalar(self, _query):
            return SimpleNamespace(
                code="MX-FED-CONAGUA-OBRA", active=True, tenant_id=None,
                ruleset={}, templates={"format_definitions": [{
                    "format_code": "CONAGUA-X1", "title": "Formato X1",
                    "compiler": "compile_proposal_letter_xlsx",
                    "canonical_paths": ["facts.authority"],
                }]},
            )
        async def execute(self, _query):
            return _Result()

    catalog = asyncio.run(load_format_catalog(_DB(), tenant_id="tenant", jurisdiction_code="MX-FED-CONAGUA-OBRA"))
    assert catalog["CONAGUA-X1"]["canonical_paths"] == ["facts.authority"]
    assert "CFE" not in catalog
