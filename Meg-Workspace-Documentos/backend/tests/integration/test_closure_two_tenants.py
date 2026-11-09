import pytest
from uuid import uuid4
from sqlalchemy import select

from app.models.expediente import ExpedienteObra
from app.models.procurement import TenderPackage
from app.services.procurement.workspace import TenderWorkspaceService
from app.core.errors import MegalodonException

from tests.conftest import _login


def make_expediente(tenant, user):
    return ExpedienteObra(
        tenant_id=tenant.id, responsable_id=user.id,
        identificador=f"EXP-{uuid4().hex[:8]}", titulo="Obra E2E", descripcion="Prueba",
        organo="Dependencia", unidad_administrativa="UA", serie_documental="OBRA",
        subserie_documental="LICITACION", proyecto_nombre="Proyecto E2E",
    )

@pytest.mark.asyncio
async def test_workspace_documents_and_cross_tenant_http(async_client, db_session, tenant_a_user, tenant_b_user):
    tenant_a, user_a = tenant_a_user
    tenant_b, user_b = tenant_b_user
    exp_a, exp_b = make_expediente(tenant_a, user_a), make_expediente(tenant_b, user_b)
    db_session.add_all([exp_a, exp_b]); await db_session.flush()
    tender_a = TenderPackage(tenant_id=tenant_a.id, expediente_id=exp_a.id, identifier="TP-A", title="Tender A", jurisdiction_code="MX-FED-OBRA", current_revision=1)
    tender_b = TenderPackage(tenant_id=tenant_b.id, expediente_id=exp_b.id, identifier="TP-B", title="Tender B", jurisdiction_code="MX-FED-OBRA", current_revision=1)
    db_session.add_all([tender_a, tender_b]); await db_session.commit(); await db_session.refresh(tender_a); await db_session.refresh(tender_b)

    svc_a = TenderWorkspaceService(db_session, user_a)
    doc_a = await svc_a.open_or_create(tender_a.id, "AT-01", "Documento A")
    edited = await svc_a.update_document(tender_a.id, doc_a.id, content_text="A EDITADO", content_model={}, expected_row_version=doc_a.row_version)
    assert edited.human_modified is True and edited.version == 2
    headers_a = await _login(async_client, user_a.email)
    headers_b = await _login(async_client, user_b.email)
    assert (await async_client.get(f"/api/v1/procurement/tenders/{tender_b.id}", headers=headers_a)).status_code in (403, 404)
    assert (await async_client.get(f"/api/v1/procurement/tenders/{tender_a.id}/workspace/documents/{doc_a.id}", headers=headers_b)).status_code in (403, 404)

@pytest.mark.asyncio
async def test_workspace_rejects_stale_write_and_destructive_regeneration(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    exp = make_expediente(tenant, user); db_session.add(exp); await db_session.flush()
    tender = TenderPackage(tenant_id=tenant.id, expediente_id=exp.id, identifier=f"TP-{uuid4().hex[:8]}", title="Tender", jurisdiction_code="MX-FED-OBRA", current_revision=1)
    db_session.add(tender); await db_session.commit(); await db_session.refresh(tender)
    svc = TenderWorkspaceService(db_session, user)
    doc = await svc.open_or_create(tender.id, "AT-02", "Documento")
    v = doc.row_version
    doc = await svc.update_document(tender.id, doc.id, content_text="humano", content_model={}, expected_row_version=v)
    with pytest.raises(MegalodonException) as exc:
        await svc.update_document(tender.id, doc.id, content_text="stale", content_model={}, expected_row_version=v)
    assert exc.value.status_code == 409
    with pytest.raises(MegalodonException) as exc:
        await svc.regenerate(tender.id, doc.id, generated_text="GENERADO", generated_model={}, expected_row_version=doc.row_version)
    assert exc.value.status_code == 409
    refreshed = await svc.get_document(tender.id, doc.id)
    assert refreshed.content_text == "humano"
    assert refreshed.last_conflict is not None

@pytest.mark.asyncio
async def test_service_layer_isolation_bim_budget_schedule_topography_montecarlo(db_session, tenant_a_user, tenant_b_user):
    """Defense-in-depth: bypass HTTP and invoke domain services directly.

    A router dependency is not allowed to be the only security boundary.
    This test deliberately supplies B's UUIDs to A's services.
    """
    from app.models.bim import ModeloBIM
    from app.models.presupuesto import Presupuesto
    from app.models.programacion import ProgramaObra
    from app.models.topografia import Levantamiento
    from app.models.montecarlo import MonteCarloRun, EstadoMonteCarlo
    from app.services.bim_service import BIMService
    from app.services.presupuesto_service import PresupuestoService
    from app.services.programacion_service import ProgramacionService
    from app.services.topografia_service import TopografiaService
    from app.services.montecarlo_service import MonteCarloService

    tenant_a, user_a = tenant_a_user
    tenant_b, user_b = tenant_b_user
    exp_a, exp_b = make_expediente(tenant_a, user_a), make_expediente(tenant_b, user_b)
    db_session.add_all([exp_a, exp_b]); await db_session.flush()

    from decimal import Decimal
    from app.engines.costos.parametros import FuenteParametrosCosteo, ParametrosCosteoSnapshot

    def budget(expediente, tenant, prefix, nombre):
        parametros = ParametrosCosteoSnapshot(
            Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"),
            FuenteParametrosCosteo.CAPTURA_USUARIO,
            "Fixture de aislamiento multi-tenant",
        )
        return Presupuesto(
            tenant_id=tenant.id, expediente_id=expediente.id,
            identificador=f"{prefix}-{uuid4().hex[:8]}", nombre=nombre,
            factor_indirecto=parametros.factor_indirecto,
            factor_utilidad=parametros.factor_utilidad,
            factor_impuesto=parametros.factor_impuesto,
            factor_riesgo=parametros.factor_riesgo,
            metadatos={"parametros_costeo": parametros.to_dict()},
        )

    budget_a = budget(exp_a, tenant_a, "PA", "Presupuesto A")
    budget_b = budget(exp_b, tenant_b, "PB", "Presupuesto B")
    prog_a = ProgramaObra(tenant_id=tenant_a.id, expediente_id=exp_a.id, identificador=f"GA-{uuid4().hex[:8]}", nombre="Programa A", fecha_inicio_plan=__import__('datetime').datetime.now(__import__('datetime').timezone.utc))
    prog_b = ProgramaObra(tenant_id=tenant_b.id, expediente_id=exp_b.id, identificador=f"GB-{uuid4().hex[:8]}", nombre="Programa B", fecha_inicio_plan=__import__('datetime').datetime.now(__import__('datetime').timezone.utc))
    topo_a = Levantamiento(expediente_id=exp_a.id, identificador=f"TA-{uuid4().hex[:8]}", nombre="Topo A")
    topo_b = Levantamiento(expediente_id=exp_b.id, identificador=f"TB-{uuid4().hex[:8]}", nombre="Topo B")
    model_a = ModeloBIM(tenant_id=tenant_a.id, expediente_id=exp_a.id, identificador=f"BA-{uuid4().hex[:8]}", nombre="BIM A", ruta_archivo=f"tenant/{tenant_a.id}/a.ifc")
    model_b = ModeloBIM(tenant_id=tenant_b.id, expediente_id=exp_b.id, identificador=f"BB-{uuid4().hex[:8]}", nombre="BIM B", ruta_archivo=f"tenant/{tenant_b.id}/b.ifc")
    db_session.add_all([budget_a, budget_b, prog_a, prog_b, topo_a, topo_b, model_a, model_b]); await db_session.commit()

    assert await PresupuestoService(db_session, tenant_a.id).get(budget_b.id) is None
    with pytest.raises(MegalodonException):
        await ProgramacionService(db_session, tenant_a.id)._validar_programa_en_expediente(prog_b.id, exp_b.id, tenant_id=tenant_a.id)
    with pytest.raises(MegalodonException):
        await BIMService(db_session, tenant_a.id)._validar_modelo_en_expediente(model_b.id, exp_b.id)
    assert await TopografiaService(db_session, tenant_a.id).listar_levantamientos(exp_b.id) == []

    run_b = MonteCarloRun(tenant_id=tenant_b.id, task_id=f"task-{uuid4().hex}", request_hash=uuid4().hex, estado=EstadoMonteCarlo.PENDIENTE.value, progreso=0, iteraciones=10, seed=1, presupuesto_base=1, presupuesto_maximo=2, variables=[], configuracion={})
    db_session.add(run_b); await db_session.commit()
    assert await MonteCarloService(db_session, tenant_a.id).esta_cancelada(run_b.task_id) is False
    assert await MonteCarloService(db_session, tenant_a.id).marcar_en_proceso(str(run_b.id)) is None
