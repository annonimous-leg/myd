from app.engines.procurement.requirements import ProcurementRequirementMapper


def test_requirement_conditions_are_deterministic():
    matches = ProcurementRequirementMapper._matches
    assert matches({"field": "procedure_type", "op": "eq", "value": "LICITACION_PUBLICA"}, {"procedure_type": "LICITACION_PUBLICA"})
    assert matches({"all_of": [
        {"field": "jurisdiction_code", "op": "eq", "value": "FEDERAL"},
        {"field": "procedure_type", "op": "in", "value": ["LICITACION_PUBLICA", "INVITACION"]},
    ]}, {"jurisdiction_code": "FEDERAL", "procedure_type": "LICITACION_PUBLICA"})
    assert not matches({"field": "procedure_type", "op": "eq", "value": "INVITACION"}, {"procedure_type": "LICITACION_PUBLICA"})
