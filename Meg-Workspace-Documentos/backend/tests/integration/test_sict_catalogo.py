"""SICT PDF → immutable source edition → operational costing.

Public source fixtures are explicitly synthetic. Set MEGALODON_SICT_PACKAGE
and MEGALODON_SICT_ORIGINALS to execute the real document acceptance privately.
"""
from collections import Counter
from decimal import Decimal
from io import BytesIO
import json
import os
from pathlib import Path

from openpyxl import load_workbook
from pypdf import PdfReader
import pytest
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import func, select

from app.core.errors import MegalodonException
from app.models.catalogo_apu import CatalogoAPU
from app.models.catalogo_importacion import CatalogoRegistro, EstimacionParametrica
from app.services.catalogo_importacion import estimate, fingerprint, import_package, prepare, source_without_vat
from app.services.catalogo_package import verify_package
from app.services.sict_catalogo import PROFILES, extract_page, extract_source, write_package
from tests.conftest import _login
from tests.integration.test_catalogo_importacion import PARAMS
from tests.integration.test_closure_two_tenants import make_expediente


@pytest.fixture
def synthetic_package(tmp_path):
    from tests.fixtures.catalog_import import make_synthetic_package
    return make_synthetic_package(tmp_path)


def word(text, x, y):
    return dict(text=text, x0=x, x1=x+8, top=y, bottom=y+8)


def test_sict_columns_preserve_hourly_modes_and_do_not_use_acquisition_as_price():
    words = [word('1011',120,140), word('Synthetic',150,140), word('machine',190,140),
             word('$771.70',345,140), word('$14,893.80',407,140), word('$100.81',455,140),
             word('$83.85',498,140), word('$3.22',548,140)]
    items = extract_page(list(reversed(words)), PROFILES['maquinaria'], 12)
    assert len(items) == 1
    assert items[0]['description'] == 'Synthetic machine'
    assert [v['text'] for v in items[0]['prices']] == ['$771.70', '$14,893.80', '$100.81', '$83.85', '$3.22']


def test_sict_missing_unit_is_preserved_as_missing_not_changed_to_lot():
    items = extract_page([word('CA1010.1010',52,140), word('Synthetic',113,140), word('$33,532.23',516,140)], PROFILES['servicios'],43)
    assert items[0]['unit'] == ''
    assert items[0]['prices'][0]['text'] == '$33,532.23'


@pytest.fixture
def source_package(tmp_path):
    originals = tmp_path/'originals'; originals.mkdir()
    pdf = originals/'synthetic-sict.pdf'
    c = Canvas(str(pdf))
    for number in range(1,44):
        c.drawString(40,750,'Synthetic fixture; not an official source')
        if number == 2:
            c.drawString(40,710,'TABULADOR DE SERVICIOS RELACIONADOS CON LA OBRA 2026')
            c.drawString(40,690,'Vigente desde 1 de febrero de 2026')
            c.drawString(40,670,'Los precios no incluyen el IVA.')
        if number == 43:
            c.setFont('Helvetica',8)
            c.drawString(52,640,'CA1010.1010'); c.drawString(113,640,'Synthetic topographic study')
            c.drawString(468,640,'km'); c.drawString(516,640,'$33,532.23')
        c.showPage()
    c.save()
    records = extract_source(pdf,'servicios')
    package = tmp_path/'package'; write_package(package,records)
    return package, originals, records


def test_sict_extracts_declared_vigencia_and_cotes_original_pdf(source_package):
    package, originals, records = source_package
    verified = verify_package(package, originals)
    assert verified.missing_source_ids == set()
    assert records['fuente'][0]['fecha_vigencia'] == '2026-02-01'
    assert len(records['pagina_fuente']) == 43
    rows, prices = prepare(verified, set(verified.verified_source_ids))
    assert Counter(r['estado'] for r in rows)['COTIZABLE'] == 1
    p = next(iter(prices.values()))
    assert p['precio_unitario'] == Decimal('33532.23') and p['unidad'] == 'km'
    assert p['desglose'] is None  # Published observed cost, not a fabricated APU.


@pytest.fixture
def construction_editions(tmp_path):
    """Two small synthetic editions exercise the documented construction layout."""
    originals = tmp_path / 'originals'
    originals.mkdir()
    editions = []
    for month, price in [('febrero', '92.07'), ('julio', '92.31')]:
        pdf = originals / f'synthetic-construction-{month}.pdf'
        canvas = Canvas(str(pdf))
        for number in range(1, 89):
            canvas.setFont('Helvetica', 8)
            if number == 2:
                canvas.drawString(40, 710, 'TABULADOR A COSTO DIRECTO PARA LA CONSTRUCCIÓN 2026')
                canvas.drawString(40, 690, f'Aplica a partir del 1 de {month} de 2026')
                canvas.drawString(40, 670, 'Los precios no incluyen el IVA.')
            if number == 88:
                canvas.drawString(81, 640, '101.03.1100')
                canvas.drawString(150, 640, 'Synthetic cut; not an official source')
                canvas.drawString(480, 640, 'm3')
                canvas.drawString(530, 640, f'${price}')
            canvas.showPage()
        canvas.save()
        records = extract_source(pdf, 'construccion')
        package = tmp_path / month
        write_package(package, records)
        editions.append((package, originals, records))
    return editions


def test_construction_editions_preserve_document_dates_prices_and_identity(construction_editions):
    source_ids = []
    for (package, originals, records), effective, expected_price in zip(
        construction_editions, ['2026-02-01', '2026-07-01'], ['92.07', '92.31'], strict=True
    ):
        verified = verify_package(package, originals)
        source = records['fuente'][0]
        source_ids.append(source['fuente_id'])
        assert source['fecha_vigencia'] == source['edicion'] == effective
        assert records['partida_catalogo'][0]['fecha_precio'] == effective
        rows, prices = prepare(verified, set(verified.verified_source_ids))
        assert Counter(r['estado'] for r in rows)['COTIZABLE'] == 1
        price, = prices.values()
        assert price['precio_unitario'] == Decimal(expected_price)
        assert price['vigencia_inicio'] == effective
        assert price['origen']['fuente']['sha256'] == source['sha256']
    assert len(set(source_ids)) == 2


@pytest.mark.asyncio
async def test_sict_sector_factor_cannot_be_replaced_by_general_or_other_pavement(db_session, tenant_a_user, synthetic_package):
    from tests.unit.test_catalogo_package import write_package as fixture_write
    package, originals, records = synthetic_package
    source = records['fuente'][0];source['familia']='SICT_DGST_2026'
    records['modelo_parametrico'][0]['aplicabilidad']=json.dumps({'fic_especialidad':'CARRETERA_ASFALTICA'})
    records['factor_geografico'][0]['instrucciones']=json.dumps({'fic_especialidad':'GENERAL'})
    fixture_write(package, records)
    batch,_=await import_package(db_session, tenant_a_user[1], package, originals, {'SYNTHETIC'})
    model=await db_session.scalar(select(CatalogoRegistro).where(CatalogoRegistro.importacion_id==batch.id,CatalogoRegistro.estado=='PARAMETRICO'))
    factor=await db_session.scalar(select(CatalogoRegistro).where(CatalogoRegistro.importacion_id==batch.id,CatalogoRegistro.estado=='FACTOR'))
    model_id, factor_id = model.id, factor.id
    for scope in ['GENERAL','CARRETERA_HIDRAULICA']:
        factor.original={**factor.original,'instrucciones':json.dumps({'fic_especialidad':scope})}
        factor.sha256=fingerprint(factor.original);await db_session.commit()
        with pytest.raises(MegalodonException,match='especialidad'):
            await estimate(db_session,tenant_a_user[1],model_id,factor_id,Decimal(36),Decimal(1),'Sector regression')
        await db_session.refresh(tenant_a_user[1])
        factor=await db_session.get(CatalogoRegistro,factor_id)
    assert await db_session.scalar(select(func.count()).select_from(EstimacionParametrica).where(
        EstimacionParametrica.modelo_registro_id == model_id)) == 0
    factor.original={**factor.original,'instrucciones':json.dumps({'fic_especialidad':'CARRETERA_ASFALTICA'})}
    factor.sha256=fingerprint(factor.original);await db_session.commit()
    result=await estimate(db_session,tenant_a_user[1],model_id,factor_id,Decimal(36),Decimal(1),'Correct sector regression')
    assert result.monto == Decimal('130128.36') and not result.evidencia['apto_aprobacion_contractual']


async def costing_flow(client, db, tenant, user, batch, clave='CA1010.1010', pu=Decimal('33532.23'), unidad='km', total=Decimal('80477.35')):
    from app.models.user import UserRole
    user.role=UserRole.ADMIN
    exp=make_expediente(tenant,user);db.add(exp);await db.commit()
    headers=await _login(client,user.email)
    item=await db.scalar(select(CatalogoAPU).where(CatalogoAPU.registro_importado_id.in_(
        select(CatalogoRegistro.id).where(CatalogoRegistro.importacion_id==batch.id)),CatalogoAPU.clave==clave))
    assert item and item.unidad==unidad and item.precio_unitario==pu
    url=f'/api/v1/presupuestos/{exp.id}/presupuestos'
    response=await client.post(url,headers=headers,json={'nombre':'SICT fuente importada', 'parametros_costeo':PARAMS,
        'partidas':[{'numero':1,'catalogo_apu_id':str(item.id),'descripcion':'','unidad':'','cantidad':'2.4'}]})
    assert response.status_code==200,response.text
    budget=response.json();assert Decimal(str(budget['monto_total']))==total
    assert not budget['partidas'][0]['conceptos']  # No matrix was published.
    budget_id=budget['id']
    for _ in range(2):
        response=await client.post(f'{url}/{budget_id}/recalcular',headers=headers)
        assert response.status_code==200 and Decimal(str(response.json()['monto_total']))==total
    for state in ['VALIDADO','APROBADO']:
        response=await client.patch(f'{url}/{budget_id}/estado',headers=headers,json={'estado':state})
        assert response.status_code==200,response.text
    xlsx=await client.get(f'{url}/{budget_id}/excel',headers=headers)
    pdf=await client.get(f'{url}/{budget_id}/pdf',headers=headers)
    assert xlsx.status_code==pdf.status_code==200
    cells=[c.value for sheet in load_workbook(BytesIO(xlsx.content),data_only=True) for row in sheet for c in row]
    assert float(total) in cells and item.origen['fuente']['sha256'] in cells
    text=' '.join(p.extract_text() for p in PdfReader(BytesIO(pdf.content)).pages)
    assert f'{total:,.2f}' in text and clave in text
    assert item.origen['fuente']['sha256'] in text.replace('\n','')
    return f'{url}/{budget_id}'


async def enable_disposable_catalog_acceptance_plan(db, tenant):
    from datetime import datetime, timedelta, timezone
    from app.models.entitlements import Suscripcion
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=31)
    tenant.plan = 'ENTERPRISE'
    tenant.plan_vencimiento = end
    db.add(Suscripcion(tenant_id=tenant.id, plan='ENTERPRISE', proveedor='TEST_SYNTHETIC',
        estado='ACTIVA', fecha_inicio=now, fecha_fin=end, monto=0, moneda='MXN',
        metadatos={'synthetic': True, 'purpose': 'disposable SICT acceptance; no payment'}))
    await db.commit()


async def check_construction_edition_coexistence(client, db, tenant, user, editions):
    await enable_disposable_catalog_acceptance_plan(db, tenant)
    urls, batches = [], []
    for (package, originals, _), pu, total in zip(
        editions, ['92.07', '92.31'], ['220.97', '221.54'], strict=True
    ):
        verified = verify_package(package, originals)
        selected = {r['fuente_id'] for r in verified.records['fuente']
                    if json.loads(r['metadatos']).get('perfil') == 'construccion'}
        assert len(selected) == 1
        batch, created = await import_package(db, user, package, originals, selected)
        assert created
        batches.append(batch.id)
        urls.append(await costing_flow(client, db, tenant, user, batch,
            clave='101.03.1100', pu=Decimal(pu), unidad='m3', total=Decimal(total)))
        again, created = await import_package(db, user, package, originals, selected)
        assert not created and again.id == batch.id
    assert len(set(batches)) == 2
    items = list((await db.scalars(select(CatalogoAPU).where(
        CatalogoAPU.tenant_id == tenant.id, CatalogoAPU.clave == '101.03.1100'))).all())
    assert len(items) == 2
    assert {str(item.vigencia_inicio) for item in items} == {'2026-02-01', '2026-07-01'}
    assert len({item.origen['fuente']['sha256'] for item in items}) == 2
    # After importing July, the approved February budget still exports its
    # original amount and original source hash, not July's catalogue value.
    headers = await _login(client, user.email)
    february = next(item for item in items if str(item.vigencia_inicio) == '2026-02-01')
    response = await client.get(urls[0] + '/excel', headers=headers)
    assert response.status_code == 200
    cells = [c.value for sheet in load_workbook(BytesIO(response.content), data_only=True)
             for row in sheet for c in row]
    assert 220.97 in cells and february.origen['fuente']['sha256'] in cells
    assert 221.54 not in cells


@pytest.mark.asyncio
async def test_july_import_preserves_february_budget_and_retry_identity(
    async_client, db_session, tenant_a_user, construction_editions
):
    await check_construction_edition_coexistence(
        async_client, db_session, *tenant_a_user, construction_editions)


@pytest.mark.asyncio
async def test_authentic_july_construction_and_february_coexistence(async_client, db_session, tenant_a_user):
    february = os.environ.get('MEGALODON_SICT_PACKAGE')
    july = os.environ.get('MEGALODON_SICT_JULY_PACKAGE')
    originals = os.environ.get('MEGALODON_SICT_ORIGINALS')
    if not all((february, july, originals)):
        pytest.skip('Private February and July SICT construction packages not supplied')
    verified = verify_package(Path(july), Path(originals))
    source, = verified.records['fuente']
    assert source['sha256'] == '91240656edcc3c7dbeb92c1765ab61fe37e7019419392828835951624b62d772'
    assert source['paginas'] == '485' and source['fecha_vigencia'] == '2026-07-01'
    assert len(verified.records['partida_catalogo']) == 3825
    rows, _ = prepare(verified, set(verified.verified_source_ids))
    assert Counter(r['estado'] for r in rows) == {'CONSULTA': 486, 'COTIZABLE': 3811, 'CUARENTENA': 14}
    assert not {'102.10.1110', '302.06.1110', '302.09.1100'} & {
        r['codigo'] for r in verified.records['partida_catalogo']}
    await check_construction_edition_coexistence(async_client, db_session, *tenant_a_user,
        [(Path(february), Path(originals), None), (Path(july), Path(originals), None)])


@pytest.mark.asyncio
async def test_pdf_source_import_cost_recalculate_approve_read_exports(async_client,db_session,tenant_a_user,source_package):
    package,originals,records=source_package
    batch,_=await import_package(db_session,tenant_a_user[1],package,originals,{records['fuente'][0]['fuente_id']})
    await costing_flow(async_client,db_session,*tenant_a_user,batch)


@pytest.mark.asyncio
async def test_authentic_sict_pdf_import_and_costing(async_client,db_session,tenant_a_user):
    package=os.environ.get('MEGALODON_SICT_PACKAGE');originals=os.environ.get('MEGALODON_SICT_ORIGINALS')
    if not package or not originals:pytest.skip('Private official SICT source package not supplied')
    tenant, user = tenant_a_user
    await enable_disposable_catalog_acceptance_plan(db_session, tenant)
    verified=verify_package(Path(package),Path(originals))
    selected=set(verified.verified_source_ids)
    batch,created=await import_package(db_session,tenant_a_user[1],Path(package),Path(originals),selected)
    assert created and not verified.missing_source_ids
    await costing_flow(async_client,db_session,*tenant_a_user,batch)
    await costing_flow(async_client,db_session,*tenant_a_user,batch,clave='101.03.1100',pu=Decimal('92.07'),unidad='m3',total=Decimal('220.97'))
    for variant, price in [('ACTIVO','100.81'),('ESPERA','83.85'),('RESERVA','3.22')]:
        machine=await db_session.scalar(select(CatalogoAPU).where(CatalogoAPU.tenant_id==tenant.id,CatalogoAPU.clave=='1011:'+variant))
        assert machine.tipo=='MAQUINARIA' and machine.unidad=='h' and machine.precio_unitario==Decimal(price)
        assert machine.origen['aplicabilidad']['modo_maquinaria']==variant
    headers=await _login(async_client,tenant_a_user[1].email)
    model=await db_session.scalar(select(CatalogoRegistro).where(CatalogoRegistro.importacion_id==batch.id,
        CatalogoRegistro.tabla=='modelo_parametrico',CatalogoRegistro.original['codigo'].as_string()=='A21A1P'))
    assert model.estado=='PARAMETRICO' and model.original['costo_por_unidad']=='30037837'
    factor=await db_session.scalar(select(CatalogoRegistro).where(CatalogoRegistro.importacion_id==batch.id,
        CatalogoRegistro.tabla=='factor_geografico',CatalogoRegistro.original['localidad_base'].as_string()=='Aguascalientes',
        CatalogoRegistro.original['instrucciones'].as_string().contains('CARRETERA_ASFALTICA')))
    assert factor.original['valor']=='1.1155'
    response=await async_client.post('/api/v1/catalogo-apu/estimaciones-parametricas',headers=headers,json={
        'modelo_registro_id':str(model.id),'factor_registro_id':str(factor.id),'cantidad':'2.4',
        'ajuste_proyecto':'1','justificacion':'Caso documental SICT, pavimento asfáltico y alcance original'})
    assert response.status_code==200,response.text
    result=response.json();assert Decimal(result['monto'])==Decimal('80417297.22')
    assert not result['evidencia']['apto_aprobacion_contractual']
    assert json.loads(result['evidencia']['modelo']['aplicabilidad'])['acarreo_incluido_km']==10
    saved=await async_client.get('/api/v1/catalogo-apu/estimaciones-parametricas/'+result['id'],headers=headers)
    assert saved.status_code==200 and saved.json()==result
    # The authentic PDF joins CONCRETOHIDRÁULICO in this row. Its price and
    # hydraulic factor must survive extraction, import, calculation and reload.
    hydraulic = await db_session.scalar(select(CatalogoRegistro).where(
        CatalogoRegistro.importacion_id == batch.id,
        CatalogoRegistro.tabla == 'modelo_parametrico',
        CatalogoRegistro.original['codigo'].as_string() == 'ET42H1P'))
    assert hydraulic.estado == 'PARAMETRICO'
    assert hydraulic.original['costo_por_unidad'] == '76269489'
    hydraulic_factor = await db_session.scalar(select(CatalogoRegistro).where(
        CatalogoRegistro.importacion_id == batch.id,
        CatalogoRegistro.tabla == 'factor_geografico',
        CatalogoRegistro.original['localidad_base'].as_string() == 'Aguascalientes',
        CatalogoRegistro.original['instrucciones'].as_string().contains('CARRETERA_HIDRAULICA')))
    assert hydraulic_factor.original['valor'] == '1.0970'
    response = await async_client.post('/api/v1/catalogo-apu/estimaciones-parametricas', headers=headers,
        json={'modelo_registro_id': str(hydraulic.id), 'factor_registro_id': str(hydraulic_factor.id),
              'cantidad': '2.4', 'ajuste_proyecto': '1',
              'justificacion': 'Aceptación documental de carretera hidráulica ET42H1P'})
    assert response.status_code == 200, response.text
    result = response.json()
    assert Decimal(result['monto']) == Decimal('200802310.64')
    assert not result['evidencia']['apto_aprobacion_contractual']
    saved = await async_client.get('/api/v1/catalogo-apu/estimaciones-parametricas/' + result['id'], headers=headers)
    assert saved.status_code == 200 and saved.json() == result
    junction = await db_session.scalar(select(CatalogoRegistro).where(
        CatalogoRegistro.importacion_id == batch.id, CatalogoRegistro.tabla == 'modelo_parametrico',
        CatalogoRegistro.original['codigo'].as_string() == 'ENTA42C'))
    assert junction.estado == 'CUARENTENA'  # No inferred FIC for a junction.
    assert junction.original['unidad_medida_base'] == 'Entronque'
    assert 'Entronque' not in junction.original['nombre']


def test_duplicate_printed_parametric_codes_remain_two_quarantined_records(tmp_path):
    pdf=tmp_path/'synthetic-duplicates.pdf'
    c=Canvas(str(pdf))
    for number in range(1,43):
        c.setFont('Helvetica',8)
        if number == 2:
            c.drawString(40,710,'TABULADOR DE COSTOS PARAMÉTRICOS 2026')
            c.drawString(40,690,'Aplica a partir del 1 de febrero de 2026')
        if number == 42:
            for y,price in [(640,'$30,000,001'),(600,'$30,000,002')]:
                c.drawString(52,y,'A21A1P');c.drawString(113,y,'CARRETERA ASFÁLTICA synthetic duplicate')
                c.drawString(460,y,'km');c.drawString(508,y,price)
        c.showPage()
    c.save()
    records=extract_source(pdf,'parametricos')
    models=records['modelo_parametrico']
    assert len(models)==2 and len({r['modelo_id'] for r in models})==2
    assert {r['estado_revision'] for r in models}=={'CUARENTENA'}
    assert {r['costo_por_unidad'] for r in models}=={'30000001','30000002'}
    package=tmp_path/'package';write_package(package,records)
    verified=verify_package(package,tmp_path)
    rows,_=prepare(verified,set(verified.verified_source_ids))
    assert {r['estado'] for r in rows if r['tabla']=='modelo_parametrico'}=={'CUARENTENA'}


@pytest.mark.parametrize('title,date_text,error',[
    ('TABULADOR DE SERVICIOS RELACIONADOS CON LA OBRA 2026','Aplica a partir del 1 de julio de 2026','julio'),
    ('TABULADOR DE MAQUINARIA 2026','Aplica a partir del 1 de febrero de 2026','corresponde'),
    ('TABULADOR DE SERVICIOS RELACIONADOS CON LA OBRA 2026','sin fecha verificada','Vigencia'),
])
def test_unverified_source_layout_or_vigencia_is_rejected_before_export(tmp_path,title,date_text,error):
    pdf=tmp_path/'synthetic-preface.pdf';c=Canvas(str(pdf));c.setFont('Helvetica',8)
    c.drawString(40,710,title);c.drawString(40,690,date_text);c.save()
    with pytest.raises(ValueError,match=error):extract_source(pdf,'servicios')


def test_sict_published_net_price_requires_its_direct_cost_and_tax_methodology():
    text='En general a todos los precios cotizados que incluyen el IVA, se les deduce el 16% por concepto de este impuesto. Existen casos especiales, como los combustibles y equipos exentos.'
    records={'fuente':[{'fuente_id':'s','familia':'SICT_DGST_2026','tipo_fuente':'TABULADOR_COSTO_DIRECTO','metadatos':'{"perfil":"maquinaria"}'}],
        'pagina_fuente':[{'fuente_id':'s','pagina_pdf':'9','texto_bruto':text,'texto_sha256':'tax-evidence'},
                         {'fuente_id':'s','pagina_pdf':'7','texto_bruto':'Los costos fueron calculados a Costo Directo.','texto_sha256':'direct-evidence'}]}
    evidence=source_without_vat(records,'s')
    assert evidence['pagina_pdf']=='9' and evidence['pagina_costo_directo']=='7'
    assert evidence['metodo']=='SICT_PRECIO_DIRECTO_PUBLICADO'
    records['fuente'][0]['familia']='OTHER_PUBLISHER'
    assert source_without_vat(records,'s') is None
    records['fuente'][0]['familia']='SICT_DGST_2026';records['pagina_fuente'].pop()
    assert source_without_vat(records,'s') is None


@pytest.mark.parametrize('description, expected', [
    ('CARRETERA con carpeta de CONCRETOHIDRÁULICO', 'CARRETERA_HIDRAULICA'),
    ('CARRETERA con carpeta de CONCRETO HIDRÁULICO', 'CARRETERA_HIDRAULICA'),
    ('CARRETERA con carpeta ASFÁLTICA', 'CARRETERA_ASFALTICA'),
    ('CARRETERA con carpeta ASFÁLTICA y CONCRETO HIDRÁULICO', ''),
    ('PUENTE de concreto hidráulico', ''),
])
def test_sict_road_scope_preserves_pdf_spacing_and_rejects_mixed_material(tmp_path, description, expected):
    pdf = tmp_path / 'synthetic-material.pdf'
    canvas = Canvas(str(pdf))
    for number in range(1, 43):
        canvas.setFont('Helvetica', 8)
        if number == 2:
            canvas.drawString(40, 710, 'TABULADOR DE COSTOS PARAMÉTRICOS 2026')
            canvas.drawString(40, 690, 'Aplica a partir del 1 de febrero de 2026')
        if number == 42:
            canvas.drawString(52, 640, 'A21H1P')
            canvas.drawString(113, 640, description)
            canvas.drawString(460, 640, 'km')
            canvas.drawString(508, 640, '$30,000,001')
        canvas.showPage()
    canvas.save()
    model, = extract_source(pdf, 'parametricos')['modelo_parametrico']
    assert model['nombre_bruto'] == description
    assert json.loads(model['aplicabilidad'])['fic_especialidad'] == expected
    assert model['estado_revision'] == ('VALIDADO_ESTRUCTURAL' if expected else 'REQUIERE_REVISION')


def test_sict_parametric_long_unit_stays_out_of_description():
    # Column coordinates measured on the supplied February PDF, page 98.
    words = [word('ENTA42C', 52, 116.81), word('ENTRONQUE', 126, 116.81),
             word('con', 427.03, 116.81), word('Entronque', 446.47, 116.81),
             word('$8,557,633', 512.38, 116.81)]
    item, = extract_page(words, PROFILES['parametricos'], 98)
    assert item['unit'] == 'Entronque'
    assert item['description'] == 'ENTRONQUE con'
