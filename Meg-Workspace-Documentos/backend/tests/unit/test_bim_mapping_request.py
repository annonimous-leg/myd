"""Input limits for user-provided BIM element-to-APU mapping."""
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.v1.bim import GenerarPresupuestoRequest


def test_element_mapping_rejects_more_than_twenty_thousand_entries():
    params = {
        "factor_indirecto": "0",
        "factor_utilidad": "0",
        "factor_impuesto": "0",
        "factor_riesgo": "0",
        "fuente": "CAPTURA_USUARIO",
        "referencia": "Prueba de límite de mapeo BIM",
    }
    mapping = {uuid4(): uuid4() for _ in range(20_001)}

    with pytest.raises(ValidationError, match="20000"):
        GenerarPresupuestoRequest(
            parametros_costeo=params,
            mapeo_elementos=mapping,
        )


def test_element_mapping_accepts_empty_mapping_by_default():
    params = {
        "factor_indirecto": "0",
        "factor_utilidad": "0",
        "factor_impuesto": "0",
        "factor_riesgo": "0",
        "fuente": "CAPTURA_USUARIO",
        "referencia": "Prueba de límite de mapeo BIM",
    }
    request = GenerarPresupuestoRequest(parametros_costeo=params)

    assert request.mapeo_elementos == {}
