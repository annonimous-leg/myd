"""Economic versions: immutable acceptance, independent nested revisions and valid bases."""
from copy import deepcopy
from decimal import Decimal
from uuid import UUID

import pytest

from app.core.errors import MegalodonException
from app.models.presupuesto import Presupuesto
from app.services.presupuesto_service import PresupuestoService
from tests.conftest import _login
from tests.integration.test_closure_two_tenants import make_expediente
from tests.integration.test_sict_catalogo import enable_disposable_catalog_acceptance_plan

PARAMS = dict(factor_indirecto=0, factor_utilidad=0, factor_impuesto=0,
              factor_riesgo=0, fuente='CAPTURA_USUARIO', referencia='Fixture: sin recargos')


@pytest.mark.asyncio
async def test_approved_nested_budget_revision_is_independent(async_client, db_session, tenant_a_user):
    tenant, user = tenant_a_user
    user.role = 'revisor'
    exp = make_expediente(tenant, user)
    db_session.add(exp)
    await enable_disposable_catalog_acceptance_plan(db_session, tenant)
    await db_session.commit()
    headers = await _login(async_client, user.email)
    base = f'/api/v1/presupuestos/{exp.id}/presupuestos'
    result = await async_client.post(base, headers=headers, json={
        'nombre': 'APU verificable', 'parametros_costeo': PARAMS, 'partidas': [{
            'numero': 1, 'descripcion': 'Muro', 'unidad': 'm2', 'cantidad': 2,
            'conceptos': [{'clave': 'M1', 'descripcion': 'Material', 'unidad': 'm2', 'cantidad': 1,
                'insumos': [{'clave': 'I1', 'descripcion': 'Pieza', 'tipo': 'MATERIAL',
                    'unidad': 'pza', 'cantidad': 3, 'precio_unitario': 10, 'rendimiento': 1}]}],
        }],
    })
    assert result.status_code == 200, result.text
    original = result.json()
    url = f'{base}/{original["id"]}'
    for state in ['CALCULADO', 'VALIDADO', 'APROBADO']:
        if original['estado'] == state:
            continue
        result = await async_client.patch(url+'/estado', headers=headers, json={'estado': state})
        assert result.status_code == 200, result.text
        original = result.json()
        if state == 'VALIDADO':
            blocked = await async_client.post(url+'/recalcular', headers=headers)
            assert blocked.status_code == 409
    original = deepcopy(original)
    part_id = original['partidas'][0]['id']
    assert original['monto_total'] == 60
    for method, suffix, body in [
        ('post', '/recalcular', None),
        ('patch', f'/partidas/{part_id}', {'cantidad': 9}),
        ('delete', f'/partidas/{part_id}', None),
        ('put', '/parametros-costeo', {'parametros_costeo': PARAMS}),
    ]:
        response = await async_client.request(method, url+suffix, headers=headers, json=body)
        assert response.status_code == 409, response.text
    result = await async_client.post(url+'/revisiones', headers=headers, json={'motivo': 'Nueva cantidad medida'})
    assert result.status_code == 201, result.text
    revision = result.json()
    assert revision['estado'] == 'BORRADOR'
    assert revision['metadatos']['revision']['presupuesto_origen_id'] == original['id']
    rp, op = revision['partidas'][0], original['partidas'][0]
    assert rp['id'] != op['id']
    assert rp['conceptos'][0]['id'] != op['conceptos'][0]['id']
    assert rp['conceptos'][0]['insumos'][0]['id'] != op['conceptos'][0]['insumos'][0]['id']
    result = await async_client.patch(f'{base}/{revision["id"]}/partidas/{rp["id"]}',
                                     headers=headers, json={'cantidad': 3})
    assert result.status_code == 200, result.text
    assert result.json()['monto_total'] == 90
    saved = (await async_client.get(base, headers=headers)).json()
    assert next(x for x in saved if x['id'] == original['id']) == original
    edited = next(x for x in saved if x['id'] == revision['id'])
    assert edited['partidas'][0]['conceptos'][0]['insumos'][0]['precio_unitario'] == 10
    assert edited['estado'] == 'CALCULADO'
    service = PresupuestoService(db_session, tenant.id)
    comparison = await service.validar_sobrecostos(UUID(revision['id']), exp.id, UUID(original['id']))
    assert comparison['factor_sobrecosto'] == .5
    assert not comparison['dentro_tolerancia']


@pytest.mark.asyncio
async def test_zero_and_unrelated_bases_are_not_financial_comparisons(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    exp, other = make_expediente(tenant, user), make_expediente(tenant, user)
    db_session.add_all([exp, other])
    await db_session.flush()
    def budget(expediente, code, total):
        return Presupuesto(tenant_id=tenant.id, expediente_id=expediente.id, identificador=code,
            nombre=code, monto_total=Decimal(total), factor_indirecto=0, factor_utilidad=0, factor_impuesto=0)
    actual, zero, unrelated = budget(exp, 'A', '100'), budget(exp, 'Z', '0'), budget(other, 'O', '100')
    db_session.add_all([actual, zero, unrelated])
    await db_session.commit()
    service = PresupuestoService(db_session, tenant.id)
    with pytest.raises(MegalodonException, match='Comparación no calculable'):
        await service.validar_sobrecostos(actual.id, exp.id, zero.id)
    with pytest.raises(MegalodonException, match='Presupuesto no encontrado'):
        await service.validar_sobrecostos(actual.id, exp.id, unrelated.id)
    with pytest.raises(MegalodonException, match='Presupuesto no encontrado'):
        await service.validar_sobrecostos(unrelated.id, exp.id, actual.id)
