from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from uuid import UUID, uuid4

from sqlalchemy import select, or_, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode, MegalodonException
from app.models.procurement import TenderPackage
from app.models.procurement_jobs import ProcurementIdempotency, ProcurementJob
from app.models.user import User
from app.workers.celery_app import celery_app
from app.services.procurement.preparation_runs import fail_attempt_trace


PROCUREMENT_WORKER_HARD_LIMIT_SECONDS = 1800
PROCUREMENT_STALE_GRACE_SECONDS = 120


class ProcurementJobService:
    def __init__(self, db: AsyncSession, user: User):
        self.db = db
        self.user = user

    @staticmethod
    def request_hash(
        *,
        tender_id: UUID,
        kind: str,
        revision: int,
        model_hash: str,
    ) -> str:
        payload = {
            "tender_id": str(tender_id),
            "kind": kind,
            "revision": revision,
            "model_hash": model_hash,
        }
        return sha256(
            json.dumps(
                payload, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()

    async def _publish(
        self,
        job: ProcurementJob,
        tender: TenderPackage,
    ) -> ProcurementJob:
        """Publica un job durable serializando sólo este agregado.

        Procurement conserva su propia tabla/estado; no comparte un kernel de
        jobs con BIM ni Monte Carlo. El row lock evita que dos replays o dos
        reconciliadores publiquen el mismo PENDING simultáneamente. Se mantiene
        el lock durante el send acotado del broker para que un worker recibido
        inmediatamente espere a que QUEUED quede confirmado.
        """
        locked = await self.db.scalar(
            select(ProcurementJob)
            .where(
                ProcurementJob.id == job.id,
                ProcurementJob.tenant_id == job.tenant_id,
            )
            .with_for_update().execution_options(populate_existing=True)
        )
        if locked is None:
            raise MegalodonException(
                ErrorCode.TAREA_NO_ENCONTRADA,
                "Job de Procurement no encontrado.",
                404,
            )

        if locked.status in {"QUEUED", "RUNNING", "SUCCEEDED"}:
            return locked
        if locked.status != "PENDING":
            raise MegalodonException(
                ErrorCode.CONFLICT,
                f"El job {locked.id} no es publicable desde {locked.status}.",
                409,
            )

        if not locked.task_id:
            # Identidad determinista: si el proceso cae antes del commit, el
            # siguiente intento reconstruye exactamente el mismo task_id.
            locked.task_id = str(locked.id)
            await self.db.flush()

        try:
            celery_app.send_task(
                "app.workers.procurement_tasks.execute_job",
                args=[
                    str(locked.id),
                    str(self.user.id),
                    str(self.user.tenant_id),
                    str(tender.id),
                ],
                task_id=locked.task_id,
            )
        except Exception as exc:
            # El error del cliente del broker puede ser ambiguo. Conservamos
            # PENDING durable y diagnóstico; si el broker sí aceptó el mensaje,
            # el worker podrá reclamar PENDING apenas liberemos este lock.
            locked.error_code = "ENQUEUE_FAILED"
            locked.error_message = str(exc)[:4000]
            await self.db.commit()
            raise MegalodonException(
                ErrorCode.ARCHIVO_ERROR,
                "No se pudo confirmar la publicación del job de Procurement; quedó pendiente para reconciliación.",
                503,
                details={"job_id": str(locked.id), "task_id": locked.task_id},
            ) from exc

        locked.status = "QUEUED"
        locked.error_code = None
        locked.error_message = None
        await self.db.commit()
        await self.db.refresh(locked)
        return locked

    async def create_or_replay(
        self,
        tender: TenderPackage,
        kind: str,
        idempotency_key: str | None = None,
    ) -> tuple[ProcurementJob, bool]:
        model_hash = sha256(
            json.dumps(
                tender.canonical_model, sort_keys=True, default=str
            ).encode()
        ).hexdigest()
        effective_key = (
            idempotency_key
            or f"derived:{kind}:{tender.id}:r{tender.current_revision}:{model_hash}"
        )[:128]
        request_hash = self.request_hash(
            tender_id=tender.id,
            kind=kind,
            revision=tender.current_revision,
            model_hash=model_hash,
        )

        existing = await self.db.scalar(
            select(ProcurementIdempotency).where(
                ProcurementIdempotency.tenant_id == self.user.tenant_id,
                ProcurementIdempotency.key == effective_key,
            )
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                raise MegalodonException(
                    ErrorCode.CONFLICT,
                    "La Idempotency-Key ya fue utilizada para otra operación.",
                    409,
                )
            job = await self.db.get(ProcurementJob, existing.job_id)
            if job is None:
                raise MegalodonException(
                    ErrorCode.ARCHIVO_ERROR,
                    "Registro de idempotencia huérfano; requiere reconciliación administrativa.",
                    500,
                )
            if job.status == "PENDING":
                await self._publish(job, tender)
            return job, True

        job = ProcurementJob(
            id=uuid4(),
            tenant_id=self.user.tenant_id,
            creado_por_id=self.user.id,
            actualizado_por_id=self.user.id,
            tender_id=tender.id,
            kind=kind,
            status="PENDING",
            task_id=None,
            idempotency_key=effective_key,
            request_hash=request_hash,
            progress=0,
        )
        self.db.add(job)

        try:
            await self.db.flush()
            # El id de Celery queda durable antes del primer intento de envío.
            job.task_id = str(job.id)
            self.db.add(
                ProcurementIdempotency(
                    tenant_id=self.user.tenant_id,
                    key=effective_key,
                    request_hash=request_hash,
                    job_id=job.id,
                )
            )
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            existing = await self.db.scalar(
                select(ProcurementIdempotency).where(
                    ProcurementIdempotency.tenant_id == self.user.tenant_id,
                    ProcurementIdempotency.key == effective_key,
                )
            )
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise MegalodonException(ErrorCode.CONFLICT,
                        "La Idempotency-Key ya fue utilizada para otra operación.", 409)
                job = await self.db.get(ProcurementJob, existing.job_id)
                if job is not None:
                    if job.status == "PENDING":
                        await self._publish(job, tender)
                    return job, True
            raise
        except Exception:
            await self.db.rollback()
            raise

        await self._publish(job, tender)
        return job, False

    @classmethod
    async def reconcile_pending(
        cls,
        db: AsyncSession,
        *,
        limit: int = 100,
    ) -> int:
        """Recupera publicaciones perdidas y workers muertos por hard-timeout."""
        now = datetime.now(timezone.utc)
        stale_before = now - timedelta(
            seconds=(
                PROCUREMENT_WORKER_HARD_LIMIT_SECONDS
                + PROCUREMENT_STALE_GRACE_SECONDS
            )
        )

        stale = (
            await db.scalars(
                select(ProcurementJob)
                .where(
                    or_(
                        (ProcurementJob.status == "RUNNING") &
                        (ProcurementJob.lease_expires_at <= now),
                        (ProcurementJob.status == "QUEUED") &
                        (ProcurementJob.claim_token.is_(None)) &
                        (ProcurementJob.updated_at < stale_before),
                    ),
                )
                .order_by(ProcurementJob.started_at)
                .limit(limit)
                .with_for_update(skip_locked=True).execution_options(populate_existing=True)
            )
        ).all()
        for job in stale:
            await fail_attempt_trace(db, job, code="WORKER_LEASE_EXPIRED", detail="El intento durable venció.")
            job.status = "PENDING"
            job.progress = 0
            job.started_at = None
            job.claim_token = None
            job.lease_expires_at = None
            job.error_code = "WORKER_LEASE_EXPIRED"
            job.error_message = (
                "El worker excedió su límite de ejecución; el job será republicado."
            )
        if stale:
            await db.commit()

        jobs = (
            await db.scalars(
                select(ProcurementJob)
                .where(ProcurementJob.status == "PENDING")
                .order_by(ProcurementJob.created_at)
                .limit(limit)
            )
        ).all()

        published = 0
        for job in jobs:
            user = (
                await db.get(User, job.creado_por_id)
                if job.creado_por_id is not None
                else None
            )
            tender = await db.scalar(
                select(TenderPackage).where(
                    TenderPackage.id == job.tender_id,
                    TenderPackage.tenant_id == job.tenant_id,
                )
            )
            if (
                user is None
                or user.tenant_id != job.tenant_id
                or tender is None
            ):
                job.status = "FAILED"
                job.error_code = "DURABLE_CONTEXT_INVALID"
                job.error_message = (
                    "No se pudo reconstruir el contexto durable del job."
                )
                job.finished_at = now
                await db.commit()
                continue

            service = cls(db, user)
            try:
                await service._publish(job, tender)
            except MegalodonException:
                # _publish dejó PENDING + diagnóstico; siguiente tick reintenta.
                continue
            published += 1

        return published

    @staticmethod
    def attempt_is_current(job: ProcurementJob | None, token: UUID) -> bool:
        if job is None or job.status != "RUNNING" or job.claim_token != token:
            return False
        expires = job.lease_expires_at
        if expires is None:
            return False
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return expires > datetime.now(timezone.utc)

    async def claim(self, job_id: UUID) -> tuple[ProcurementJob, UUID | None]:
        job = await self.db.scalar(select(ProcurementJob).where(
            ProcurementJob.id == job_id, ProcurementJob.tenant_id == self.user.tenant_id,
        ).with_for_update().execution_options(populate_existing=True))
        if job is None:
            raise RuntimeError("Procurement job no encontrado")
        if job.status not in {"PENDING", "QUEUED"}:
            return job, None
        if job.creado_por_id != self.user.id or not self.user.is_active:
            raise RuntimeError("Invalid durable Procurement user context")
        token = uuid4()
        job.attempt += 1
        job.claim_token = token
        job.lease_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=PROCUREMENT_WORKER_HARD_LIMIT_SECONDS + PROCUREMENT_STALE_GRACE_SECONDS)
        job.status = "RUNNING"
        job.progress = 5
        job.started_at = datetime.now(timezone.utc)
        job.error_code = None
        job.error_message = None
        job.finished_at = None
        await self.db.commit()
        return job, token

    async def fail_attempt(self, job_id: UUID, token: UUID, exc: Exception) -> bool:
        job = await self.db.scalar(select(ProcurementJob).where(
            ProcurementJob.id == job_id, ProcurementJob.tenant_id == self.user.tenant_id,
        ).with_for_update().execution_options(populate_existing=True))
        if not self.attempt_is_current(job, token):
            return False
        await fail_attempt_trace(self.db, job, code=type(exc).__name__, detail=str(exc))
        job.status = "FAILED"
        job.progress = 100
        job.error_code = type(exc).__name__
        job.error_message = str(exc)[:4000]
        job.finished_at = datetime.now(timezone.utc)
        job.claim_token = None
        job.lease_expires_at = None
        await self.db.commit()
        return True

    async def get(self, job_id: UUID) -> ProcurementJob:
        job = await self.db.scalar(
            select(ProcurementJob).where(
                ProcurementJob.id == job_id,
                ProcurementJob.tenant_id == self.user.tenant_id,
            )
        )
        if job is None:
            raise MegalodonException(
                ErrorCode.TAREA_NO_ENCONTRADA,
                "Job de Procurement no encontrado.",
                404,
            )
        return job
