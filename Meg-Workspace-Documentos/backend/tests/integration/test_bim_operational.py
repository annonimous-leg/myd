from pathlib import Path
from uuid import uuid4
import pytest
from app.services.bim_service import BIMService
from app.services.bim_operational import BIMOperationalService
from app.models.bim_revision import RevisionBIM
from app.core.errors import MegalodonException
from tests.integration.test_bim_regressions import model, PARAMS


@pytest.mark.asyncio
async def test_coverage_persists_per_revision_and_failed_processing_keeps_snapshot(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    exp, obj = await model(db_session, tenant, user)
    content = (Path(__file__).parents[1] / 'fixtures/ifc/wall_millimetres.ifc').read_bytes()
    service = BIMService(db_session, tenant.id)
    await service.procesar_ifc(modelo_id=obj.id, file_content=content)
    first = obj.revision_actual_id
    assert first is not None
    snapshot = await db_session.get(RevisionBIM, first)
    assert len(snapshot.cobertura) == 1
    assert snapshot.cobertura[0]['estado_cobertura'] == 'ADMITIDO'
    await service.procesar_ifc(modelo_id=obj.id, file_content=content)
    assert obj.revision_actual_id == first  # A retry of identical content is not a new design.
    with pytest.raises(MegalodonException):
        await service.procesar_ifc(modelo_id=obj.id, file_content=b'invalid')
    await db_session.refresh(obj)
    assert obj.revision_actual_id == first


@pytest.mark.asyncio
async def test_draft_never_resolves_economics_and_foreign_revision_is_rejected(db_session, tenant_a_user, tenant_b_user):
    tenant, user = tenant_a_user
    exp, obj = await model(db_session, tenant, user)
    content = (Path(__file__).parents[1] / 'fixtures/ifc/wall_millimetres.ifc').read_bytes()
    await BIMService(db_session, tenant.id).procesar_ifc(modelo_id=obj.id, file_content=content)
    revision = await db_session.get(RevisionBIM, obj.revision_actual_id)
    ops = BIMOperationalService(db_session, tenant.id)
    decision = await ops.guardar_decision(obj.id, exp.id, user.id, {
        'revision_id': revision.id, 'familia_global_id': revision.cobertura[0]['global_id'],
        'criterio': 'PADRE', 'confirmar': False, 'lineas': [],
        'referencia_contractual': '', 'documento_id': None,
    })
    assert decision.confirmada is False
    with pytest.raises(MegalodonException, match='confirmadas'):
        await ops.crear_presupuesto(obj.id, exp.id, user.id, [decision.id], PARAMS)
    with pytest.raises(MegalodonException, match='no encontrado'):
        await BIMOperationalService(db_session, tenant_b_user[0].id).cobertura(obj.id, exp.id)


@pytest.mark.asyncio
async def test_confirmed_measurement_creates_budget_and_changes_invalidate_without_mutating_history(db_session, tenant_a_user):
    from app.models.expediente import Documento
    from app.models.catalogo_apu import CatalogoAPU
    from app.services.presupuesto_service import PresupuestoService
    from decimal import Decimal
    tenant, user = tenant_a_user
    exp, obj = await model(db_session, tenant, user)
    content = (Path(__file__).parents[1] / 'fixtures/ifc/wall_millimetres.ifc').read_bytes()
    await BIMService(db_session, tenant.id).procesar_ifc(modelo_id=obj.id, file_content=content)
    revision = await db_session.get(RevisionBIM, obj.revision_actual_id)
    apu = CatalogoAPU(tenant_id=tenant.id, clave=uuid4().hex, descripcion='Contrato sintético, muro',
        tipo='CONCEPTO', unidad='m3', precio_unitario=125, fuente='TEST_SYNTHETIC')
    steel = CatalogoAPU(tenant_id=tenant.id, clave=uuid4().hex, descripcion='Concepto separado sintético',
        tipo='CONCEPTO', unidad='kg', precio_unitario=5, fuente='TEST_SYNTHETIC')
    document = Documento(expediente_id=exp.id, identificador=uuid4().hex, nombre='Contrato sintético',
        tipo_documental='CONTRATO', formato='pdf', storage_path='synthetic.pdf', storage_bucket='test',
        size_bytes=100, hash_sha256='a'*64)
    db_session.add_all([apu, steel, document]); await db_session.commit()
    ops = BIMOperationalService(db_session, tenant.id)
    payload = {'revision_id': revision.id, 'familia_global_id': revision.cobertura[0]['global_id'],
        'criterio': 'PADRE', 'confirmar': True, 'documento_id': document.id,
        'referencia_contractual': 'Cláusula 3 de medición y pago del contrato sintético',
        'lineas': [{'global_id': revision.cobertura[0]['global_id'], 'catalogo_apu_id': apu.id,
                'cantidad': '2.4', 'referencia_medicion': '2 × 0.4 × 3 metros', 'alcance': 'Volumen de concreto'},
            {'global_id': revision.cobertura[0]['global_id'], 'catalogo_apu_id': steel.id,
                'cantidad': '10', 'referencia_medicion': 'Lista de acero sintética', 'alcance': 'Acero medido por separado'}]}
    decision = await ops.guardar_decision(obj.id, exp.id, user.id, payload)
    budget = await ops.crear_presupuesto(obj.id, exp.id, user.id, [decision.id], PARAMS)
    assert budget.monto_total == Decimal('350.00')
    assert budget.metadatos['bim_cobertura']['completa'] is True
    assert not await ops.presupuesto_obsoleto(budget)
    from datetime import datetime, timezone
    from sqlalchemy import select
    from app.models.programacion import ActividadPrograma
    program = await BIMService(db_session, tenant.id).generar_actividades_4d(
        modelo_id=obj.id, expediente_id=exp.id, fecha_inicio=datetime(2026,11,11,tzinfo=timezone.utc),
        creado_por_id=user.id, tenant_id=tenant.id)
    activities = (await db_session.scalars(select(ActividadPrograma).where(ActividadPrograma.programa_id==program.id))).all()
    assert sum(a.costo_presupuestado for a in activities) == Decimal('350.00')
    await ops.guardar_decision(obj.id,exp.id,user.id,{
        'revision_id':revision.id,'familia_global_id':decision.familia_global_id,
        'criterio':'PADRE','confirmar':False,'lineas':[]})
    assert (await ops.estado_decision(decision))['estado'] == 'VIGENTE'
    assert not await ops.presupuesto_obsoleto(budget)
    original = decision.datos.copy()
    apu.precio_unitario = 140
    await db_session.commit()
    assert 'CAMBIO_CONCEPTO_O_PRECIO' in (await ops.estado_decision(decision))['causas']
    assert await ops.presupuesto_obsoleto(budget)
    with pytest.raises(MegalodonException):
        await PresupuestoService(db_session, tenant.id).cambiar_estado(budget.id, exp.id, 'VALIDADO')
    assert decision.datos == original
    apu.precio_unitario = 125
    document.hash_sha256 = 'b'*64
    await db_session.commit()
    assert 'CAMBIO_SUSTENTO_CONTRACTUAL' in (await ops.estado_decision(decision))['causas']
    await BIMService(db_session, tenant.id).procesar_ifc(modelo_id=obj.id, file_content=content+b'\n')
    assert 'CAMBIO_REVISION_MODELO' in (await ops.estado_decision(decision))['causas']
    historical = await ops.cobertura(obj.id, exp.id, revision.id)
    assert historical['actual'] is False
    assert len(historical['items']) == 1


@pytest.mark.asyncio
async def test_postgres_rejects_rewriting_coverage_history(db_session, tenant_a_user):
    if db_session.bind.dialect.name != 'postgresql':
        pytest.skip('Immutable snapshot trigger requires PostgreSQL')
    from sqlalchemy import update
    from sqlalchemy.exc import DBAPIError
    tenant, user = tenant_a_user
    exp, obj = await model(db_session, tenant, user)
    content = (Path(__file__).parents[1] / 'fixtures/ifc/wall_millimetres.ifc').read_bytes()
    await BIMService(db_session, tenant.id).procesar_ifc(modelo_id=obj.id,file_content=content)
    with pytest.raises(DBAPIError, match='immutable'):
        async with db_session.begin_nested():
            await db_session.execute(update(RevisionBIM).where(RevisionBIM.id==obj.revision_actual_id).values(cobertura=[]))


@pytest.mark.asyncio
async def test_incremental_types_preserve_coverage_and_component_policy_cannot_pay_ancestors(db_session, tenant_a_user):
    import ifcopenshell
    from app.engines.bim.motor_bim import TIPOS_DEFAULT
    tenant, user = tenant_a_user
    exp, obj = await model(db_session, tenant, user)
    source = ifcopenshell.open(str(Path(__file__).parents[1] / 'fixtures/ifc/wall_millimetres.ifc'))
    wall = source.by_type('IfcWall')[0]
    member = source.create_entity('IfcMember', GlobalId=ifcopenshell.guid.new(), Representation=wall.Representation)
    plate = source.create_entity('IfcPlate', GlobalId=ifcopenshell.guid.new(), Representation=wall.Representation)
    roof = source.create_entity('IfcRoof', GlobalId=ifcopenshell.guid.new())
    source.create_entity('IfcRelAggregates', GlobalId=ifcopenshell.guid.new(), RelatingObject=roof, RelatedObjects=[wall,member,plate])
    content = source.to_string().encode()
    bim = BIMService(db_session, tenant.id)
    await bim.procesar_ifc(modelo_id=obj.id, file_content=content)
    first = obj.revision_actual_id
    await bim.procesar_ifc(modelo_id=obj.id, file_content=content, tipos_elementos=TIPOS_DEFAULT+['IfcMember','IfcPlate'])
    assert obj.num_elementos == 4
    assert obj.revision_actual_id != first
    ops = BIMOperationalService(db_session, tenant.id)
    historical = await ops.cobertura(obj.id, exp.id, first)
    current = await ops.cobertura(obj.id, exp.id)
    assert historical['resumen']['ADMITIDO'] == 2
    assert current['resumen']['ADMITIDO'] == 4
    with pytest.raises(MegalodonException, match='contradice'):
        await ops.guardar_decision(obj.id,exp.id,user.id,{'revision_id':obj.revision_actual_id,
            'familia_global_id':roof.GlobalId,'criterio':'COMPONENTES','confirmar':False,
            'lineas':[{'global_id':roof.GlobalId,'cantidad':'1','referencia_medicion':'Prueba de medición','alcance':'No pagar el padre'}]})
