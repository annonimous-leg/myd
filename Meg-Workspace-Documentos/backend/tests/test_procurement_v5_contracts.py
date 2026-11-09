from types import SimpleNamespace

from app.engines.procurement.catalog import _derive_case_packs_from_rules
from app.engines.procurement.contract_policy import ContractPolicyError, validate_contract_model


def schedule():
    return {
        "activities": [
            {"id": f"A{i}", "name": f"Actividad {i}", "duration_days": 10, "budget": 1000}
            for i in range(1, 6)
        ]
    }


def unit_economic():
    return {
        "partidas": [{"numero": 1, "descripcion": "Concepto", "unidad": "m2", "cantidad": 1, "precio_unitario": 100, "conceptos": [{"clave": "C1", "descripcion": "C", "unidad": "m2", "cantidad": 1, "insumos": [{"clave": "M1", "descripcion": "Material", "tipo": "MATERIAL", "unidad": "kg", "cantidad": 1, "precio_unitario": 100, "rendimiento": 1}]}]}],
        "factor_indirecto": 0.12,
        "factor_utilidad": 0.08,
        "indirect_costs": {"items": [{"concept": "Oficina de obra", "amount": 12}]},
        "financing": {"cash_flow": [{"period": "Mes 1", "net": 100}]},
        "profit_detail": {"basis": "CD + CI + F", "rate": 0.08},
    }


def test_conagua_case_pack_has_all_annexes():
    profile = SimpleNamespace(
        code="MX-FED-CONAGUA-OBRA",
        authority="CONAGUA",
        ruleset={"case_packs": ["REFERENCE_CONAGUA_PTAR_2026"]},
    )
    rules = []
    for prefix, last, category in (("AT", 13, "TECNICO"), ("AE", 12, "ECONOMICO")):
        for number in range(1, last + 1):
            code = f"{prefix}-{number:02d}"
            rules.append(
                SimpleNamespace(
                    condition={
                        "conditions": [
                            {
                                "field": "case_pack_code",
                                "op": "eq",
                                "val": "REFERENCE_CONAGUA_PTAR_2026",
                            }
                        ]
                    },
                    requirement={
                        "artifact_required": [code],
                        "category": category,
                        "mandatory": True,
                    },
                    domain="PUBLIC_WORKS",
                )
            )
    packs = _derive_case_packs_from_rules(profile, rules)
    pack = next(item for item in packs if item["code"] == "REFERENCE_CONAGUA_PTAR_2026")
    assert pack is not None
    assert [a["code"] for a in pack["artifacts"]] == [
        *(f"AT-{i:02d}" for i in range(1, 14)),
        *(f"AE-{i:02d}" for i in range(1, 13)),
    ]


def test_unit_prices_require_apu():
    try:
        validate_contract_model("UNIT_PRICES", {"partidas": [{"numero": 1}]}, schedule(), {})
    except ContractPolicyError as exc:
        assert "análisis de precios unitarios" in str(exc)
    else:
        raise AssertionError("El contrato a precios unitarios debe bloquearse sin APU")


def test_lump_sum_requires_total():
    try:
        validate_contract_model("LUMP_SUM", {"partidas": [{"numero": 1}], "factor_indirecto": 0.12}, schedule(), {})
    except ContractPolicyError as exc:
        assert "memoria de integración" in str(exc) or "monto total" in str(exc)
    else:
        raise AssertionError("El precio alzado debe exigir integración económica")


def test_mixed_requires_both_bases():
    try:
        validate_contract_model("MIXED", {"partidas": [{"numero": 1}], "mixed_components": [{"basis": "UNIT_PRICES"}]}, schedule(), {})
    except ContractPolicyError as exc:
        assert "mixto" in str(exc).lower()
    else:
        raise AssertionError("El mixto debe identificar ambos componentes")


def test_unit_price_valid_policy():
    result = validate_contract_model("UNIT_PRICES", unit_economic(), schedule(), {})
    assert result.contract_type == "UNIT_PRICES"
    assert "APU" in result.required_components
    assert "FINANCING" in result.required_components
