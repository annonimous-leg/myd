"""Executed import-to-budget behaviour; synthetic fixtures are labelled as such.

Set MEGALODON_CMIC_PACKAGE, MEGALODON_VARELA_PACKAGE and
MEGALODON_CATALOG_ORIGINALS to exercise the private authentic source editions.
The genuine data are never copied into this public repository.
"""
import asyncio
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
from decimal import Decimal
from uuid import uuid4
from zipfile import ZipFile

from openpyxl import load_workbook
from pypdf import PdfReader
import pytest
from sqlalchemy import event, func, select, update

from app.core.errors import MegalodonException
from app.models.catalogo_apu import CatalogoAPU
from app.models.catalogo_importacion import CatalogoImportacion, CatalogoRegistro, EstimacionParametrica
from app.models.presupuesto import Partida
from app.models.user import Tenant, User, UserRole
from app.services.catalogo_importacion import estimate, fingerprint, import_package, prepare
from app.services.catalogo_package import SCHEMA, digest, verify_package
from tests.conftest import AsyncSessionLocalTest, _login
from tests.integration.test_closure_two_tenants import make_expediente
from tests.unit.test_catalogo_package import write_package

PARAMS = dict(factor_indirecto=0, factor_utilidad=0, factor_impuesto=0, factor_riesgo=0,
              fuente='CAPTURA_USUARIO', referencia='Prueba de costeo de fuente sin recargos')


@pytest.fixture
def synthetic_package(tmp_path):
    from tests.fixtures.catalog_import import make_synthetic_package
    return make_synthetic_package(tmp_path)


@pytest.mark.asyncio
async def test_atomic_import_retry_and_tenant_separation(db_session, tenant_a_user, tenant_b_user, synthetic_package):
    package, originals, _ = synthetic_package
    batch, created = await import_package(db_session, tenant_a_user[1], package, originals, {'SYNTHETIC'})
    assert created and batch.resumen['proyecciones_costeo'] == 1
    again, created = await import_package(db_session, tenant_a_user[1], package, originals, {'SYNTHETIC'})
    assert not created and again.id == batch.id
    assert await db_session.scalar(select(func.count()).select_from(CatalogoAPU).where(
        CatalogoAPU.tenant_id == tenant_a_user[0].id)) == 1
    other, created = await import_package(db_session, tenant_b_user[1], package, originals, {'SYNTHETIC'})
    assert created and other.id != batch.id


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['import', 'estimate'])
@pytest.mark.parametrize('revocation', ['role', 'disabled', 'session'])
async def test_revoked_actor_cannot_write_using_a_previously_loaded_identity(
        db_session, tenant_a_user, synthetic_package, operation, revocation):
    package, originals, _ = synthetic_package
    tenant, actor = tenant_a_user
    tenant_id, actor_id = tenant.id, actor.id
    if operation == 'estimate':
        batch, _ = await import_package(db_session, actor, package, originals, {'SYNTHETIC'})
        model = await db_session.scalar(select(CatalogoRegistro.id).where(
            CatalogoRegistro.importacion_id == batch.id, CatalogoRegistro.estado == 'PARAMETRICO'))
        factor = await db_session.scalar(select(CatalogoRegistro.id).where(
            CatalogoRegistro.importacion_id == batch.id, CatalogoRegistro.estado == 'FACTOR'))
    await db_session.commit()
    # The request already loaded an authorized identity. An independent
    # administration transaction revokes it before the business write.
    values = {'role': UserRole.LECTOR} if revocation == 'role' else (
        {'is_active': False} if revocation == 'disabled' else {'auth_version': actor.auth_version + 1})
    async with AsyncSessionLocalTest() as administration:
        await administration.execute(update(User).where(User.id == actor_id).values(**values))
        await administration.commit()
    assert actor.is_active and actor.role != UserRole.LECTOR
    with pytest.raises(MegalodonException) as rejected:
        if operation == 'import':
            await import_package(db_session, actor, package, originals, {'SYNTHETIC'})
        else:
            await estimate(db_session, actor, model, factor, Decimal('36'), Decimal('1'), 'Controlled revocation regression')
    assert rejected.value.status_code == 403
    assert await db_session.scalar(select(func.count()).select_from(EstimacionParametrica).where(
        EstimacionParametrica.tenant_id == tenant_id)) == 0
    if operation == 'import':
        assert await db_session.scalar(select(func.count()).select_from(CatalogoImportacion).where(
            CatalogoImportacion.tenant_id == tenant_id)) == 0


@pytest.mark.asyncio
async def test_failed_projection_rolls_back_entire_import(db_session, tenant_a_user, synthetic_package):
    package, originals, _ = synthetic_package
    tenant_id, user = tenant_a_user[0].id, tenant_a_user[1]
    bind = db_session.get_bind()
    def reject(connection, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith('INSERT INTO CATALOGOS_APU'):
            raise RuntimeError('simulated projection persistence failure')
    event.listen(bind, 'before_cursor_execute', reject)
    try:
        with pytest.raises(RuntimeError, match='projection persistence'):
            await import_package(db_session, user, package, originals, {'SYNTHETIC'})
    finally:
        event.remove(bind, 'before_cursor_execute', reject)
    for model in (CatalogoImportacion, CatalogoRegistro, CatalogoAPU):
        assert await db_session.scalar(select(func.count()).select_from(model).where(model.tenant_id == tenant_id)) == 0


@pytest.mark.asyncio
async def test_concurrent_retries_are_one_edition(db_session, tenant_a_user, synthetic_package):
    if db_session.get_bind().dialect.name != 'postgresql':
        pytest.skip('Row-lock semantics require the real PostgreSQL CI harness')
    package, originals, _ = synthetic_package
    user = tenant_a_user[1]
    async def run():
        async with AsyncSessionLocalTest() as db:
            return await import_package(db, user, package, originals, {'SYNTHETIC'})
    results = await asyncio.gather(run(), run())
    assert results[0][0].id == results[1][0].id
    assert sorted(created for _, created in results) == [False, True]


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['import', 'estimate'])
async def test_revocation_while_catalogue_writer_waits_for_tenant_lock(
        db_session, tenant_a_user, synthetic_package, monkeypatch, operation):
    if db_session.get_bind().dialect.name != 'postgresql':
        pytest.skip('Revocation during a row-lock wait requires PostgreSQL')
    import app.services.catalogo_importacion as service
    package, originals, _ = synthetic_package
    tenant, actor = tenant_a_user
    tenant_id, actor_id, version = tenant.id, actor.id, actor.auth_version
    if operation == 'estimate':
        batch, _ = await import_package(db_session, actor, package, originals, {'SYNTHETIC'})
        model = await db_session.scalar(select(CatalogoRegistro.id).where(
            CatalogoRegistro.importacion_id == batch.id, CatalogoRegistro.estado == 'PARAMETRICO'))
        factor = await db_session.scalar(select(CatalogoRegistro.id).where(
            CatalogoRegistro.importacion_id == batch.id, CatalogoRegistro.estado == 'FACTOR'))
    await db_session.commit()
    entered = asyncio.Event()
    original_lock = service._lock_writer
    async def observe_lock(db, user):
        entered.set()
        return await original_lock(db, user)
    monkeypatch.setattr(service, '_lock_writer', observe_lock)
    async def write():
        async with AsyncSessionLocalTest() as writer:
            if operation == 'import':
                return await import_package(writer, actor, package, originals, {'SYNTHETIC'})
            return await estimate(writer, actor, model, factor, Decimal('36'), Decimal('1'), 'Concurrent revocation regression')
    async with AsyncSessionLocalTest() as administration:
        await administration.scalar(select(Tenant.id).where(Tenant.id == tenant_id).with_for_update())
        pending = asyncio.create_task(write())
        try:
            await asyncio.wait_for(entered.wait(), timeout=5)
            assert not pending.done()
            await administration.execute(update(User).where(User.id == actor_id).values(auth_version=version + 1))
            await administration.commit()
            with pytest.raises(MegalodonException) as rejected:
                await asyncio.wait_for(pending, timeout=10)
            assert rejected.value.status_code == 403
        finally:
            await administration.rollback()
            if not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
    assert await db_session.scalar(select(func.count()).select_from(EstimacionParametrica).where(
        EstimacionParametrica.tenant_id == tenant_id)) == 0
    if operation == 'import':
        assert await db_session.scalar(select(func.count()).select_from(CatalogoImportacion).where(
            CatalogoImportacion.tenant_id == tenant_id)) == 0


@pytest.mark.parametrize('damage', ['missing_pdf', 'pending_child', 'arithmetic', 'tax', 'ambiguous_unit'])
def test_unreviewed_prices_remain_inspectable_not_usable(synthetic_package, damage):
    package, originals, records = synthetic_package
    if damage == 'missing_pdf': next(originals.glob('*.pdf')).unlink()
    if damage == 'pending_child': records['componente_partida'][0]['estado_revision'] = 'REQUIERE_REVISION'
    if damage == 'arithmetic': records['componente_partida'][0]['importe'] = '10.00'
    if damage == 'ambiguous_unit': records['partida_catalogo'][0]['unidad'] = 'kg $25.00'
    if damage == 'tax':
        page = records['pagina_fuente'][0]
        page.update(texto_bruto='SYNTHETIC', caracteres='9', texto_sha256=hashlib.sha256(b'SYNTHETIC').hexdigest())
    write_package(package, records)
    rows, projections = prepare(verify_package(package, originals), {'SYNTHETIC'})
    assert 'p' not in projections
    parent = next(r for r in rows if r['tabla'] == 'partida_catalogo')
    assert parent['estado'] == 'CUARENTENA' and parent['motivos']
    assert parent['original'] == records['partida_catalogo'][0]


@pytest.mark.asyncio
async def test_upload_preview_import_retry_rejects_reader_and_bad_manifest(async_client, db_session, tenant_a_user, synthetic_package, monkeypatch):
    from app.config import settings
    package, originals, records = synthetic_package
    monkeypatch.setattr(settings, 'CATALOGO_ORIGINALES_DIR', str(originals))
    def payload():
        buffer = BytesIO()
        with ZipFile(buffer, 'w') as archive:
            for path in package.rglob('*'):
                if path.is_file(): archive.write(path, 'nested/' + str(path.relative_to(package)))
        return buffer.getvalue()
    headers = await _login(async_client, tenant_a_user[1].email)
    preview = await async_client.post('/api/v1/catalogo-apu/importaciones/verificar', headers=headers,
                                     files={'archivo': ('source.zip', payload(), 'application/zip')})
    assert preview.status_code == 200, preview.text
    assert preview.json()['fuentes'][0]['original_cotejado']
    assert await db_session.scalar(select(func.count()).select_from(CatalogoImportacion).where(
        CatalogoImportacion.tenant_id == tenant_a_user[0].id)) == 0
    first = None
    for created in (True, False):
        response = await async_client.post('/api/v1/catalogo-apu/importaciones', headers=headers,
            files={'archivo': ('source.zip', payload(), 'application/zip')}, data={'fuentes': '["SYNTHETIC"]'})
        assert response.status_code == 200, response.text
        assert response.json()['creada'] is created
        if first is None: first = response.json()['id']
        assert response.json()['id'] == first
    manifest_path = package / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['counts']['partida_catalogo'] += 1
    manifest_path.write_text(json.dumps(manifest))
    bad = await async_client.post('/api/v1/catalogo-apu/importaciones', headers=headers,
        files={'archivo': ('bad.zip', payload(), 'application/zip')}, data={'fuentes': '["SYNTHETIC"]'})
    assert bad.status_code == 422 and 'Conteo incorrecto' in bad.text
    tenant_a_user[1].role = UserRole.LECTOR
    await db_session.commit()
    reader = await async_client.post('/api/v1/catalogo-apu/importaciones', headers=headers,
        files={'archivo': ('source.zip', payload(), 'application/zip')}, data={'fuentes': '["SYNTHETIC"]'})
    assert reader.status_code == 403


@pytest.mark.asyncio
async def test_create_from_catalogue_resolves_server_price_and_atomic_detail(async_client, db_session, tenant_a_user, synthetic_package):
    from app.models.presupuesto import Presupuesto
    package, originals, _ = synthetic_package
    tenant, user = tenant_a_user
    batch, _ = await import_package(db_session, user, package, originals, {'SYNTHETIC'})
    item = await db_session.scalar(select(CatalogoAPU).where(CatalogoAPU.tenant_id == tenant.id))
    exp = make_expediente(tenant, user)
    db_session.add(exp)
    await db_session.commit()
    headers = await _login(async_client, user.email)
    base = f'/api/v1/presupuestos/{exp.id}/presupuestos'
    response = await async_client.post(base, headers=headers, json={'nombre': 'Precio resuelto en servidor',
        'parametros_costeo': PARAMS, 'partidas': [{'numero': 1, 'catalogo_apu_id': str(item.id),
            'descripcion': 'client altered', 'unidad': 'wrong', 'cantidad': '2.4', 'precio_unitario': 1}]})
    assert response.status_code == 200, response.text
    result = response.json()
    assert Decimal(str(result['monto_total'])) == Decimal('365.83')
    line = result['partidas'][0]
    assert line['descripcion'] == item.descripcion and line['unidad'] == 'm3'
    assert line['metadatos']['catalogo_asignado']['origen_importacion']['importacion_id'] == str(batch.id)
    assert line['conceptos'][0]['insumos'][0]['cantidad'] == 0.227273
    budget_id = result['id']
    recalculated = await async_client.post(f'{base}/{budget_id}/recalcular', headers=headers)
    assert recalculated.status_code == 200 and recalculated.json()['monto_total'] == 365.83
    # An altered catalogue projection is detected before writing a new header.
    item.precio_unitario = 1
    await db_session.commit()
    denied = await async_client.post(base, headers=headers, json={'nombre': 'Debe fallar', 'parametros_costeo': PARAMS,
        'partidas': [{'numero': 1, 'catalogo_apu_id': str(item.id), 'descripcion': '', 'unidad': '', 'cantidad': 1}]})
    assert denied.status_code == 400 and 'difiere de su edición' in denied.text
    assert await db_session.scalar(select(func.count()).select_from(Presupuesto).where(Presupuesto.expediente_id == exp.id)) == 1


async def run_budget_flow(client, db, tenant, user, batch, clave, expected_pu, quantity, expected_total):
    from datetime import datetime, timedelta, timezone
    from app.models.entitlements import Suscripcion
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=31)
    tenant.plan, tenant.plan_vencimiento = 'ENTERPRISE', end
    db.add(Suscripcion(tenant_id=tenant.id, plan='ENTERPRISE', proveedor='TEST_SYNTHETIC',
        estado='ACTIVA', fecha_inicio=now, fecha_fin=end, monto=0, moneda='MXN',
        metadatos={'synthetic': True, 'purpose': 'disposable catalogue acceptance; no payment'}))
    user.role = UserRole.ADMIN
    exp = make_expediente(tenant, user)
    db.add(exp)
    await db.commit()
    headers = await _login(client, user.email)
    listing = await client.get(f'/api/v1/catalogo-apu?q={clave}&tipo=CONCEPTO', headers=headers)
    assert listing.status_code == 200, listing.text
    item = next(i for i in listing.json()['items'] if i['clave'] == clave and i['origen']['importacion_id'] == str(batch.id))
    base = f'/api/v1/presupuestos/{exp.id}/presupuestos'
    create = await client.post(base, headers=headers, json={'nombre': 'Catálogo importado', 'partidas': [], 'parametros_costeo': PARAMS})
    assert create.status_code == 200, create.text
    budget_id = create.json()['id']
    priced = await client.post(f'{base}/{budget_id}/partidas/desde-catalogo', headers=headers,
                              json={'catalogo_apu_id': item['id'], 'cantidad': str(quantity)})
    assert priced.status_code == 200, priced.text
    line = priced.json()['partidas'][0]
    assert Decimal(str(line['precio_unitario'])) == expected_pu
    assert Decimal(str(priced.json()['monto_total'])) == expected_total
    assert line['conceptos'][0]['insumos'][0]['cantidad'] == 0.227273
    # A new session/API request reloads Numeric from storage, not the in-memory
    # import dictionary. Repeated recalculation must reproduce the source cent.
    for _ in range(2):
        recalc = await client.post(f'{base}/{budget_id}/recalcular', headers=headers)
        assert recalc.status_code == 200, recalc.text
        assert Decimal(str(recalc.json()['monto_total'])) == expected_total
        assert recalc.json()['partidas'][0]['conceptos'][0]['insumos'][0]['cantidad'] == 0.227273
    for state in ('VALIDADO', 'APROBADO'):
        response = await client.patch(f'{base}/{budget_id}/estado', headers=headers, json={'estado': state})
        assert response.status_code == 200, response.text
    excel = await client.get(f'{base}/{budget_id}/excel', headers=headers)
    pdf = await client.get(f'{base}/{budget_id}/pdf', headers=headers)
    assert excel.status_code == pdf.status_code == 200
    workbook = load_workbook(BytesIO(excel.content), data_only=True)
    cells = [c.value for sheet in workbook for row in sheet for c in row]
    assert float(expected_total) in cells
    assert item['origen']['fuente']['sha256'] in cells
    assert item['origen']['fila_sha256'] in cells
    text = '\n'.join(p.extract_text() for p in PdfReader(BytesIO(pdf.content)).pages)
    assert f'{expected_total:,.2f}' in text and clave in text
    assert item['origen']['fuente']['sha256'] in text.replace('\n', '')
    mutation = await client.delete(f'/api/v1/catalogo-apu/{item["id"]}', headers=headers)
    assert mutation.status_code == 409
    return {'presupuesto_id': budget_id, 'pu': str(expected_pu), 'cantidad': str(quantity),
            'total': str(expected_total), 'pdf_leido': True, 'excel_leido': True, 'origen': item['origen']}, headers


@pytest.mark.asyncio
async def test_import_search_apu_persist_recalculate_approve_excel_pdf(async_client, db_session, tenant_a_user, synthetic_package):
    package, originals, _ = synthetic_package
    tenant, user = tenant_a_user
    batch, _ = await import_package(db_session, user, package, originals, {'SYNTHETIC'})
    await run_budget_flow(async_client, db_session, tenant, user, batch, 'TEST-EXC', Decimal('152.43'), Decimal('2.4'), Decimal('365.83'))


@pytest.mark.asyncio
async def test_parametric_estimate_persists_without_becoming_contractual_apu(async_client, db_session, tenant_a_user, tenant_b_user, synthetic_package):
    package, originals, _ = synthetic_package
    tenant, user = tenant_a_user
    batch, _ = await import_package(db_session, user, package, originals, {'SYNTHETIC'})
    headers = await _login(async_client, user.email)
    model = await db_session.scalar(select(CatalogoRegistro).where(CatalogoRegistro.importacion_id == batch.id, CatalogoRegistro.estado == 'PARAMETRICO'))
    factor = await db_session.scalar(select(CatalogoRegistro).where(CatalogoRegistro.importacion_id == batch.id, CatalogoRegistro.estado == 'FACTOR'))
    response = await async_client.post('/api/v1/catalogo-apu/estimaciones-parametricas', headers=headers, json={
        'modelo_registro_id': str(model.id), 'factor_registro_id': str(factor.id), 'cantidad': '36',
        'ajuste_proyecto': '1', 'justificacion': 'Condiciones coincidentes con modelo base en prueba'})
    assert response.status_code == 200, response.text
    result = response.json()
    assert Decimal(result['monto']) == Decimal('130128.36')
    assert not result['evidencia']['apto_aprobacion_contractual']
    assert result['evidencia']['modelo_sha256'] == model.sha256
    saved = await async_client.get(f'/api/v1/catalogo-apu/estimaciones-parametricas/{result["id"]}', headers=headers)
    assert saved.json() == result
    other = await _login(async_client, tenant_b_user[1].email)
    assert (await async_client.get(f'/api/v1/catalogo-apu/estimaciones-parametricas/{result["id"]}', headers=other)).status_code == 404
    assert (await async_client.get(f'/api/v1/catalogo-apu/importaciones/{batch.id}/registros', headers=other)).status_code == 404


@pytest.mark.asyncio
async def test_authentic_cmic_varela_operational_flow(async_client, db_session, tenant_a_user):
    names = ('MEGALODON_CMIC_PACKAGE', 'MEGALODON_VARELA_PACKAGE', 'MEGALODON_CATALOG_ORIGINALS')
    if not all(os.getenv(n) for n in names):
        pytest.skip('Private authentic catalogue packages and original PDFs must be supplied explicitly')
    cmic_path, varela_path, originals = (Path(os.environ[n]) for n in names)
    tenant, user = tenant_a_user
    cmic_sources = {r['fuente_id'] for r in verify_package(cmic_path, originals).records['fuente']}
    batch, created = await import_package(db_session, user, cmic_path, originals, cmic_sources)
    assert created
    result, headers = await run_budget_flow(async_client, db_session, tenant, user, batch, 'E01.024',
                                          Decimal('152.43'), Decimal('2.4'), Decimal('365.83'))
    same, created = await import_package(db_session, user, cmic_path, originals, cmic_sources)
    assert not created and same.id == batch.id
    varela_sources = {r['fuente_id'] for r in verify_package(varela_path, originals).records['fuente'] if r['fuente_id'].startswith('varela_')}
    varela, _ = await import_package(db_session, user, varela_path, originals, varela_sources)
    assert varela.resumen['proyecciones_costeo'] == 0  # assemblies lack a price; models are antebudgets
    model = await db_session.scalar(select(CatalogoRegistro).where(CatalogoRegistro.importacion_id == varela.id,
        CatalogoRegistro.tabla == 'modelo_parametrico', CatalogoRegistro.original['codigo'].as_string() == '01-002'))
    pending_model = await db_session.scalar(select(CatalogoRegistro).where(CatalogoRegistro.importacion_id == varela.id,
        CatalogoRegistro.tabla == 'modelo_parametrico', CatalogoRegistro.original['codigo'].as_string() == '01-001'))
    assert pending_model.estado == 'CUARENTENA'
    factor = await db_session.scalar(select(CatalogoRegistro).where(CatalogoRegistro.importacion_id == varela.id,
        CatalogoRegistro.tabla == 'factor_geografico', CatalogoRegistro.original['localidad_base'].as_string() == 'AGUASCALIENTES'))
    assert model.estado == 'PARAMETRICO' and factor.estado == 'FACTOR'
    response = await async_client.post('/api/v1/catalogo-apu/estimaciones-parametricas', headers=headers, json={
        'modelo_registro_id': str(model.id), 'factor_registro_id': str(factor.id), 'cantidad': '43',
        'ajuste_proyecto': '1', 'justificacion': 'Caso de aceptación: superficie base de la casa clase 2 SHF'})
    assert response.status_code == 200, response.text
    actual = response.json()
    assert Decimal(actual['monto']) == Decimal('333486.02')
    assert not actual['evidencia']['apto_aprobacion_contractual']
    pending = await db_session.scalar(select(CatalogoRegistro).where(CatalogoRegistro.importacion_id == batch.id,
        CatalogoRegistro.tabla == 'partida_catalogo', CatalogoRegistro.entidad_id == 'partida_638cc46e09d4265112c216c4'))
    assert pending.estado == 'CUARENTENA'
    assert not await db_session.scalar(select(CatalogoAPU.id).where(CatalogoAPU.registro_importado_id == pending.id))
    report_path = os.getenv('MEGALODON_CATALOG_EVIDENCE_REPORT')
    if report_path:
        Path(report_path).write_text(json.dumps({'cmic': batch.resumen, 'cmic_flujo': result,
            'varela': varela.resumen, 'varela_estimacion': actual, 'alcance': 'API real y SQLite de pruebas; no Supabase ni certificación visual universal',
            'produccion_general': 'NO GO'}, ensure_ascii=False, indent=2))


@pytest.mark.asyncio
async def test_all_pending_catalogue_types_are_visible_and_paginated(
        async_client, db_session, tenant_a_user, synthetic_package):
    package, originals, records = synthetic_package
    for table in ('partida_catalogo', 'modelo_parametrico', 'factor_geografico'):
        records[table][0]['estado_revision'] = 'REQUIERE_REVISION'
    write_package(package, records)
    batch, _ = await import_package(db_session, tenant_a_user[1], package, originals, {'SYNTHETIC'})
    assert batch.resumen['estados']['CUARENTENA'] == 3
    headers = await _login(async_client, tenant_a_user[1].email)
    url = f'/api/v1/catalogo-apu/importaciones/{batch.id}/registros'
    seen = []
    for skip in range(3):
        response = await async_client.get(url, headers=headers,
            params={'tabla': '*', 'estado': 'CUARENTENA', 'skip': skip, 'limit': 1})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['total'] == 3
        item, = result['items']
        assert item['estado'] == 'CUARENTENA' and item['motivos']
        seen.append(item)
    assert len({item['id'] for item in seen}) == 3
    assert {item['tabla'] for item in seen} == {'partida_catalogo', 'modelo_parametrico', 'factor_geografico'}
    # Existing table-specific callers keep their contract.
    response = await async_client.get(url, headers=headers, params={'estado': 'CUARENTENA'})
    assert response.json()['total'] == 1
    assert response.json()['items'][0]['tabla'] == 'partida_catalogo'
