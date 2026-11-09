from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.bim import ModeloBIM, ElementoBIM
from app.models.catalogo_apu import CatalogoAPU
from app.models.presupuesto import Presupuesto
from app.services.bim_service import BIMService
from tests.conftest import _create_tenant_and_user, _login
from tests.integration.test_bim_regressions import model, PARAMS


@pytest.mark.asyncio
async def test_failed_budget_commit_does_not_persist_budget_or_link(db_session, tenant_a_user, monkeypatch):
    tenant, user = tenant_a_user
    exp, obj = await model(db_session, tenant, user)
    element = ElementoBIM(modelo_id=obj.id, global_id=uuid4().hex, express_id=1, tipo="IfcWall")
    db_session.add(element)
    await db_session.commit()
    exp_id, obj_id, element_id, tenant_id = exp.id, obj.id, element.id, tenant.id
    commit = db_session.commit

    async def fail_with_links():
        if element.partida_id is not None:
            raise RuntimeError("commit with links failed")
        await commit()

    monkeypatch.setattr(db_session, "commit", fail_with_links)
    with pytest.raises(RuntimeError, match="commit with links failed"):
        await BIMService(db_session, tenant_id).crear_presupuesto_desde_bim(
            modelo_id=obj_id, expediente_id=exp_id, parametros_costeo=PARAMS
        )
    await db_session.rollback()
    assert await db_session.scalar(select(Presupuesto.id).where(Presupuesto.expediente_id == exp_id)) is None
    assert (await db_session.get(ElementoBIM, element_id)).partida_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize("persist", [True, False])
async def test_ifc_cleanup_reconciles_commit_outcome(db_session, tenant_a_user, monkeypatch, persist):
    from app.services import bim_service

    tenant, user = tenant_a_user
    exp, _ = await model(db_session, tenant, user)
    exp_id, tenant_id = exp.id, tenant.id

    class Storage:
        def __init__(self):
            self.objects = {}

        async def subir(self, path, content, **kwargs):
            self.objects[path] = content

        async def eliminar(self, paths):
            for path in paths:
                self.objects.pop(path)

    storage = Storage()
    monkeypatch.setattr(bim_service, "storage_bim", lambda: storage)
    commit = db_session.commit

    async def lose_ack():
        if persist:
            await commit()
        raise RuntimeError("commit result unknown")

    monkeypatch.setattr(db_session, "commit", lose_ack)
    if persist:
        saved = await BIMService(db_session, tenant_id).crear_modelo(
            expediente_id=exp_id, nombre="Upload under test", file_content=b"ifc", filename="audit.ifc"
        )
        assert storage.objects[saved.ruta_archivo] == b"ifc"
    else:
        with pytest.raises(RuntimeError, match="commit result unknown"):
            await BIMService(db_session, tenant_id).crear_modelo(
                expediente_id=exp_id, nombre="Upload under test", file_content=b"ifc", filename="audit.ifc"
            )
        assert storage.objects == {}
        assert await db_session.scalar(select(ModeloBIM.id).where(ModeloBIM.nombre == "Upload under test", ModeloBIM.tenant_id == tenant_id)) is None


@pytest.mark.asyncio
async def test_area_requires_concept_specific_review(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    exp, obj = await model(db_session, tenant, user)
    element = ElementoBIM(modelo_id=obj.id, global_id=uuid4().hex, express_id=1,
                           tipo="IfcWall", area=16, fuente_area="GEOMETRIA_CALCULADA")
    apu = CatalogoAPU(tenant_id=tenant.id, clave="WALL-SIDE", descripcion="Una cara de muro",
                      tipo="CONCEPTO", unidad="m2", precio_unitario=125, fuente="TEST")
    db_session.add_all([element, apu])
    await db_session.commit()
    options = dict(modelo_id=obj.id, expediente_id=exp.id, parametros_costeo=PARAMS,
                   mapeo_catalogo={"IfcWall": apu.id}, creado_por_id=user.id)
    service = BIMService(db_session, tenant.id)
    draft = await service.crear_presupuesto_desde_bim(**options)
    assert draft.estado == "BORRADOR"
    assert draft.monto_total == 0
    reviewed = await service.crear_presupuesto_desde_bim(**options, cantidades_complementarias=[
        {"elemento_id": element.id, "unidad": "m2", "cantidad": 6, "referencia": "Una cara revisada"}
    ])
    assert reviewed.monto_total == 750


@pytest.mark.asyncio
@pytest.mark.parametrize(("path", "payload"), [("cancelar", None), ("checkout", {"plan": "PRO"})])
async def test_readers_cannot_manage_billing(async_client, db_session, path, payload):
    from app.models.user import UserRole

    _, user = await _create_tenant_and_user(db_session, "billing-guard", "reader@example.com", role=UserRole.LECTOR)
    headers = await _login(async_client, user.email)
    response = await async_client.post(f"/api/v1/pagos/{path}", headers=headers, json=payload)
    assert response.status_code == 403


def test_ifc_dispatch_uses_dedicated_queue_and_configured_timeout(monkeypatch):
    from app.core import process_queue
    from app.workers.process_tasks import ejecutar_proceso

    published = []
    monkeypatch.setattr(ejecutar_proceso, "apply_async", lambda **opts: published.append(opts))
    monkeypatch.setattr(process_queue.settings, "IFC_PROCESSING_TIMEOUT_SECONDS", 123)
    monkeypatch.setattr(process_queue.settings, "IFC_DEDICATED_QUEUE", True)
    process_queue._enviar("ifc-job", "BIM_IFC")
    process_queue._enviar("drawing-job", "BIM_DRAWING")
    assert published[0]["queue"] == "megalodon-ifc"
    assert published[0]["time_limit"] == 123
    assert "queue" not in published[1]
    assert "time_limit" not in published[1]


@pytest.mark.asyncio
async def test_stripe_correlates_checkout_and_uses_provider_period(db_session, tenant_a_user, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace
    from app.integrations.payments import stripe_provider
    from app.models.entitlements import Suscripcion
    from app.services.suscripcion_service import SuscripcionService

    tenant, _ = tenant_a_user
    subscription = Suscripcion(tenant_id=tenant.id, plan="PRO", proveedor="STRIPE",
                               estado="PENDIENTE_PAGO", external_id="cs_example", monto=100, moneda="MXN")
    db_session.add(subscription)
    await db_session.commit()
    period = int((datetime.now(timezone.utc) + timedelta(days=11)).timestamp())

    def retrieve(subscription_id):
        assert subscription_id == "sub_example"
        return {"status": "active", "items": {"data": [{"current_period_end": period}]}}

    monkeypatch.setattr(stripe_provider, "_stripe_sdk", SimpleNamespace(Subscription=SimpleNamespace(retrieve=retrieve)))
    service = SuscripcionService(db_session)
    event = {"id": "evt_example", "type": "checkout.session.completed", "data": {
        "object": {"id": "cs_example", "subscription": "sub_example", "mode": "subscription"}
    }}
    await service.procesar_webhook("STRIPE", event, {})
    await service.procesar_webhook("STRIPE", event, {})
    await db_session.refresh(subscription)
    await db_session.refresh(tenant)
    assert subscription.external_id == "sub_example"
    assert subscription.estado == "ACTIVA"
    assert tenant.plan == "PRO"
    assert tenant.plan_vencimiento.replace(tzinfo=timezone.utc).timestamp() == period


@pytest.mark.asyncio
async def test_budget_retry_returns_same_record_and_rejects_key_reuse(db_session, tenant_a_user):
    from app.core.errors import MegalodonException

    tenant, user = tenant_a_user
    exp, obj = await model(db_session, tenant, user)
    db_session.add(ElementoBIM(modelo_id=obj.id, global_id=uuid4().hex, express_id=1, tipo="IfcWall"))
    await db_session.commit()
    service = BIMService(db_session, tenant.id)
    kwargs = dict(expediente_id=exp.id, modelo_id=obj.id, parametros_costeo=PARAMS)
    first = await service.crear_presupuesto_desde_bim(**kwargs, solicitud={"clave": "key", "huella": "original"})
    again = await service.crear_presupuesto_desde_bim(**kwargs, solicitud={"clave": "key", "huella": "original"})
    assert first.id == again.id
    from app.services.presupuesto_service import PresupuestoService
    revision = await PresupuestoService(db_session, tenant.id).crear_revision(
        first.id, exp.id, "Revisar medición", user.id
    )
    assert "solicitud" not in revision.metadatos["bim_cobertura"]
    assert (await service.crear_presupuesto_desde_bim(
        **kwargs, solicitud={"clave": "key", "huella": "original"}
    )).id == first.id
    with pytest.raises(MegalodonException) as exc:
        await service.crear_presupuesto_desde_bim(**kwargs, solicitud={"clave": "key", "huella": "changed"})
    assert exc.value.status_code == 409
