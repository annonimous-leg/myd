from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from uuid import UUID, uuid4

from sqlalchemy import select, or_, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode, MegalodonException
from app.engines.ia.ocr_metrados import ResultadoOCR
from app.models.ocr_job import OCRJob, OCRJobStatus
from app.models.presupuesto import Presupuesto
from app.models.user import User
from app.services.ocr_service import OCRService
from app.workers.celery_app import celery_app


OCR_MAX_ATTEMPTS = 3
OCR_HARD_LIMIT_SECONDS = 300
OCR_STALE_GRACE_SECONDS = 60


class OCRJobService:
    """Durabilidad del dominio OCR sin compartir estado de jobs con otros dominios."""

    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id

    async def validar_presupuesto(self, presupuesto_id: UUID | None) -> None:
        if presupuesto_id is None:
            return
        exists = await self.db.scalar(
            select(Presupuesto.id).where(
                Presupuesto.id == presupuesto_id,
                Presupuesto.tenant_id == self.tenant_id,
            )
        )
        if exists is None:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                "Presupuesto no encontrado en el tenant.",
                status_code=404,
            )

    @staticmethod
    def request_hash(
        *,
        source_bytes: bytes,
        filename: str,
        presupuesto_id: UUID | None,
    ) -> str:
        payload = {
            "source_sha256": sha256(source_bytes).hexdigest(),
            "filename": filename,
            "presupuesto_id": str(presupuesto_id) if presupuesto_id else None,
        }
        return sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    async def recuperar_por_idempotencia(
        self,
        key: str | None,
        request_hash: str,
    ) -> OCRJob | None:
        if not key:
            return None
        row = await self.db.scalar(
            select(OCRJob).where(
                OCRJob.tenant_id == self.tenant_id,
                OCRJob.idempotency_key == key,
            )
        )
        if row is None:
            return None
        if row.request_hash != request_hash:
            raise MegalodonException(
                ErrorCode.CONFLICT,
                "La Idempotency-Key OCR ya fue utilizada para otra entrada.",
                status_code=409,
            )
        return row

    async def crear(
        self,
        *,
        user: User,
        job_id: UUID,
        filename: str,
        content_type: str | None,
        storage_path: str,
        source_bytes: bytes,
        presupuesto_id: UUID | None,
        idempotency_key: str | None = None,
        request_hash: str | None = None,
    ) -> tuple[OCRJob, bool]:
        await self.validar_presupuesto(presupuesto_id)
        req_hash = request_hash or self.request_hash(
            source_bytes=source_bytes,
            filename=filename,
            presupuesto_id=presupuesto_id,
        )
        existing = await self.recuperar_por_idempotencia(
            idempotency_key, req_hash
        )
        if existing is not None:
            return existing, True

        row = OCRJob(
            id=job_id,
            tenant_id=self.tenant_id,
            creado_por_id=user.id,
            actualizado_por_id=user.id,
            task_id=str(job_id),
            idempotency_key=idempotency_key,
            request_hash=req_hash,
            filename=filename,
            content_type=content_type,
            storage_path=storage_path,
            source_sha256=sha256(source_bytes).hexdigest(),
            size_bytes=len(source_bytes),
            presupuesto_id=presupuesto_id,
            status=OCRJobStatus.PENDING.value,
            progress=0,
            attempts=0,
            result={},
        )
        self.db.add(row)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            existing = await self.recuperar_por_idempotencia(
                idempotency_key, req_hash
            )
            if existing is not None:
                return existing, True
            raise
        return row, False

    async def publicar(self, job_id: UUID) -> OCRJob:
        """Publica un PENDING bajo lock sólo del OCRJob correspondiente."""
        job = await self.db.scalar(
            select(OCRJob)
            .where(
                OCRJob.id == job_id,
                OCRJob.tenant_id == self.tenant_id,
            )
            .with_for_update().execution_options(populate_existing=True)
        )
        if job is None:
            raise MegalodonException(
                ErrorCode.TAREA_NO_ENCONTRADA,
                "Trabajo OCR no encontrado.",
                status_code=404,
            )
        if job.status in {
            OCRJobStatus.QUEUED.value,
            OCRJobStatus.RUNNING.value,
            OCRJobStatus.SUCCEEDED.value,
        }:
            return job
        if job.status != OCRJobStatus.PENDING.value:
            raise MegalodonException(
                ErrorCode.CONFLICT,
                f"Trabajo OCR no publicable desde {job.status}.",
                status_code=409,
            )

        try:
            celery_app.send_task(
                "app.workers.ocr_tasks.extraer_metrados_ocr",
                args=[str(job.id)],
                task_id=job.task_id,
            )
        except Exception as exc:
            job.error_code = "ENQUEUE_FAILED"
            job.error_message = str(exc)[:4000]
            await self.db.commit()
            raise MegalodonException(
                ErrorCode.ARCHIVO_ERROR,
                "No se pudo confirmar la publicación OCR; quedó pendiente para reconciliación.",
                status_code=503,
                details={"job_id": str(job.id), "task_id": job.task_id},
            ) from exc

        job.status = OCRJobStatus.QUEUED.value
        job.queued_at = datetime.now(timezone.utc)
        job.error_code = None
        job.error_message = None
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def get_by_task(self, task_id: str) -> OCRJob:
        job = await self.db.scalar(
            select(OCRJob).where(
                OCRJob.task_id == task_id,
                OCRJob.tenant_id == self.tenant_id,
            )
        )
        if job is None:
            raise MegalodonException(
                ErrorCode.TAREA_NO_ENCONTRADA,
                "Trabajo OCR no encontrado.",
                status_code=404,
            )
        return job

    async def claim(self, job_id: UUID) -> tuple[OCRJob | None, str | None]:
        job = await self.db.scalar(
            select(OCRJob)
            .where(
                OCRJob.id == job_id,
                OCRJob.tenant_id == self.tenant_id,
            )
            .with_for_update().execution_options(populate_existing=True)
        )
        if job is None:
            return None, None
        if job.status not in {
            OCRJobStatus.PENDING.value,
            OCRJobStatus.QUEUED.value,
        }:
            return job, None
        if job.attempts >= OCR_MAX_ATTEMPTS:
            job.status = OCRJobStatus.FAILED.value
            job.error_code = "MAX_ATTEMPTS"
            job.error_message = "Se agotaron los intentos de OCR."
            job.finished_at = datetime.now(timezone.utc)
            await self.db.commit()
            return job, None

        token = str(uuid4())
        job.attempts += 1
        job.claim_token = token
        job.status = OCRJobStatus.RUNNING.value
        job.progress = max(job.progress, 1)
        job.started_at = datetime.now(timezone.utc)
        job.finished_at = None
        job.error_code = None
        job.error_message = None
        await self.db.commit()
        await self.db.refresh(job)
        return job, token

    @staticmethod
    def _vigente(job: OCRJob | None, token: str) -> bool:
        if job is None or job.status != OCRJobStatus.RUNNING.value or job.claim_token != token:
            return False
        if job.started_at is None:
            return False
        started = job.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        return started + timedelta(seconds=OCR_HARD_LIMIT_SECONDS + OCR_STALE_GRACE_SECONDS) > datetime.now(timezone.utc)

    async def completar(
        self,
        job_id: UUID,
        claim_token: str,
        resultado: ResultadoOCR,
    ) -> bool:
        """Persiste sugerencias y resultado en la misma transacción."""
        try:
            job = await self.db.scalar(
                select(OCRJob)
                .where(
                    OCRJob.id == job_id,
                    OCRJob.tenant_id == self.tenant_id,
                )
                .with_for_update().execution_options(populate_existing=True)
            )
            if not self._vigente(job, claim_token):
                await self.db.rollback()
                return False

            if job.presupuesto_id is not None and resultado.metrados:
                await OCRService(
                    self.db, tenant_id=job.tenant_id
                )._crear_partidas_sugeridas(
                    job.presupuesto_id,
                    resultado,
                    auto_commit=False,
                )

            if not self._vigente(job, claim_token):
                await self.db.rollback()
                return False
            job.result = {
                "status": "SUCCESS",
                "filename": job.filename,
                "presupuesto_id": str(job.presupuesto_id) if job.presupuesto_id else None,
                "total_metrados": resultado.total_metrados,
                "confianza_promedio": resultado.confianza_promedio,
                "metrados": [m.to_dict() for m in resultado.metrados],
                "paginas_procesadas": resultado.paginas_procesadas,
                "errores": resultado.errores,
            }
            job.status = OCRJobStatus.SUCCEEDED.value
            job.progress = 100
            job.claim_token = None
            job.finished_at = datetime.now(timezone.utc)
            await self.db.commit()
            return True
        except Exception:
            await self.db.rollback()
            raise

    async def fallar(
        self,
        job_id: UUID,
        claim_token: str,
        exc: Exception,
    ) -> str:
        job = await self.db.scalar(
            select(OCRJob)
            .where(
                OCRJob.id == job_id,
                OCRJob.tenant_id == self.tenant_id,
            )
            .with_for_update().execution_options(populate_existing=True)
        )
        if not self._vigente(job, claim_token):
            return "STALE"

        job.error_code = getattr(
            getattr(exc, "code", None), "value", type(exc).__name__
        )
        job.error_message = str(exc)[:4000]
        job.claim_token = None
        if job.attempts >= OCR_MAX_ATTEMPTS:
            job.status = OCRJobStatus.FAILED.value
            job.finished_at = datetime.now(timezone.utc)
        else:
            job.status = OCRJobStatus.PENDING.value
            job.progress = 0
            job.started_at = None
        await self.db.commit()
        return job.status

    @classmethod
    async def reconciliar(cls, db: AsyncSession, *, limit: int = 50) -> int:
        now = datetime.now(timezone.utc)
        stale_before = now - timedelta(
            seconds=OCR_HARD_LIMIT_SECONDS + OCR_STALE_GRACE_SECONDS
        )

        stale = (
            await db.scalars(
                select(OCRJob)
                .where(
                    or_(
                        (OCRJob.status == OCRJobStatus.RUNNING.value) &
                        (func.coalesce(OCRJob.started_at, OCRJob.updated_at) < stale_before),
                        (OCRJob.status == OCRJobStatus.QUEUED.value) &
                        (OCRJob.claim_token.is_(None)) &
                        (func.coalesce(OCRJob.queued_at, OCRJob.updated_at) < stale_before),
                    ),
                )
                .order_by(OCRJob.started_at)
                .limit(limit)
                .with_for_update(skip_locked=True).execution_options(populate_existing=True)
            )
        ).all()
        for job in stale:
            job.claim_token = None
            job.queued_at = None
            if job.attempts >= OCR_MAX_ATTEMPTS:
                job.status = OCRJobStatus.FAILED.value
                job.error_code = "MAX_ATTEMPTS"
                job.error_message = "Se agotaron los intentos de OCR."
                job.finished_at = now
            else:
                job.status = OCRJobStatus.PENDING.value
                job.progress = 0
                job.started_at = None
                job.error_code = "WORKER_LEASE_EXPIRED"
                job.error_message = "El worker OCR venció; el trabajo será republicado."
        if stale:
            await db.commit()

        ids = (
            await db.scalars(
                select(OCRJob.id)
                .where(OCRJob.status == OCRJobStatus.PENDING.value)
                .order_by(OCRJob.created_at)
                .limit(limit)
            )
        ).all()

        published = 0
        for job_id in ids:
            row = await db.get(OCRJob, job_id)
            if row is None:
                continue
            service = cls(db, row.tenant_id)
            try:
                published_row = await service.publicar(job_id)
            except MegalodonException:
                continue
            if published_row.status == OCRJobStatus.QUEUED.value:
                published += 1
        return published
