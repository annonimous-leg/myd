from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.engines.costos.parametros import (
    FuenteParametrosCosteo,
    ParametrosCosteoSnapshot,
    verificar_snapshot_almacenado,
)
from app.schemas.costos import ParametrosCosteoInput
from app.schemas.procurement.schemas import ProcurementEconomicModel
from app.engines.costos.motor_costeo import PresupuestoCosteo, PartidaCosteo


def test_snapshot_is_stable_and_deeply_immutable():
    evidence = {"documento": {"paginas": [3, 4]}}
    snapshot = ParametrosCosteoSnapshot(
        Decimal("0.12"), Decimal("0.08"), Decimal("0.16"), Decimal("0.02"),
        FuenteParametrosCosteo.CONTRATO, "Contrato OBRA-2026-17, anexo económico",
        evidencia=evidence,
    )
    first = snapshot.to_dict()
    assert snapshot.to_dict() == first
    assert len(first["sha256"]) == 64
    assert ParametrosCosteoSnapshot.from_dict(first).to_dict() == first
    evidence["documento"]["paginas"].append(5)
    assert snapshot.to_dict() == first
    with pytest.raises(TypeError):
        snapshot.evidencia["documento"] = {}  # type: ignore[index]
    with pytest.raises(AttributeError):
        snapshot.evidencia["documento"]["paginas"].append(5)


def test_snapshot_rejects_invalid_values():
    with pytest.raises(ValueError, match="referencia"):
        ParametrosCosteoSnapshot(
            Decimal("0.15"), Decimal("0.10"), Decimal("0.16"), Decimal("0"),
            FuenteParametrosCosteo.CAPTURA_USUARIO, "   ",
        )
    with pytest.raises(ValueError, match="4 decimales"):
        ParametrosCosteoSnapshot(
            Decimal("0.12345"), Decimal("0"), Decimal("0"), Decimal("0"),
            FuenteParametrosCosteo.CAPTURA_USUARIO, "prueba",
        )


def test_stored_snapshot_rejects_tampering_and_column_drift():
    snapshot = ParametrosCosteoSnapshot(
        Decimal("0.12"), Decimal("0.08"), Decimal("0.16"), Decimal("0.02"),
        FuenteParametrosCosteo.CONTRATO, "Contrato OBRA-2026-17",
    )
    payload = snapshot.to_dict()
    factores = (Decimal("0.12"), Decimal("0.08"), Decimal("0.16"), Decimal("0.02"))
    assert verificar_snapshot_almacenado(payload, factores) == snapshot

    manipulado = {**payload, "referencia": "otra fuente"}
    with pytest.raises(ValueError, match="huella"):
        verificar_snapshot_almacenado(manipulado, factores)
    with pytest.raises(ValueError, match="columnas"):
        verificar_snapshot_almacenado(payload, (*factores[:3], Decimal("0.03")))


def test_http_contract_requires_explicit_parameters_and_reference():
    with pytest.raises(ValidationError):
        ParametrosCosteoInput.model_validate({})
    with pytest.raises(ValidationError):
        ParametrosCosteoInput.model_validate({
            "factor_indirecto": 0.15, "factor_utilidad": 0.10,
            "factor_impuesto": 0.16, "factor_riesgo": 0,
            "fuente": "CAPTURA_USUARIO", "referencia": "   ",
        })


def test_procurement_requires_traceable_parameters_when_it_has_items():
    with pytest.raises(ValidationError, match="factor_impuesto"):
        ProcurementEconomicModel.model_validate({
            "partidas": [{"numero": 1}], "factor_indirecto": 0.10, "factor_utilidad": 0.08,
        })
    model = ProcurementEconomicModel.model_validate({
        "partidas": [{"numero": 1}], "factor_indirecto": 0.10,
        "factor_utilidad": 0.08, "factor_impuesto": 0.16,
        "factor_riesgo": 0, "source": "Convocatoria, anexo AE-05",
    })
    assert model.source == "Convocatoria, anexo AE-05"


def test_cost_engine_composes_financing_utility_and_additional_charges_in_order():
    params = ParametrosCosteoSnapshot(
        factor_indirecto=Decimal("0.10"),
        factor_utilidad=Decimal("0.10"),
        factor_impuesto=Decimal("0.16"),
        factor_riesgo=Decimal("0"),
        fuente=FuenteParametrosCosteo.CONTRATO,
        referencia="Convocatoria sintética con composición económica completa",
        factor_financiamiento=Decimal("0.05"),
        factor_cargos_adicionales=Decimal("0.02"),
    )
    budget = PresupuestoCosteo(
        identificador="TEST-INTEGRAL",
        nombre="Costeo integral",
        parametros=params,
        partidas=[
            PartidaCosteo(
                numero=1,
                descripcion="Partida base",
                unidad="pza",
                cantidad=Decimal("1"),
                precio_unitario_manual=Decimal("100"),
            )
        ],
    )

    assert budget.monto_directo == Decimal("100.00")
    assert budget.monto_indirecto == Decimal("10.00")
    assert budget.monto_financiamiento == Decimal("5.50")
    assert budget.monto_utilidad == Decimal("11.55")
    assert budget.monto_cargos_adicionales == Decimal("2.54")
    assert budget.monto_impuesto == Decimal("20.73")
    assert budget.monto_total == Decimal("150.32")


def test_legacy_snapshot_defaults_new_components_to_zero_without_forging_values():
    legacy = {
        "factor_indirecto": "0.1200",
        "factor_utilidad": "0.0800",
        "factor_impuesto": "0.1600",
        "factor_riesgo": "0.0000",
        "fuente": "CONTRATO",
        "referencia": "Contrato histórico",
        "vigencia": None,
        "jurisdiccion": None,
        "evidencia": {},
    }
    parsed = ParametrosCosteoSnapshot.from_dict(legacy)
    assert parsed.factor_financiamiento == Decimal("0.0000")
    assert parsed.factor_cargos_adicionales == Decimal("0.0000")


def test_risk_contingency_does_not_compound_statutory_additional_charges():
    params = ParametrosCosteoSnapshot(
        factor_indirecto=Decimal("0.10"),
        factor_utilidad=Decimal("0.10"),
        factor_impuesto=Decimal("0.16"),
        factor_riesgo=Decimal("0.10"),
        fuente=FuenteParametrosCosteo.CONTRATO,
        referencia="Separación de contingencia y cargos reglamentarios",
        factor_financiamiento=Decimal("0.05"),
        factor_cargos_adicionales=Decimal("0.02"),
    )
    budget = PresupuestoCosteo(
        identificador="TEST-RISK-BASE",
        nombre="Risk and additional charge bases",
        parametros=params,
        partidas=[PartidaCosteo(
            numero=1,
            descripcion="Base",
            unidad="pza",
            cantidad=Decimal("1"),
            precio_unitario_manual=Decimal("100"),
        )],
    )
    assert budget.monto_financiamiento == Decimal("5.50")
    assert budget.monto_utilidad == Decimal("11.55")
    assert budget.base_cargos_adicionales == Decimal("127.05")
    assert budget.monto_riesgo == Decimal("11.00")
    assert budget.monto_cargos_adicionales == Decimal("2.54")
    assert budget.monto_impuesto == Decimal("22.49")
    assert budget.monto_total == Decimal("163.08")

