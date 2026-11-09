from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import AsyncSessionLocal
from app.models.procurement import (
    PreparationRunStatus, PreparationStageStatus, TenderPackage,
    TenderPreparationRun, TenderPreparationStageRun,
)


PIPELINE_VERSION = "procurement-preparation-v2"


class PreparationRunTracker:
    """Durable tenant-scoped trace stored independently from the business transaction."""

    def __init__(self, db: AsyncSession, tender: TenderPackage, user_id: UUID, *, session_factory=None):
        self.session_factory = session_factory or AsyncSessionLocal
        self.db = db
        self.tender_id = tender.id
        self.tenant_id = tender.tenant_id
        self.user_id = user_id
        self.run_id: UUID | None = None
        self.correlation_id: str | None = None
        self._active_stage_id: UUID | None = None

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    async def start(self, correlation_id: str | None = None) -> TenderPreparationRun:
        self.correlation_id = correlation_id or uuid4().hex
        async with self.session_factory() as trace_db:
            run = TenderPreparationRun(
                tender_id=self.tender_id,
                tenant_id=self.tenant_id,
                correlation_id=self.correlation_id,
                pipeline_version=PIPELINE_VERSION,
                status=PreparationRunStatus.RUNNING.value,
                started_at=self._now(),
                creado_por_id=self.user_id,
                actualizado_por_id=self.user_id,
            )
            trace_db.add(run)
            await trace_db.commit()
            await trace_db.refresh(run)
            self.run_id = run.id
            return run

    async def begin_stage(
        self,
        stage: str,
        *,
        input_refs: dict[str, Any] | None = None,
        rule_version: str | None = None,
        engine_version: str | None = None,
    ) -> TenderPreparationStageRun:
        if self.run_id is None:
            raise RuntimeError("Preparation run no iniciado")
        async with self.session_factory() as trace_db:
            run = await trace_db.scalar(select(TenderPreparationRun).where(
                TenderPreparationRun.id == self.run_id,
                TenderPreparationRun.tenant_id == self.tenant_id,
            ))
            if run is None:
                raise RuntimeError("Preparation run no encontrado en el tenant")
            run.current_stage = stage
            run.updated_at = datetime.now(timezone.utc)
            stage_run = TenderPreparationStageRun(
                preparation_run_id=run.id,
                tenant_id=self.tenant_id,
                stage=stage,
                status=PreparationStageStatus.RUNNING.value,
                input_refs=input_refs or {},
                output_refs={},
                rule_version=rule_version,
                engine_version=engine_version,
                started_at=self._now(),
            )
            trace_db.add(stage_run)
            await trace_db.commit()
            await trace_db.refresh(stage_run)
            self._active_stage_id = stage_run.id
            return stage_run

    async def finish_stage(
        self,
        *,
        status: str,
        output_refs: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_detail: str | None = None,
    ) -> None:
        if self.run_id is None or self._active_stage_id is None:
            raise RuntimeError("No existe una etapa activa")
        async with self.session_factory() as trace_db:
            stage_run = await trace_db.scalar(select(TenderPreparationStageRun).where(
                TenderPreparationStageRun.id == self._active_stage_id,
                TenderPreparationStageRun.tenant_id == self.tenant_id,
                TenderPreparationStageRun.preparation_run_id == self.run_id,
            ))
            if stage_run is None:
                raise RuntimeError("StageRun no encontrado en el tenant")
            stage_run.status = status
            stage_run.output_refs = output_refs or {}
            stage_run.error_code = error_code
            stage_run.error_detail = error_detail
            stage_run.finished_at = self._now()
            run = await trace_db.scalar(select(TenderPreparationRun).where(
                TenderPreparationRun.id == self.run_id,
                TenderPreparationRun.tenant_id == self.tenant_id,
            ))
            if run is not None:
                run.current_stage = None
                run.updated_at = datetime.now(timezone.utc)
            await trace_db.commit()
        self._active_stage_id = None

    async def finish(
        self,
        status: str,
        *,
        failure_code: str | None = None,
        failure_detail: str | None = None,
        atomic: bool = False,
    ) -> None:
        if self.run_id is None:
            raise RuntimeError("Preparation run no iniciado")
        if atomic:
            # Readiness is part of the same transaction as the tender and job.
            # Earlier stage diagnostics remain independently durable.
            await self._finish_in(self.db, status, failure_code, failure_detail)
            await self.db.flush()
        else:
            async with self.session_factory() as trace_db:
                await self._finish_in(trace_db, status, failure_code, failure_detail)
                await trace_db.commit()

    async def _finish_in(self, trace_db, status, failure_code, failure_detail):
        run = await trace_db.scalar(select(TenderPreparationRun).where(
            TenderPreparationRun.id == self.run_id,
            TenderPreparationRun.tenant_id == self.tenant_id,
        ).with_for_update().execution_options(populate_existing=True))
        if run is None:
            raise RuntimeError("Preparation run no encontrado en el tenant")
        run.status = status
        run.failure_code = failure_code
        run.failure_detail = failure_detail
        run.current_stage = None
        run.finished_at = self._now()
        run.updated_at = datetime.now(timezone.utc)


def attempt_correlation(job_id: UUID, token: UUID) -> str:
    return f"job:{job_id}:attempt:{token}"


async def fail_attempt_trace(db: AsyncSession, job, *, code: str, detail: str) -> None:
    """Fail only the trace belonging to this durable claim, in its transaction."""
    if job.claim_token is None:
        return
    runs = (await db.scalars(select(TenderPreparationRun).where(
        TenderPreparationRun.tenant_id == job.tenant_id,
        TenderPreparationRun.tender_id == job.tender_id,
        TenderPreparationRun.correlation_id == attempt_correlation(job.id, job.claim_token),
        TenderPreparationRun.status == PreparationRunStatus.RUNNING.value,
    ).with_for_update().execution_options(populate_existing=True))).all()
    for run in runs:
        run.status = PreparationRunStatus.FAILED.value
        run.failure_code, run.failure_detail = code, detail[:4000]
        run.finished_at = datetime.now(timezone.utc).isoformat()
        run.current_stage = None
        stages = (await db.scalars(select(TenderPreparationStageRun).where(
            TenderPreparationStageRun.tenant_id == job.tenant_id,
            TenderPreparationStageRun.preparation_run_id == run.id,
            TenderPreparationStageRun.status == PreparationStageStatus.RUNNING.value,
        ).with_for_update().execution_options(populate_existing=True))).all()
        for stage in stages:
            stage.status = PreparationStageStatus.FAILED.value
            stage.error_code, stage.error_detail = code, detail[:4000]
            stage.finished_at = run.finished_at
