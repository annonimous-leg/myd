"""Regressions through independent DB sessions, never same-session token edits."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.models.montecarlo import EstadoMonteCarlo, MonteCarloRun
from app.models.presupuesto import Presupuesto
from app.models.ocr_job import OCRJob
from app.services.montecarlo_service import MonteCarloService
from app.services.ocr_jobs import OCRJobService
from app.engines.ia.ocr_metrados import ResultadoOCR
from tests.conftest import AsyncSessionLocalTest
from tests.test_prr_reproductions_20261007 import _montecarlo_run, _expediente


def empty_ocr(job_id):
    return ResultadoOCR(documento_id=str(job_id), total_metrados=0,
                        confianza_promedio=0, metrados=[], texto_completo="",
                        paginas_procesadas=1, errores=[])


@pytest.mark.asyncio
async def test_montecarlo_cached_attempt_cannot_overwrite_cancellation(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    run = _montecarlo_run(tenant_id=tenant.id, user_id=user.id,
                         estado=EstadoMonteCarlo.PENDIENTE.value)
    db_session.add(run)
    await db_session.commit()
    run_id, task_id, tenant_id = run.id, run.task_id, tenant.id
    service = MonteCarloService(db_session, tenant_id)
    token = await service.marcar_en_proceso(str(run_id))
    # run stays strongly referenced in the old worker's identity map.
    async with AsyncSessionLocalTest() as other:
        await MonteCarloService(other, tenant_id).cancelar(task_id, tenant_id)
    assert not await service.completar(task_id, {"obsolete": True}, 1, token=token)
    async with AsyncSessionLocalTest() as fresh:
        persisted = await fresh.get(MonteCarloRun, run_id)
        assert persisted.estado == EstadoMonteCarlo.CANCELADO.value
        assert persisted.resultado is None


@pytest.mark.asyncio
async def test_ocr_cached_attempt_cannot_overwrite_new_claim(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    job_id, tenant_id = uuid4(), tenant.id
    service = OCRJobService(db_session, tenant_id)
    job, _ = await service.crear(user=user, job_id=job_id, filename="x.png",
        content_type="image/png", storage_path=f"tenant/{tenant_id}/{job_id}",
        source_bytes=b"source", presupuesto_id=None)
    job, old_token = await service.claim(job_id)
    await db_session.commit()  # release the refresh read transaction
    async with AsyncSessionLocalTest() as other:
        row = await other.get(OCRJob, job_id)
        row.status, row.claim_token, row.started_at = "PENDING", None, None
        await other.commit()
        _, new_token = await OCRJobService(other, tenant_id).claim(job_id)
    assert new_token != old_token
    assert not await service.completar(job_id, old_token, empty_ocr(job_id))
    async with AsyncSessionLocalTest() as fresh:
        persisted = await fresh.get(OCRJob, job_id)
        assert persisted.status == "RUNNING"
        assert persisted.claim_token == new_token
        assert persisted.attempts == 2


@pytest.mark.asyncio
async def test_montecarlo_budget_write_failure_reverts_both_rows(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    exp = _expediente(tenant_id=tenant.id, user_id=user.id, suffix="ATOMIC-DB")
    db_session.add(exp)
    await db_session.flush()
    budget = Presupuesto(tenant_id=tenant.id, expediente_id=exp.id,
        identificador=f"AT-{uuid4().hex[:8]}", nombre="Atomic DB failure",
        factor_indirecto=0, factor_utilidad=0, factor_impuesto=0.16)
    db_session.add(budget)
    await db_session.flush()
    run = _montecarlo_run(tenant_id=tenant.id, user_id=user.id,
                         estado=EstadoMonteCarlo.PENDIENTE.value)
    run.presupuesto_id, run.expediente_id = budget.id, exp.id
    db_session.add(run)
    await db_session.commit()
    run_id, budget_id = run.id, budget.id
    service = MonteCarloService(db_session, tenant.id)
    token = await service.marcar_en_proceso(str(run_id))
    # Actual DB rejection of the projection UPDATE, after completion assigns both rows.
    sqlite = db_session.bind.dialect.name == "sqlite"
    if sqlite:
        ddl = """CREATE TRIGGER reject_mc_projection BEFORE UPDATE OF resultado_montecarlo
                 ON presupuestos WHEN NEW.resultado_montecarlo IS NOT NULL
                 BEGIN SELECT RAISE(ABORT, 'projection_rejected'); END"""
    else:
        await db_session.execute(text("""CREATE FUNCTION reject_mc_projection() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'projection_rejected'; END $$"""))
        ddl = """CREATE TRIGGER reject_mc_projection BEFORE UPDATE OF resultado_montecarlo
                 ON presupuestos FOR EACH ROW EXECUTE FUNCTION reject_mc_projection()"""
    await db_session.execute(text(ddl))
    await db_session.commit()
    try:
        with pytest.raises(DBAPIError, match="projection_rejected"):
            await service.completar(run.task_id, {"p80": 1190}, 5, token=token)
        async with AsyncSessionLocalTest() as fresh:
            saved_run = await fresh.get(MonteCarloRun, run_id)
            saved_budget = await fresh.get(Presupuesto, budget_id)
            assert saved_run.estado == EstadoMonteCarlo.EN_PROCESO.value
            assert saved_run.execution_token == token
            assert saved_run.resultado is None
            assert saved_budget.resultado_montecarlo is None
    finally:
        await db_session.rollback()
        await db_session.execute(text("DROP TRIGGER reject_mc_projection" +
                                      (" ON presupuestos" if not sqlite else "")))
        if not sqlite:
            await db_session.execute(text("DROP FUNCTION reject_mc_projection()"))
        await db_session.commit()


@pytest.mark.asyncio
async def test_ocr_lost_queued_message_is_republished(db_session, tenant_a_user, monkeypatch):
    tenant, user = tenant_a_user
    job_id = uuid4()
    job, _ = await OCRJobService(db_session, tenant.id).crear(user=user,
        job_id=job_id, filename="x.png", content_type="image/png",
        storage_path=f"tenant/{tenant.id}/{job_id}", source_bytes=b"source",
        presupuesto_id=None)
    job.status = "QUEUED"
    job.queued_at = datetime.now(timezone.utc) - timedelta(seconds=400)
    await db_session.commit()
    sent = []
    monkeypatch.setattr("app.services.ocr_jobs.celery_app.send_task",
                        lambda *args, **kwargs: sent.append(kwargs))
    assert await OCRJobService.reconciliar(db_session) == 1
    assert sent[0]["args"] == [str(job_id)]
    await db_session.refresh(job)
    assert job.status == "QUEUED"
    assert job.claim_token is None
    assert job.attempts == 0


@pytest.mark.asyncio
async def test_ocr_expired_unreclaimed_attempt_cannot_complete(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    job_id = uuid4()
    service = OCRJobService(db_session, tenant.id)
    job, _ = await service.crear(user=user, job_id=job_id, filename="x.png",
        content_type="image/png", storage_path=f"tenant/{tenant.id}/{job_id}",
        source_bytes=b"source", presupuesto_id=None)
    job, token = await service.claim(job_id)
    job.started_at = datetime.now(timezone.utc) - timedelta(seconds=400)
    await db_session.commit()
    assert not await service.completar(job_id, token, empty_ocr(job_id))
    assert await service.fallar(job_id, token, RuntimeError("late")) == "STALE"


@pytest.mark.asyncio
async def test_ocr_does_not_add_rows_to_budget_approved_in_other_session(db_session, tenant_a_user):
    from app.engines.ia.ocr_metrados import MetradoExtraido
    from app.models.presupuesto import Partida
    from app.core.errors import MegalodonException
    from sqlalchemy import select
    tenant, user = tenant_a_user
    tenant_id = tenant.id
    exp = _expediente(tenant_id=tenant_id, user_id=user.id, suffix="OCR-APPROVED")
    db_session.add(exp)
    await db_session.flush()
    budget = Presupuesto(tenant_id=tenant_id, expediente_id=exp.id,
        identificador=f"OA-{uuid4().hex[:8]}", nombre="OCR editable",
        estado="BORRADOR", factor_indirecto=0, factor_utilidad=0, factor_impuesto=0)
    db_session.add(budget)
    await db_session.commit()
    budget_id = budget.id
    service = OCRJobService(db_session, tenant_id)
    job_id = uuid4()
    job, _ = await service.crear(user=user, job_id=job_id, filename="x.png",
        content_type="image/png", storage_path=f"tenant/{tenant_id}/{job_id}",
        source_bytes=b"source", presupuesto_id=budget_id)
    _, token = await service.claim(job_id)
    await db_session.commit()
    async with AsyncSessionLocalTest() as other:
        current = await other.get(Presupuesto, budget_id)
        current.estado = "APROBADO"
        await other.commit()
    result = empty_ocr(job_id)
    result.metrados = [MetradoExtraido(concepto="M", descripcion="Muro", unidad="m2",
        cantidad=10, confianza=90, pagina=1, bbox=(0, 0, 10, 10), texto_original="Muro 10 m2")]
    result.total_metrados = 1
    with pytest.raises(MegalodonException):
        await service.completar(job_id, token, result)
    # Failure must leave caller's session reusable without a manual rollback.
    async with AsyncSessionLocalTest() as fresh:
        assert (await fresh.get(Presupuesto, budget_id)).estado == "APROBADO"
        assert (await fresh.get(OCRJob, job_id)).status == "RUNNING"
        assert (await fresh.scalars(select(Partida).where(Partida.presupuesto_id == budget_id))).all() == []
    assert await service.fallar(job_id, token, RuntimeError("approved")) == "PENDING"


@pytest.mark.asyncio
async def test_ocr_api_keeps_source_after_ambiguous_postcommit_error(db_session, tenant_a_user, monkeypatch):
    from io import BytesIO
    from fastapi import UploadFile
    from unittest.mock import AsyncMock
    from types import SimpleNamespace
    from app.api.v1.ocr import extraer_metrados
    tenant, user = tenant_a_user
    storage = SimpleNamespace(subir=AsyncMock(), eliminar=AsyncMock())
    monkeypatch.setattr("app.api.v1.ocr.storage_documentos", lambda: storage)
    create = OCRJobService.crear
    async def postcommit_failure(self, **kwargs):
        await create(self, **kwargs)
        raise ConnectionError("lost acknowledgement after durable commit")
    monkeypatch.setattr(OCRJobService, "crear", postcommit_failure)
    with pytest.raises(ConnectionError, match="lost acknowledgement"):
        await extraer_metrados(file=UploadFile(file=BytesIO(b"input"), filename="x.png"),
            presupuesto_id=None, idempotency_key=None, db=db_session,
            current_user=user, _rate_limit=True)
    assert storage.subir.await_count == 1
    storage.eliminar.assert_not_awaited()


@pytest.mark.asyncio
async def test_ocr_api_removes_source_when_database_confirms_no_job(db_session, tenant_a_user, monkeypatch):
    from io import BytesIO
    from fastapi import UploadFile
    from unittest.mock import AsyncMock
    from types import SimpleNamespace
    from app.api.v1.ocr import extraer_metrados
    _, user = tenant_a_user
    storage = SimpleNamespace(subir=AsyncMock(), eliminar=AsyncMock())
    monkeypatch.setattr("app.api.v1.ocr.storage_documentos", lambda: storage)
    async def rejected(self, **kwargs):
        raise ValueError("before commit")
    monkeypatch.setattr(OCRJobService, "crear", rejected)
    with pytest.raises(ValueError, match="before commit"):
        await extraer_metrados(file=UploadFile(file=BytesIO(b"input"), filename="x.png"),
            presupuesto_id=None, idempotency_key=None, db=db_session,
            current_user=user, _rate_limit=True)
    assert storage.eliminar.await_count == 1


@pytest.mark.asyncio
async def test_postgresql_montecarlo_worker_runs_across_separate_event_loops(db_session, tenant_a_user):
    if db_session.bind.dialect.name != "postgresql":
        pytest.skip("Requires migrated PostgreSQL and real Redis Celery backend")
    import asyncio
    from app.workers.montecarlo_tasks import ejecutar_simulacion
    tenant, user = tenant_a_user
    for _ in range(2):
        run = _montecarlo_run(tenant_id=tenant.id, user_id=user.id,
                             estado=EstadoMonteCarlo.PENDIENTE.value)
        db_session.add(run)
        await db_session.commit()
        run_id, task_id = run.id, run.task_id
        payload = MonteCarloService.payload_worker(run)
        result = await asyncio.to_thread(ejecutar_simulacion.apply,
            args=[task_id, str(run_id), payload], task_id=task_id, throw=True)
        assert result.result["status"] == "SUCCESS"
        async with AsyncSessionLocalTest() as fresh:
            saved = await fresh.get(MonteCarloRun, run_id)
            assert saved.estado == EstadoMonteCarlo.COMPLETADO.value
            assert saved.resultado
            assert saved.execution_token is None
