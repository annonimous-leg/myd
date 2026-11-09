from decimal import Decimal, localcontext
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.engines.costos.indices import actualizar_precio
from app.schemas.indices_costos import ObservacionIndiceCreate


def test_precio_desde_niveles_con_baja_y_contexto_local():
    with localcontext() as context:
        context.prec = 6
        assert actualizar_precio(Decimal('560.46'), Decimal('117.12345678'), Decimal('112.76543210')) == Decimal('539.61')
        assert context.prec == 6


@pytest.mark.parametrize('valor', ['0', '-1', 'NaN', 'Infinity'])
def test_no_admite_niveles_invalidos(valor):
    with pytest.raises(ValueError):
        actualizar_precio(Decimal('10'), Decimal(valor), Decimal('100'))


@pytest.mark.parametrize('cambio', [{'medida': 'ANUAL'}, {'mes': '2099-01-01'},
                                {'mes': '2020-01-12'}, {'publicado_el': '2099-02-01'},
                                {'publicado_el': '2020-01-20'}, {'valor': 'Infinity'}])
def test_no_acepta_observaciones_incompatibles(cambio):
    datos = {'serie_id': str(uuid4()), 'medida': 'NIVEL', 'mes': '2020-01-01', 'valor': '100',
             'publicado_el': '2020-02-10', 'evidencia': {'url': 'https://example.invalid/doc.pdf',
             'sha256': 'a' * 64, 'localizador': 'Tabla controlada 1'}}
    with pytest.raises(ValidationError):
        ObservacionIndiceCreate.model_validate({**datos, **cambio})
