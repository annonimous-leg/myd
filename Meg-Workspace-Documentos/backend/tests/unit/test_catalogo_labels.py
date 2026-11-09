from datetime import date, datetime, timezone
from uuid import uuid4

import pytest

from app.core.catalogo_labels import market_research_label
from app.schemas.catalogo_apu import CatalogoAPUOut


@pytest.mark.parametrize('value,expected', [
    ('2026-01-01', 'enero 2026'), ('2026-02-28', 'febrero 2026'),
    (date(2025, 12, 31), 'diciembre 2025'),
    ('2026-02-30', 'fecha por verificar'), (None, 'fecha por verificar'),
    ('2026', 'fecha por verificar'), ('', 'fecha por verificar'),
])
def test_source_month_is_explicit_and_never_inferred_from_current_date(value, expected):
    assert market_research_label(value) == f'Investigación de mercado Megalodon · {expected}'


def test_display_name_preserves_original_identity_and_provenance():
    source = {'titulo': 'Synthetic publisher', 'sha256': 'a' * 64, 'fecha_vigencia': '2026-02-01'}
    item = CatalogoAPUOut(id=uuid4(), clave='TEST', descripcion='Synthetic', tipo='CONCEPTO',
        unidad='m2', precio_unitario=10, fuente='SOURCE-A@edition', zona_economica=None,
        estado=None, incluye_iva=False, vigencia_inicio='2026-01-01', vigencia_fin=None,
        origen={'fuente': source}, created_at=datetime.now(timezone.utc))
    output = item.model_dump()
    assert output['fuente_visible'] == 'Investigación de mercado Megalodon · febrero 2026'
    assert output['fuente'] == 'SOURCE-A@edition'
    assert output['origen']['fuente'] == source
