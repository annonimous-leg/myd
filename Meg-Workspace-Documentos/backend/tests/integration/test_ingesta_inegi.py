"""HTTP and database ingestion tests using explicitly SYNTHETIC source documents."""
import asyncio
import json
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.models.indices_costos import CargaIndiceCosto, ObservacionIndiceCosto
from tests.integration.test_indices_costos import indices, BASE  # noqa: F401
from tests.unit.test_ingesta_inegi import contrato_controlado, documento_controlado, datos_archivo


@pytest_asyncio.fixture
async def carga_inegi(async_client, indices):
    contrato = contrato_controlado()
    contrato.indicador = str(uuid4().int)[:29]
    response = await async_client.post(BASE + '/series', headers=indices['global_auth'], json={
        'codigo': contrato.indicador, 'version_metodologia': 'CONTROLADA-NO-OFICIAL',
        'nombre': 'MATERIAL SINTÉTICO NO OFICIAL', 'alcance': 'MATERIAL', 'region': 'CONTROLADA',
        'moneda': 'MXN', 'incluye_iva': False, 'condiciones_precio': 'DATOS SINTÉTICOS, NO USAR EN PRODUCCIÓN',
        'periodo_referencia': 'CONTROLADO=100', 'evidencia': contrato.evidencia_metadatos.model_dump(mode='json'),
        'contrato_inegi': contrato.model_dump(mode='json')})
    assert response.status_code == 201, response.text
    documento = documento_controlado()
    documento['Series'][0]['INDICADOR'] = contrato.indicador
    archivo = json.dumps(documento).encode()
    data = datos_archivo(archivo, response.json()['id'])
    return {**indices, 'archivo': archivo, 'data': data, 'documento': documento}


async def cargar(client, fixture, *, confirmar=True, auth=None, archivo=None, data=None):
    return await client.post(BASE + '/cargas/inegi', params={'confirmar': str(confirmar).lower()},
        headers=auth or fixture['global_auth'], files={'archivo': ('original.json', archivo or fixture['archivo'], 'application/json')},
        data={'metadatos': (data or fixture['data']).model_dump_json()})


@pytest.mark.asyncio
async def test_previsualizar_importar_y_repetir_archivo(async_client, db_session, carga_inegi):
    f = carga_inegi
    preview = await cargar(async_client, f, confirmar=False)
    assert preview.status_code == 200, preview.text
    assert preview.json()['estado'] == 'VALIDADO_SIN_REGISTRAR'
    assert preview.json()['carga_id'] is None
    assert not await db_session.scalar(select(CargaIndiceCosto.id).where(CargaIndiceCosto.serie_id == f['data'].serie_id))
    first = await cargar(async_client, f)
    assert first.status_code == 200, first.text
    again = await cargar(async_client, f)
    assert again.status_code == 200, again.text
    assert first.json()['carga_id'] == again.json()['carga_id']
    assert again.json()['repetida'] is True
    assert await db_session.scalar(select(func.count()).select_from(ObservacionIndiceCosto).where(
        ObservacionIndiceCosto.serie_id == f['data'].serie_id)) == 2
    download = await async_client.get(BASE + f"/cargas/{first.json()['carga_id']}/archivo", headers=f['global_auth'])
    assert download.content == f['archivo']
    assert download.headers['cache-control'] == 'no-store'
    # PostgreSQL is the precision authority; SQLite converts Numeric to floats.
    rows = (await db_session.scalars(select(ObservacionIndiceCosto).where(
        ObservacionIndiceCosto.serie_id == f['data'].serie_id).order_by(ObservacionIndiceCosto.mes))).all()
    if db_session.bind.dialect.name == 'postgresql':
        assert rows[0].valor == Decimal('100.12345678901234567')
        assert rows[1].valor == Decimal('110.76543210987654321')
    retirada = await async_client.post(BASE + '/retiros', headers=f['global_auth'], json={
        'observacion_id': str(rows[0].id), 'motivo': 'Prueba controlada de retiro; no reactivar con importación'})
    assert retirada.status_code == 201, retirada.text
    replay = await cargar(async_client, f)
    assert replay.status_code == 200
    assert replay.json()['estado'] == 'REGISTRADO_CON_RETIROS'
    assert replay.json()['observaciones_retiradas'] == 1
    visible = await async_client.get(BASE + '/observaciones', params={'serie_id': str(f['data'].serie_id)}, headers=f['auth'])
    assert len(visible.json()) == 1


@pytest.mark.asyncio
async def test_rechazo_de_huella_y_permisos_sin_escrituras(async_client, db_session, carga_inegi):
    f = carga_inegi
    assert (await cargar(async_client, f, auth=f['auth'])).status_code == 403
    bad = await cargar(async_client, f, archivo=f['archivo'] + b' ')
    assert bad.status_code == 400, bad.text
    assert not await db_session.scalar(select(CargaIndiceCosto.id).where(CargaIndiceCosto.serie_id == f['data'].serie_id))
    missing = await async_client.get(BASE + f'/cargas/{uuid4()}/archivo', headers=f['auth'])
    assert missing.status_code == 403


@pytest.mark.asyncio
async def test_colision_revierte_archivo_y_todas_las_observaciones(async_client, db_session, carga_inegi):
    f = carga_inegi
    existing = await async_client.post(BASE + '/observaciones', headers=f['global_auth'], json={
        'serie_id': str(f['data'].serie_id), 'medida': 'NIVEL', 'mes': '2020-02-01', 'valor': '110',
        'publicado_el': '2020-03-10', 'evidencia': f['data'].evidencia.model_dump(mode='json')})
    assert existing.status_code == 201, existing.text
    result = await cargar(async_client, f)
    assert result.status_code == 409, result.text
    assert not await db_session.scalar(select(CargaIndiceCosto.id).where(CargaIndiceCosto.serie_id == f['data'].serie_id))
    assert await db_session.scalar(select(func.count()).select_from(ObservacionIndiceCosto).where(
        ObservacionIndiceCosto.serie_id == f['data'].serie_id)) == 1


@pytest.mark.asyncio
async def test_inegi_importado_alimenta_motor_real(async_client, db_session, carga_inegi):
    f = carga_inegi
    response = await cargar(async_client, f)
    assert response.status_code == 200, response.text
    mappings = await async_client.get(BASE + '/vinculos', headers=f['auth'])
    old = next(row for row in mappings.json() if row['id'] == f['refs'][0]['vinculo_id'])
    link = await async_client.post(BASE + '/vinculos', headers=f['auth'], json={
        'insumo_id': old['insumo_id'], 'serie_id': str(f['data'].serie_id), 'mes_base': '2020-01-01',
        'region': 'CONTROLADA', 'fundamento': 'Correspondencia exclusivamente sintética para integración',
        'evidencia': f['data'].evidencia.model_dump(mode='json')})
    assert link.status_code == 201, link.text
    obs = await async_client.get(BASE + '/observaciones', params={'serie_id': str(f['data'].serie_id)}, headers=f['auth'])
    price = await async_client.post(BASE + '/calcular', headers=f['auth'], json={
        'vinculo_id': link.json()['id'], 'observacion_base_id': obs.json()[0]['id'], 'observacion_destino_id': obs.json()[1]['id']})
    assert price.status_code == 200, price.text
    assert price.json()['precio_actualizado'] == '22.13'
    assert price.json()['base']['carga_id'] == response.json()['carga_id']


@pytest.mark.asyncio
async def test_postgres_reimportacion_concurrente_e_inmutabilidad(async_client, db_session, carga_inegi):
    if db_session.bind.dialect.name != 'postgresql':
        pytest.skip('Requires PostgreSQL row locking and evidence triggers')
    f = carga_inegi
    a, b = await asyncio.wait_for(
        asyncio.gather(cargar(async_client, f), cargar(async_client, f)), timeout=15)
    assert a.status_code == b.status_code == 200, (a.text, b.text)
    assert a.json()['carga_id'] == b.json()['carga_id']
    assert sorted([a.json()['repetida'], b.json()['repetida']]) == [False, True]
    for statement in ["UPDATE cargas_indices_costos SET archivo=archivo WHERE id=:id",
                      "DELETE FROM cargas_indices_costos WHERE id=:id", "TRUNCATE cargas_indices_costos CASCADE"]:
        with pytest.raises(DBAPIError, match='evidencia de índices es inmutable'):
            await db_session.execute(text(statement), {'id': UUID(a.json()['carga_id'])})
        await db_session.rollback()
    # Even a direct SQL writer cannot detach an observation from its source's
    # identity, edition date, or actual bytes.
    wrong_file = """INSERT INTO cargas_indices_costos
        (id, serie_id, documento_sha256, publicado_el, mes_inicio, mes_fin,
         ultima_actualizacion, evidencia, archivo, registrado_por)
        SELECT :newid, serie_id, :sha, publicado_el, mes_inicio, mes_fin,
         ultima_actualizacion, evidencia, archivo, registrado_por
        FROM cargas_indices_costos WHERE id=:id"""
    with pytest.raises(DBAPIError, match='ck_carga_indice_sha'):
        await db_session.execute(text(wrong_file), {'id': UUID(a.json()['carga_id']), 'newid': uuid4(), 'sha': 'b' * 64})
    await db_session.rollback()
    for change in ["(CASE WHEN left(documento_sha256,1)='b' THEN 'a' ELSE 'b' END) || substring(documento_sha256 from 2)", "documento_sha256"]:
        publication = "publicado_el" if change != 'documento_sha256' else "publicado_el + 1"
        sql = f"""INSERT INTO observaciones_indices_costos
            (id, serie_id, mes, valor, publicado_el, documento_sha256, evidencia, registrado_por, carga_id)
            SELECT :newid, serie_id, DATE '2019-12-01', valor, {publication}, {change}, evidencia, registrado_por, carga_id
            FROM observaciones_indices_costos WHERE carga_id=:id ORDER BY mes LIMIT 1"""
        with pytest.raises(DBAPIError, match='fk_observacion_carga'):
            await db_session.execute(text(sql), {'id': UUID(a.json()['carga_id']), 'newid': uuid4()})
        await db_session.rollback()
