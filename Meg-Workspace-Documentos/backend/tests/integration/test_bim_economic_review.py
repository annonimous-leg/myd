"""A mesh-derived estimate is not an approved economic measurement."""
from decimal import Decimal
from uuid import uuid4

import pytest

from app.models.bim import ElementoBIM
from app.models.catalogo_apu import CatalogoAPU
from app.services.bim_service import BIMService
from tests.integration.test_bim_regressions import model, PARAMS


@pytest.mark.asyncio
async def test_geometric_volume_needs_review_and_preserves_original(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    exp, obj = await model(db_session, tenant, user)
    element = ElementoBIM(modelo_id=obj.id, global_id=uuid4().hex, express_id=1,
                          tipo='IfcBeam', volumen=2, fuente_volumen='GEOMETRIA_CALCULADA')
    apu = CatalogoAPU(tenant_id=tenant.id, clave='GEOM-REVIEW', descripcion='Revisión sintética',
                     tipo='CONCEPTO', unidad='m3', precio_unitario=100, fuente='TEST_SYNTHETIC')
    db_session.add_all([element, apu])
    await db_session.commit()
    service = BIMService(db_session, tenant.id)
    options = dict(modelo_id=obj.id, expediente_id=exp.id, parametros_costeo=PARAMS,
                   mapeo_catalogo={'IfcBeam': apu.id}, creado_por_id=user.id)
    draft = await service.crear_presupuesto_desde_bim(**options)
    assert draft.estado == 'BORRADOR'
    assert draft.monto_total == Decimal('0.00')
    assert draft.metadatos['bim_cobertura']['volumenes_geometricos_pendientes'] == [str(element.id)]

    reviewed = await service.crear_presupuesto_desde_bim(**options, cantidades_complementarias=[{
        'elemento_id': element.id, 'unidad': 'm3', 'cantidad': 2.25,
        'referencia': 'Memoria independiente revisada, sección B-01',
    }])
    assert reviewed.monto_total == Decimal('225.00')
    assert reviewed.metadatos['bim_cobertura']['completa'] is True
    capture = reviewed.metadatos['bim_cobertura']['capturas'][0]
    assert capture['fuente_original'] == 'GEOMETRIA_CALCULADA'
    assert capture['cantidad_original'] == 2
    assert capture['usuario_id'] == str(user.id)
    assert element.volumen == 2
    assert element.fuente_volumen == 'GEOMETRIA_CALCULADA'
    from datetime import datetime, timezone
    from sqlalchemy import select
    from app.models.programacion import ActividadPrograma
    program = await service.generar_actividades_4d(
        modelo_id=obj.id, expediente_id=exp.id, fecha_inicio=datetime(2026, 11, 11, tzinfo=timezone.utc),
        dias_por_defecto=5, creado_por_id=user.id, tenant_id=tenant.id)
    activities = (await db_session.scalars(select(ActividadPrograma).where(
        ActividadPrograma.programa_id == program.id))).all()
    assert sum(a.costo_presupuestado for a in activities) == Decimal('225.00')


@pytest.mark.asyncio
async def test_parent_and_child_cannot_both_be_charged_even_with_different_apus(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    exp, obj = await model(db_session, tenant, user)
    parent_guid, child_guid = uuid4().hex, uuid4().hex
    parent = ElementoBIM(modelo_id=obj.id, global_id=parent_guid, express_id=1, tipo='IfcRoof',
                         volumen=2, fuente_volumen='QTO_IFC',
                         propiedades={'_componentes_geometria': [child_guid]})
    child = ElementoBIM(modelo_id=obj.id, global_id=child_guid, express_id=2, tipo='IfcSlab',
                        volumen=2, fuente_volumen='QTO_IFC')
    apus = [CatalogoAPU(tenant_id=tenant.id, clave='PARENT-'+str(i), descripcion='Sintético',
                       tipo='CONCEPTO', unidad='m3', precio_unitario=100, fuente='TEST_SYNTHETIC')
            for i in range(2)]
    db_session.add_all([parent, child, *apus])
    await db_session.commit()
    budget = await BIMService(db_session, tenant.id).crear_presupuesto_desde_bim(
        modelo_id=obj.id, expediente_id=exp.id, parametros_costeo=PARAMS,
        mapeo_catalogo={'IfcRoof': apus[0].id, 'IfcSlab': apus[1].id}, creado_por_id=user.id)
    assert budget.estado == 'BORRADOR'
    assert budget.monto_total == Decimal('0.00')
    evidence = budget.metadatos['bim_cobertura']
    assert set(evidence['elementos_pendientes']) == {str(parent.id), str(child.id)}
    assert evidence['conflictos_conjuntos'] == [{
        'padre_global_id': parent_guid, 'componente_global_id': child_guid,
    }]
    assert evidence['reglas_candidatas_conjuntos'][0]['sustento_contractual'] is None
    assert evidence['reglas_candidatas_conjuntos'][0]['estado'] == 'PENDIENTE_DE_APROBACION_ECONOMICA'
