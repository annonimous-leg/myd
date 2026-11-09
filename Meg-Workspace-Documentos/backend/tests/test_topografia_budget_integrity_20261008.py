"""Source-preserving pricing and integrity at the topography/budget seam."""
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select, func

from app.core.errors import MegalodonException
from app.models.catalogo_apu import CatalogoAPU
from app.models.topografia import CalculoVolumen
from app.services.presupuesto_service import PresupuestoService
from app.services.topografia_service import TopografiaService
from tests.test_topografia_tin_20261008 import surfaces, PARAMS


async def measured_budget(db, tenant, user):
    existing, _ = await surfaces(db, tenant, user)
    topo = TopografiaService(db, tenant.id)
    calc = await topo.calcular_volumen(superficie_existente_id=existing.id, elevacion_referencia=0)
    budget = await topo.generar_partida_movimiento_tierras(calculo_volumen_id=calc.id,
        expediente_id=existing.expediente_id, parametros_costeo=PARAMS, creado_por_id=user.id)
    return existing.expediente_id, budget


def catalog(tenant_id, **kwargs):
    return CatalogoAPU(tenant_id=tenant_id, clave=uuid4().hex, descripcion='Synthetic earthwork price',
        tipo='CONCEPTO', unidad=kwargs.pop('unidad', 'm3'), precio_unitario=kwargs.pop('precio_unitario', 100),
        fuente='TEST_SYNTHETIC', **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize('damage', ['quantity', 'missing_snapshot', 'deleted_line', 'source_digest'])
async def test_tampered_quantities_cannot_be_approved_or_exported(db_session, tenant_a_user, damage):
    tenant, user = tenant_a_user
    exp_id, budget = await measured_budget(db_session, tenant, user)
    item = catalog(tenant.id)
    db_session.add(item)
    await db_session.commit()
    svc = PresupuestoService(db_session, tenant.id)
    budget = await svc.asignar_catalogo_partida(budget.id, exp_id, budget.partidas[0].id, item.id, user.id)
    if damage == 'quantity':
        budget.partidas[0].cantidad = 99
    elif damage == 'missing_snapshot':
        budget.metadatos = {k: v for k, v in budget.metadatos.items() if k != 'topografia_evidencia'}
    elif damage == 'deleted_line':
        await db_session.delete(budget.partidas[0])
    else:
        budget.partidas[0].metadatos = {**budget.partidas[0].metadatos, 'topografia': {
            **budget.partidas[0].metadatos['topografia'], 'evidencia_sha256': 'invalid'}}
    await db_session.commit()
    with pytest.raises(MegalodonException):
        await svc.cambiar_estado(budget.id, exp_id, 'VALIDADO')
    for operation in [svc.generar_excel, svc.generar_pdf]:
        with pytest.raises(MegalodonException, match='evidencia topográfica'):
            await operation(budget.id, exp_id)


@pytest.mark.asyncio
@pytest.mark.parametrize('reference', [0.00005, -0.00005])
async def test_reference_precision_is_rejected_before_numeric_storage_rounds_it(db_session, tenant_a_user, reference):
    tenant, user = tenant_a_user
    existing, _ = await surfaces(db_session, tenant, user)
    with pytest.raises(MegalodonException, match='cuatro decimales'):
        await TopografiaService(db_session, tenant.id).calcular_volumen(
            superficie_existente_id=existing.id, elevacion_referencia=reference)
    assert await db_session.scalar(select(func.count()).select_from(CalculoVolumen).where(
        CalculoVolumen.superficie_existente_id == existing.id)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('invalid', ['unit', 'tax', 'foreign', 'zero', 'desglose'])
async def test_price_binding_rejects_incompatible_or_unreviewed_catalogs(db_session, tenant_a_user, tenant_b_user, invalid):
    tenant, user = tenant_a_user
    exp_id, budget = await measured_budget(db_session, tenant, user)
    kwargs = {'unit': {'unidad':'m2'}, 'tax': {'incluye_iva':True}, 'zero': {'precio_unitario':0},
              'desglose': {'desglose':{'insumos':[{'cantidad':-1, 'precio_unitario':100}]}}}.get(invalid, {})
    item = catalog(tenant_b_user[0].id if invalid == 'foreign' else tenant.id, **kwargs)
    db_session.add(item)
    await db_session.commit()
    qty, source = budget.partidas[0].cantidad, dict(budget.partidas[0].metadatos)
    with pytest.raises(MegalodonException):
        await PresupuestoService(db_session, tenant.id).asignar_catalogo_partida(
            budget.id, exp_id, budget.partidas[0].id, item.id, user.id)
    assert budget.partidas[0].cantidad == qty
    assert budget.partidas[0].metadatos == source
    assert budget.partidas[0].precio_unitario == 0


@pytest.mark.asyncio
async def test_catalog_apu_binding_preserves_measured_quantity_and_observed_source(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    exp_id, budget = await measured_budget(db_session, tenant, user)
    item = catalog(tenant.id, desglose={'insumos':[
        {'clave':'MAT','descripcion':'Synthetic material','unidad':'kg','cantidad':2,'precio_unitario':10},
        {'clave':'LAB','descripcion':'Synthetic labor','tipo':'MANO_OBRA','unidad':'h','cantidad':1,'precio_unitario':30}]})
    db_session.add(item)
    await db_session.commit()
    quantity, origin, part_id = budget.partidas[0].cantidad, dict(budget.partidas[0].metadatos['topografia']), budget.partidas[0].id
    svc = PresupuestoService(db_session, tenant.id)
    budget = await svc.asignar_catalogo_partida(budget.id, exp_id, part_id, item.id, user.id)
    part = budget.partidas[0]
    assert part.id == part_id and part.cantidad == quantity
    assert part.metadatos['topografia'] == origin
    assert part.precio_unitario == Decimal('50.00')
    assert len(part.conceptos) == 1 and len(part.conceptos[0].insumos) == 2
    assert part.metadatos['catalogo_asignado']['precio_observado'].startswith('100')
    assert part.metadatos['catalogo_asignado']['precio_aplicado'] == '50.00'
    # Subsequent source catalogue edits never reprice a saved revision silently.
    item.precio_unitario = 999
    item.desglose = None
    await db_session.commit()
    budget = await svc.recalcular(budget.id, exp_id)
    assert budget.partidas[0].precio_unitario == Decimal('50.00')
    await svc.cambiar_estado(budget.id, exp_id, 'VALIDADO')
    with pytest.raises(MegalodonException, match='revisión'):
        await svc.asignar_catalogo_partida(budget.id, exp_id, part_id, item.id, user.id)


@pytest.mark.asyncio
async def test_price_binding_route_preserves_origin_and_rejects_reader(async_client, auth_headers, db_session, tenant_a_user):
    from app.models.user import UserRole
    tenant, user = tenant_a_user
    exp_id, budget = await measured_budget(db_session, tenant, user)
    item = catalog(tenant.id)
    db_session.add(item)
    await db_session.commit()
    part_id = budget.partidas[0].id
    route = f'/api/v1/presupuestos/{exp_id}/presupuestos/{budget.id}/partidas/{part_id}/catalogo'
    response = await async_client.put(route, headers=auth_headers, json={'catalogo_apu_id':str(item.id)})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['partidas'][0]['id'] == str(part_id)
    assert result['partidas'][0]['metadatos']['topografia'] == budget.partidas[0].metadatos['topografia']
    assert result['partidas'][0]['metadatos']['catalogo_asignado']['catalogo_id'] == str(item.id)
    user.role = UserRole.LECTOR
    await db_session.commit()
    denied = await async_client.put(route, headers=auth_headers, json={'catalogo_apu_id':str(item.id)})
    assert denied.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize('damage', ['price', 'snapshot', 'missing', 'insumo'])
async def test_assigned_price_evidence_cannot_silently_diverge(db_session, tenant_a_user, damage):
    tenant, user = tenant_a_user
    exp_id, budget = await measured_budget(db_session, tenant, user)
    kwargs = {'desglose': {'insumos': [{'clave':'I','descripcion':'Synthetic','unidad':'kg',
        'cantidad':1,'precio_unitario':100}]}} if damage == 'insumo' else {}
    item = catalog(tenant.id, **kwargs)
    db_session.add(item)
    await db_session.commit()
    svc = PresupuestoService(db_session, tenant.id)
    budget = await svc.asignar_catalogo_partida(budget.id, exp_id, budget.partidas[0].id, item.id, user.id)
    part = budget.partidas[0]
    if damage == 'price':
        part.precio_unitario = 150
    elif damage == 'insumo':
        part.conceptos[0].insumos[0].cantidad = 2
    elif damage == 'missing':
        part.metadatos = {'topografia':part.metadatos['topografia']}
    else:
        part.metadatos = {**part.metadatos, 'catalogo_asignado':{
            **part.metadatos['catalogo_asignado'], 'fuente':'Different source'}}
    await db_session.commit()
    for operation in [svc.recalcular, svc.generar_excel, svc.generar_pdf]:
        with pytest.raises(MegalodonException, match='catálogo asignado'):
            await operation(budget.id, exp_id)
    with pytest.raises(MegalodonException, match='catálogo asignado'):
        await svc.cambiar_estado(budget.id, exp_id, 'VALIDADO')
