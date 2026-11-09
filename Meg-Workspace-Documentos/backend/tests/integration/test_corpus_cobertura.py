import pytest

from tests.conftest import _login


@pytest.mark.asyncio
async def test_cobertura_corpus_autenticada_y_conteos_consultables(async_client, tenant_a_user):
    assert (await async_client.get('/api/v1/legal/cobertura')).status_code == 401
    auth = await _login(async_client, tenant_a_user[1].email)
    response = await async_client.get('/api/v1/legal/cobertura', headers=auth)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['total_articulos_consultables'] == 969
    assert result['documentos_sin_articulos'] == ['Manual Comité Adquisiciones']
    assert result['vigencia_certificada'] is False
    lgra = next(d for d in result['documentos'] if d['nombre'] == 'LGRA')
    assert lgra['numeros_no_segmentados'] == [12, 55, 82, 141, 214, 223]
    article = await async_client.get('/api/v1/legal/articulo/lopsrm/40', headers=auth)
    assert article.status_code == 200, article.text
    assert article.json()['contenido'].startswith('Artículo 40.')
