from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from hashlib import sha256
import json
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procurement_jobs import ProcurementJob
from app.models.procurement import TenderPackage
from app.models.user import User
from app.services.procurement.jobs import ProcurementJobService, PROCUREMENT_WORKER_HARD_LIMIT_SECONDS
from app.services.procurement.service import ProcurementService
from app.services.procurement.preparation_runs import attempt_correlation
from app.workers.database import AsyncSessionLocal
from app.workers.celery_app import celery_app


@celery_app.task(bind=True, time_limit=PROCUREMENT_WORKER_HARD_LIMIT_SECONDS,
                 acks_late=True, reject_on_worker_lost=True, track_started=True)
def execute_job(self, job_id: str, user_id: str, tenant_id: str, tender_id: str):
    return asyncio.run(_execute(job_id, user_id, tenant_id, tender_id))


async def _execute(job_id: str, user_id: str, tenant_id: str, tender_id: str):
    from app.integrations.supabase_storage import worker_storage_scope
    async with worker_storage_scope():
        return await _execute_attempt(job_id, user_id, tenant_id, tender_id)


async def _execute_attempt(job_id: str, user_id: str, tenant_id: str, tender_id: str):
    job_uuid, user_uuid, tenant_uuid, tender_uuid = map(UUID, (job_id, user_id, tenant_id, tender_id))
    async with AsyncSessionLocal() as claim_db:
        job = await claim_db.scalar(select(ProcurementJob).where(
            ProcurementJob.id == job_uuid, ProcurementJob.tenant_id == tenant_uuid))
        user = await claim_db.get(User, user_uuid)
        if (job is None or user is None or user.tenant_id != tenant_uuid or
                not user.is_active or job.creado_por_id != user_uuid or job.tender_id != tender_uuid):
            raise RuntimeError("Invalid durable Procurement message context")
        job, token = await ProcurementJobService(claim_db, user).claim(job_uuid)
        if token is None:
            return job.result if job.status == "SUCCEEDED" else {"job_id": job_id, "status": job.status}
        engine = claim_db.bind

    # This transaction belongs only to Procurement. Inner service commits flush
    # into the externally owned connection; they cannot commit the unit of work.
    # Its job lock remains held for ALL business writes, until result and business
    # state commit together. A process crash rolls them back; the durable claim
    # then expires and SKIP LOCKED recovery offers a fresh attempt.
    try:
        async with engine.connect() as connection:
            async with connection.begin():
                async with AsyncSession(bind=connection, expire_on_commit=False,
                        autoflush=False, join_transaction_mode="rollback_only") as db:
                    job = await db.scalar(select(ProcurementJob).where(
                        ProcurementJob.id == job_uuid, ProcurementJob.tenant_id == tenant_uuid
                    ).with_for_update(key_share=True).execution_options(populate_existing=True))
                    if not ProcurementJobService.attempt_is_current(job, token):
                        return {"job_id": job_id, "status": "IGNORED_STALE_ATTEMPT"}
                    user = await db.get(User, user_uuid)
                    if user is None or not user.is_active or user.tenant_id != tenant_uuid:
                        raise RuntimeError("Invalid durable Procurement user context")
                    tender = await db.scalar(select(TenderPackage).where(
                        TenderPackage.id == job.tender_id, TenderPackage.tenant_id == tenant_uuid
                    ).with_for_update(key_share=True).execution_options(populate_existing=True))
                    if tender is None:
                        raise RuntimeError("Invalid durable Procurement tender context")
                    expected_hash = ProcurementJobService.request_hash(tender_id=tender.id,
                        kind=job.kind, revision=tender.current_revision,
                        model_hash=sha256(json.dumps(tender.canonical_model, sort_keys=True, default=str).encode()).hexdigest())
                    if job.request_hash != expected_hash:
                        raise RuntimeError("Procurement input revision changed; create a new job")
                    service = ProcurementService(db, user, independent_sessions=AsyncSessionLocal,
                        preparation_correlation_id=attempt_correlation(job_uuid, token))
                    if job.kind == "RUN":
                        result = await service.run(job.tender_id)
                    elif job.kind == "COMPILE":
                        rows = await service.compile_artifacts(job.tender_id)
                        result = {"artifacts": [{"id": str(r.id), "code": r.artifact_code,
                            "version": r.version, "storage_path": r.storage_path,
                            "content_hash": r.content_hash} for r in rows]}
                    else:
                        raise RuntimeError(f"Tipo de job no soportado: {job.kind}")
                    if not ProcurementJobService.attempt_is_current(job, token):
                        raise RuntimeError("Procurement attempt expired before commit")
                    job.result = result
                    job.status = "SUCCEEDED"
                    job.progress = 100
                    job.finished_at = datetime.now(timezone.utc)
                    job.claim_token = None
                    job.lease_expires_at = None
                    job.error_code = None
                    job.error_message = None
                    await db.flush()
                # Only connection.begin owns the final commit.
        return result
    except Exception as exc:
        async with AsyncSessionLocal() as failed_db:
            user = await failed_db.get(User, user_uuid)
            if user is not None and user.tenant_id == tenant_uuid:
                await ProcurementJobService(failed_db, user).fail_attempt(job_uuid, token, exc)
        raise
