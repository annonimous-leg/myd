from datetime import datetime, timedelta, timezone
from uuid import uuid4
from hashlib import sha256
import json

import pytest
from sqlalchemy import select
from app.models.procurement import TenderPackage
from app.models.procurement_jobs import ProcurementJob
from app.services.procurement.jobs import ProcurementJobService
from app.services.procurement.service import ProcurementService
from tests.conftest import AsyncSessionLocalTest, engine_test
from tests.test_prr_reproductions_20261007 import _expediente


async def make_job(db, tenant, user):
    exp = _expediente(tenant_id=tenant.id, user_id=user.id, suffix="PROC-ATOMIC")
    db.add(exp)
    await db.flush()
    tender = TenderPackage(tenant_id=tenant.id, creado_por_id=user.id,
        actualizado_por_id=user.id, expediente_id=exp.id,
        identifier=f"PA-{uuid4().hex[:8]}", title="Atomic proposal preparation",
        state="QA_READY", canonical_model={"facts": {"original": True}}, current_revision=1)
    db.add(tender)
    await db.flush()
    job = ProcurementJob(tenant_id=tenant.id, creado_por_id=user.id,
        actualizado_por_id=user.id, tender_id=tender.id, kind="RUN", status="QUEUED",
        request_hash=ProcurementJobService.request_hash(tender_id=tender.id, kind="RUN",
            revision=1, model_hash=sha256(json.dumps(tender.canonical_model, sort_keys=True, default=str).encode()).hexdigest()), result={})
    db.add(job)
    await db.flush()
    job.task_id = str(job.id)
    await db.commit()
    return job, tender


@pytest.mark.asyncio
async def test_procurement_inner_commit_cannot_outlive_failed_job(db_session, tenant_a_user, monkeypatch):
    from app.workers import procurement_tasks as worker
    tenant, user = tenant_a_user
    job, tender = await make_job(db_session, tenant, user)
    job_id, tender_id = job.id, tender.id
    monkeypatch.setattr(worker, "AsyncSessionLocal", AsyncSessionLocalTest)
    async def failing_business(self, tender_id):
        row = await self.db.get(TenderPackage, tender_id)
        row.canonical_model = {"obsolete": "must roll back"}
        await self.db.commit()  # existing service helpers commit independently
        raise RuntimeError("business step failed after inner commit")
    monkeypatch.setattr(ProcurementService, "run", failing_business)
    with pytest.raises(RuntimeError, match="business step failed"):
        await worker._execute(str(job_id), str(user.id), str(tenant.id), str(tender_id))
    async with AsyncSessionLocalTest() as fresh:
        saved = await fresh.get(TenderPackage, tender_id)
        assert saved.canonical_model == {"facts": {"original": True}}
        assert (await fresh.get(ProcurementJob, job_id)).status == "FAILED"


@pytest.mark.asyncio
async def test_procurement_rejects_message_tender_different_from_durable_job(db_session, tenant_a_user, monkeypatch):
    from app.workers import procurement_tasks as worker
    tenant, user = tenant_a_user
    job, tender = await make_job(db_session, tenant, user)
    other_job, other_tender = await make_job(db_session, tenant, user)
    monkeypatch.setattr(worker, "AsyncSessionLocal", AsyncSessionLocalTest)
    called = []
    async def business(self, tender_id):
        called.append(tender_id)
        return {"tender_id": str(tender_id)}
    monkeypatch.setattr(ProcurementService, "run", business)
    with pytest.raises(RuntimeError, match="context"):
        await worker._execute(str(job.id), str(user.id), str(tenant.id), str(other_tender.id))
    assert called == []


@pytest.mark.asyncio
async def test_procurement_lost_queued_message_is_republished(db_session, tenant_a_user, monkeypatch):
    tenant, user = tenant_a_user
    job, tender = await make_job(db_session, tenant, user)
    job.updated_at = datetime.now(timezone.utc) - timedelta(seconds=2000)
    await db_session.commit()
    sent = []
    monkeypatch.setattr("app.services.procurement.jobs.celery_app.send_task",
                        lambda *args, **kwargs: sent.append(kwargs))
    assert await ProcurementJobService.reconcile_pending(db_session) == 1
    assert sent[0]["task_id"] == str(job.id)
    assert sent[0]["args"][3] == str(tender.id)


@pytest.mark.asyncio
async def test_procurement_old_attempt_cannot_fail_reclaimed_job(db_session, tenant_a_user, monkeypatch):
    tenant, user = tenant_a_user
    job, _ = await make_job(db_session, tenant, user)
    service = ProcurementJobService(db_session, user)
    _, old_token = await service.claim(job.id)
    async with AsyncSessionLocalTest() as other:
        row = await other.get(ProcurementJob, job.id)
        row.status, row.claim_token, row.lease_expires_at = "PENDING", None, None
        await other.commit()
        _, new_token = await ProcurementJobService(other, user).claim(job.id)
    assert new_token != old_token
    assert not await service.fail_attempt(job.id, old_token, RuntimeError("late"))
    async with AsyncSessionLocalTest() as fresh:
        row = await fresh.get(ProcurementJob, job.id)
        assert row.status == "RUNNING"
        assert row.claim_token == new_token
        assert row.attempt == 2


@pytest.mark.asyncio
async def test_procurement_changed_revision_does_not_execute(db_session, tenant_a_user, monkeypatch):
    from app.workers import procurement_tasks as worker
    tenant, user = tenant_a_user
    job, tender = await make_job(db_session, tenant, user)
    tender.current_revision += 1
    tender.canonical_model = {"changed": True}
    await db_session.commit()
    monkeypatch.setattr(worker, "AsyncSessionLocal", AsyncSessionLocalTest)
    called = []
    async def business(self, tender_id):
        called.append(tender_id)
        return {}
    monkeypatch.setattr(ProcurementService, "run", business)
    with pytest.raises(RuntimeError, match="input revision changed"):
        await worker._execute(str(job.id), str(user.id), str(tenant.id), str(tender.id))
    assert called == []


@pytest.mark.asyncio
async def test_procurement_final_job_rejection_rolls_back_business_and_ready_trace(db_session, tenant_a_user, monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    from app.models.procurement import TenderPreparationRun
    from app.services.procurement.preparation_runs import PreparationRunTracker
    from app.workers import procurement_tasks as worker
    tenant, user = tenant_a_user
    job, tender = await make_job(db_session, tenant, user)
    job_id, tender_id = job.id, tender.id
    monkeypatch.setattr(worker, "AsyncSessionLocal", AsyncSessionLocalTest)
    trace_id = None
    async def business(self, tender_id):
        nonlocal trace_id
        row = await self._get(tender_id, for_update=True)
        tracker = PreparationRunTracker(self.db, row, self.user.id, session_factory=AsyncSessionLocalTest)
        trace_id = (await tracker.start(correlation_id=self.preparation_correlation_id)).id
        row.canonical_model = {"must": "rollback"}
        await self.db.commit()
        await tracker.finish("READY_FOR_HUMAN_REVIEW", atomic=True)
        await self.db.commit()
        return {"state": "READY_FOR_HUMAN_REVIEW"}
    monkeypatch.setattr(ProcurementService, "run", business)
    sqlite = db_session.bind.dialect.name == "sqlite"
    if sqlite:
        ddl = """CREATE TRIGGER reject_proc_completion BEFORE UPDATE OF status ON procurement_jobs
            WHEN NEW.status = 'SUCCEEDED' BEGIN SELECT RAISE(ABORT, 'completion_rejected'); END"""
    else:
        await db_session.execute(text("""CREATE FUNCTION reject_proc_completion() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN IF NEW.status = 'SUCCEEDED' THEN
            RAISE EXCEPTION 'completion_rejected'; END IF; RETURN NEW; END $$"""))
        ddl = """CREATE TRIGGER reject_proc_completion BEFORE UPDATE OF status ON procurement_jobs
            FOR EACH ROW EXECUTE FUNCTION reject_proc_completion()"""
    await db_session.execute(text(ddl))
    await db_session.commit()
    try:
        with pytest.raises(DBAPIError, match="completion_rejected"):
            await worker._execute(str(job_id), str(user.id), str(tenant.id), str(tender_id))
        async with AsyncSessionLocalTest() as fresh:
            assert (await fresh.get(TenderPackage, tender_id)).canonical_model == {"facts": {"original": True}}
            saved = await fresh.get(ProcurementJob, job_id)
            assert saved.status == "FAILED"
            assert saved.result == {}
            assert (await fresh.get(TenderPreparationRun, trace_id)).status == "FAILED"
    finally:
        await db_session.rollback()
        await db_session.execute(text("DROP TRIGGER reject_proc_completion" + (" ON procurement_jobs" if not sqlite else "")))
        if not sqlite:
            await db_session.execute(text("DROP FUNCTION reject_proc_completion()"))
        await db_session.commit()


@pytest.mark.asyncio
async def test_postgresql_procurement_recovery_skips_worker_held_lock_after_inner_commit(db_session, tenant_a_user, monkeypatch):
    if db_session.bind.dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL row locks; SQLite cannot certify SKIP LOCKED")
    from sqlalchemy.ext.asyncio import AsyncSession
    tenant, user = tenant_a_user
    job, _ = await make_job(db_session, tenant, user)
    _, token = await ProcurementJobService(db_session, user).claim(job.id)
    job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.commit()
    sent = []
    monkeypatch.setattr("app.services.procurement.jobs.celery_app.send_task",
                        lambda *args, **kwargs: sent.append(kwargs))
    async with engine_test.connect() as conn:
        async with conn.begin():
            async with AsyncSession(bind=conn, join_transaction_mode="rollback_only") as writer:
                await writer.scalar(select(ProcurementJob).where(ProcurementJob.id == job.id).with_for_update(key_share=True))
                await writer.commit()  # must retain outer lock
                async with AsyncSessionLocalTest() as other:
                    assert await ProcurementJobService.reconcile_pending(other) == 0
                assert sent == []
    assert await ProcurementJobService.reconcile_pending(db_session) == 1
    await db_session.refresh(job)
    assert job.status == "QUEUED"
    assert job.claim_token is None


@pytest.mark.asyncio
async def test_procurement_failed_storage_intent_can_retry_identical_content(db_session, tenant_a_user):
    from app.services.procurement.storage_guard import ProcurementStorageGuard
    tenant, _ = tenant_a_user
    guard = ProcurementStorageGuard(session_factory=AsyncSessionLocalTest)
    args = dict(tenant_id=tenant.id, job_id=None, bucket="exports",
                path=f"tenant/{tenant.id}/artifact-sha.pdf", content_hash="a" * 64,
                content_type="application/pdf", size_bytes=5, entity_type="TenderArtifact")
    intent = await guard._prepare(**args)
    await guard._set_state(intent, "ERROR", tenant_id=tenant.id, error="upload lost")
    assert await guard._prepare(**args) == intent
