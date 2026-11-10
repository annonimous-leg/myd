"""Commercial labels never replace the source edition used for costing."""
from io import BytesIO
from zipfile import ZipFile

import pytest

from app.config import settings
from app.services.catalogo_importacion import import_package
from tests.conftest import _login
from tests.fixtures.catalog_import import make_synthetic_package


@pytest.mark.asyncio
async def test_import_preview_and_price_keep_provenance_with_monthly_label(
    async_client, db_session, tenant_a_user, tenant_b_user, tmp_path, monkeypatch,
):
    package, originals, records = make_synthetic_package(tmp_path)
    monkeypatch.setattr(settings, 'CATALOGO_ORIGINALES_DIR', str(originals))
    headers = await _login(async_client, tenant_a_user[1].email)
    buffer = BytesIO()
    with ZipFile(buffer, 'w') as archive:
        for path in package.rglob('*'):
            if path.is_file():
                archive.write(path, str(path.relative_to(package)))
    preview = await async_client.post('/api/v1/catalogo-apu/importaciones/verificar', headers=headers,
        files={'archivo': ('synthetic.zip', buffer.getvalue(), 'application/zip')})
    assert preview.status_code == 200, preview.text
    label = 'Investigación de mercado Megalodon · enero 2026'
    source = preview.json()['fuentes'][0]
    assert source['nombre_visible'] == label
    assert source['titulo'] == records['fuente'][0]['titulo']
    batch, _ = await import_package(db_session, tenant_a_user[1], package, originals, {'SYNTHETIC'})
    batches = await async_client.get('/api/v1/catalogo-apu/importaciones', headers=headers)
    assert batches.status_code == 200, batches.text
    edition = next(b for b in batches.json()['items'] if b['id'] == str(batch.id))
    assert edition['fuentes'] == ['SYNTHETIC']
    assert edition['fuentes_visibles'] == [label]
    prices = await async_client.get('/api/v1/catalogo-apu?q=TEST-EXC', headers=headers)
    assert prices.status_code == 200, prices.text
    price = prices.json()['items'][0]
    assert price['fuente_visible'] == label
    assert price['fuente'].startswith('SYNTHETIC@')
    assert price['origen']['fuente'] == records['fuente'][0]
    assert price['precio_unitario'] == 152.43
    outsider = await _login(async_client, tenant_b_user[1].email)
    assert (await async_client.get('/api/v1/catalogo-apu?q=TEST-EXC', headers=outsider)).json()['items'] == []
