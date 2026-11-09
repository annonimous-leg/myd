"""Acceptance of the shared policy using disposable persisted actors."""
from importlib import import_module
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.authorization import authorize_by_id
from app.core.deps import require_mutation_access
from app.core.errors import MegalodonException
from app.models.expediente import EstadoExpediente, ExpedienteObra
from app.models.user import UserRole
from app.modules.expedientes.service import ExpedienteModuleService
from app.services.catalogo_apu_service import CatalogoAPUService
from app.services.expediente_service import ExpedienteService
from tests.conftest import _login
from tests.integration.test_closure_two_tenants import make_expediente


@pytest.mark.parametrize('role,write,approve', [
    ('superadmin', True, True), ('admin', True, True), ('revisor', True, True),
    ('tecnico', True, False), ('lector', False, False), ('invitado', False, False),
])
@pytest.mark.asyncio
async def test_persisted_actor_policy(db_session, tenant_a_user, role, write, approve):
    tenant, user = tenant_a_user
    user.role = role
    await db_session.commit()
    for action, allowed in [('write', write), ('approve', approve), ('undefined-action', False)]:
        if allowed:
            assert await authorize_by_id(db_session, user.id, tenant.id, action) is user
        else:
            with pytest.raises(MegalodonException) as denied:
                await authorize_by_id(db_session, user.id, tenant.id, action)
            assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_actor_scope_and_activity_are_required(db_session, tenant_a_user, tenant_b_user):
    tenant, user = tenant_a_user
    for actor_id, tenant_id in [(None, tenant.id), (user.id, None), (user.id, tenant_b_user[0].id)]:
        with pytest.raises(MegalodonException) as denied:
            await authorize_by_id(db_session, actor_id, tenant_id)
        assert denied.value.status_code == 403
    tenant.is_active = False
    await db_session.commit()
    with pytest.raises(MegalodonException) as denied:
        await authorize_by_id(db_session, user.id, tenant.id)
    assert denied.value.status_code == 403


@pytest.mark.parametrize('module', [
    'expedientes', 'expedientes_advanced', 'licitaciones', 'licitaciones_obra',
    'contratos', 'catalogo_apu', 'programacion',
])
def test_all_mutation_adapters_declare_the_shared_policy(module):
    router = import_module('app.api.v1.' + module).router
    for route in router.routes:
        if route.methods - {'GET', 'HEAD', 'OPTIONS'}:
            assert any(d.call is require_mutation_access for d in route.dependant.dependencies), route.path


@pytest.mark.parametrize('role', ['lector', 'invitado'])
@pytest.mark.asyncio
async def test_read_only_roles_keep_read_access_and_commands_are_denied(
    async_client, db_session, tenant_a_user, role
):
    tenant, user = tenant_a_user
    user.role = role
    exp = make_expediente(tenant, user)
    db_session.add(exp)
    await db_session.commit()
    headers = await _login(async_client, user.email)
    response = await async_client.get(f'/api/v1/expedientes/{exp.id}', headers=headers)
    assert response.status_code == 200
    commands = [
        ('post', '/api/v1/catalogo-apu', 403),
        # Authority-side licitation and contract endpoints are deliberately
        # unmounted in the bidder workspace; their absence is a product boundary.
        ('post', '/api/v1/licitaciones', 404),
        ('post', '/api/v1/contratos', 404),
        ('post', f'/api/v1/programacion/{exp.id}/programas', 403),
        ('post', f'/api/v1/licitaciones-obra/expediente/{exp.id}/planeacion', 404),
        ('post', f'/api/v1/expedientes-advanced/{exp.id}/cambiar-estado', 403),
        ('patch', f'/api/v1/expedientes/{exp.id}/estado', 403),
    ]
    for method, url, expected_status in commands:
        response = await async_client.request(method, url, headers=headers, json={})
        assert response.status_code == expected_status, (url, response.text)
    with pytest.raises(MegalodonException) as denied:
        await CatalogoAPUService().eliminar(db_session, uuid4(), user)
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_expediente_adapters_share_states_history_and_closing_authority(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    exp = make_expediente(tenant, user)
    db_session.add(exp)
    await db_session.commit()
    standard = ExpedienteService(db_session, tenant.id)
    advanced = ExpedienteModuleService(db_session, tenant.id)
    await standard.cambiar_estado(exp.id, EstadoExpediente.EN_TRAMITE, tenant.id,
                                  actualizado_por_id=user.id)
    await advanced.cambiar_estado_expediente(exp.id, EstadoExpediente.EN_FIRMA,
                                             actualizado_por_id=user.id, motivo='Listo para firma')
    with pytest.raises(MegalodonException) as denied:
        await advanced.cambiar_estado_expediente(exp.id, EstadoExpediente.CERRADO,
                                                 actualizado_por_id=user.id)
    assert denied.value.status_code == 403
    user.role = UserRole.REVISOR
    await db_session.commit()
    result = await advanced.cambiar_estado_expediente(exp.id, EstadoExpediente.CERRADO,
                                                     actualizado_por_id=user.id, motivo='Firma concluida')
    assert result.estado == EstadoExpediente.CERRADO
    saved = await db_session.scalar(select(ExpedienteObra).where(ExpedienteObra.id == exp.id))
    history = saved.metadatos['historial_estados']
    assert [h['estado_nuevo'] for h in history] == ['EN_TRAMITE', 'EN_FIRMA', 'CERRADO']
    assert all(h['actor_id'] == str(user.id) for h in history)
