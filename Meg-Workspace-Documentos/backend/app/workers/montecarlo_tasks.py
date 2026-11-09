from __future__ import annotations

"""Worker Celery para simulaciones Monte Carlo persistentes y auditables."""

import asyncio
import time
from uuid import UUID

import structlog

from app.engines.riesgo.monte_carlo import MotorMonteCarlo, VariableRiesgo
from app.workers.celery_app import celery_app

logger = structlog.get_logger()


class MonteCarloCancelled(Exception):
    """El resultado de este intento ya no es válido; no reintentar."""


@celery_app.task(bind=True, time_limit=1200, max_retries=2, acks_late=True, reject_on_worker_lost=True, track_started=True)
def ejecutar_simulacion(self, task_id: str, run_id: str, data: dict):
    started = time.perf_counter()
    claim_token: UUID | None = None

    async def _db_progress(progress: int) -> bool:
        from app.workers.database import AsyncSessionLocal
        from app.services.montecarlo_service import MonteCarloService

        async with AsyncSessionLocal() as db:
            return await MonteCarloService(db, UUID(data["_tenant_id"])).actualizar_progreso(task_id, progress, token=claim_token)

    async def _mark_started() -> UUID | None:
        from app.workers.database import AsyncSessionLocal
        from app.services.montecarlo_service import MonteCarloService
        async with AsyncSessionLocal() as db:
            return await MonteCarloService(db, UUID(data["_tenant_id"])).marcar_en_proceso(run_id)

    async def _is_cancelled() -> bool:
        from app.workers.database import AsyncSessionLocal
        from app.services.montecarlo_service import MonteCarloService
        async with AsyncSessionLocal() as db:
            return await MonteCarloService(db, UUID(data["_tenant_id"])).esta_cancelada(task_id)

    async def _mark_complete(resultado: dict, execution_ms: int) -> bool:
        from app.workers.database import AsyncSessionLocal
        from app.services.montecarlo_service import MonteCarloService
        async with AsyncSessionLocal() as db:
            return await MonteCarloService(db, UUID(data["_tenant_id"])).completar(task_id, resultado, execution_ms, token=claim_token)

    async def _mark_failed(exc: Exception, execution_ms: int) -> bool:
        from app.workers.database import AsyncSessionLocal
        from app.services.montecarlo_service import MonteCarloService
        async with AsyncSessionLocal() as db:
            return await MonteCarloService(db, UUID(data["_tenant_id"])).fallar(task_id, exc, execution_ms, token=claim_token)

    async def _prepare_retry() -> bool:
        from app.workers.database import AsyncSessionLocal
        from app.services.montecarlo_service import MonteCarloService
        async with AsyncSessionLocal() as db:
            return await MonteCarloService(db, UUID(data["_tenant_id"])).preparar_reintento(task_id, token=claim_token)

    try:
        claim_token = asyncio.run(_mark_started())
        if claim_token is None:
            return {"status": "SKIPPED_NOT_CLAIMED", "run_id": run_id, "task_id": task_id}
        self.update_state(state="PROGRESS", meta={"progress": 1, "status": "EN_PROCESO"})

        variables = [
            VariableRiesgo(
                nombre=v["nombre"],
                distribucion=v["distribucion"],
                parametros={k: float(val) for k, val in v["parametros"].items()},
                impacto=v.get("impacto", "costo_pct"),
            )
            for v in data["variables"]
        ]

        last_persisted = 0

        def on_progress(progress: int) -> None:
            nonlocal last_persisted
            if progress >= last_persisted + 5 or progress == 100:
                if not asyncio.run(_db_progress(progress)):
                    raise MonteCarloCancelled("El intento de Monte Carlo perdió su ejecución.")
                last_persisted = progress
                self.update_state(
                    state="PROGRESS",
                    meta={"progress": progress, "status": "EN_PROCESO"},
                )

        motor = MotorMonteCarlo(
            seed=int(data["seed"]),
            chunk_size=50_000,
        )
        resultado = motor.simular_presupuesto(
            presupuesto_base=float(data["presupuesto_base"]),
            variables=variables,
            iteraciones=int(data.get("iteraciones", 10_000)),
            presupuesto_maximo=float(data["presupuesto_maximo"]),
            plazo_base=int(data["plazo_base_dias"]) if data.get("plazo_base_dias") is not None else None,
            plazo_maximo=int(data["plazo_maximo_dias"]) if data.get("plazo_maximo_dias") is not None else None,
            progress_callback=on_progress,
            confidence_level=float(data.get("confidence_level", 0.95)),
            correlaciones=data.get("correlaciones") or None,
        )
        payload = resultado.to_dict()
        execution_ms = int((time.perf_counter() - started) * 1000)
        completed = asyncio.run(_mark_complete(payload, execution_ms))
        if not completed:
            if asyncio.run(_is_cancelled()):
                return {"status": "CANCELADO", "run_id": run_id, "task_id": task_id}
            return {"status": "IGNORED_STALE_ATTEMPT", "run_id": run_id, "task_id": task_id}
        return {
            "status": "SUCCESS",
            "run_id": run_id,
            "task_id": task_id,
            "execution_ms": execution_ms,
            "result": payload,
        }
    except MonteCarloCancelled:
        return {"status": "CANCELADO", "run_id": run_id, "task_id": task_id}
    except Exception as exc:
        execution_ms = int((time.perf_counter() - started) * 1000)
        if asyncio.run(_is_cancelled()):
            return {"status": "CANCELADO", "run_id": run_id, "task_id": task_id}
        logger.exception("montecarlo_task_failed", task_id=task_id, run_id=run_id, error=str(exc))
        if claim_token is None:
            raise
        if self.request.retries < self.max_retries:
            if asyncio.run(_prepare_retry()):
                raise self.retry(countdown=30 * (self.request.retries + 1), exc=exc)
            if asyncio.run(_is_cancelled()):
                return {"status": "CANCELADO", "run_id": run_id, "task_id": task_id}
            return {"status": "IGNORED_STALE_ATTEMPT", "run_id": run_id, "task_id": task_id}
        asyncio.run(_mark_failed(exc, execution_ms))
        raise
