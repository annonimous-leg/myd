from __future__ import annotations

"""API SaaS de simulación Monte Carlo: costo y plazo."""

from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.errors import ErrorCode, MegalodonException, TareaNoEncontradaException
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from app.engines.riesgo.monte_carlo import SUPPORTED_DISTRIBUTIONS, SUPPORTED_IMPACTS
from app.models.montecarlo import EstadoMonteCarlo, MonteCarloRun
from app.models.user import User
from app.services.montecarlo_service import MonteCarloService
from app.workers.celery_app import celery_app

router = APIRouter()


class VariableRiesgoInput(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=160)
    distribucion: Literal["normal", "triangular", "uniform", "lognormal", "beta"]
    parametros: Dict[str, float]
    impacto: Literal["costo_pct", "plazo_pct", "plazo_dias", "costo_y_plazo_pct"] = "costo_pct"


class SimulacionRequest(BaseModel):
    expediente_id: Optional[UUID] = None
    presupuesto_id: Optional[UUID] = None
    programa_id: Optional[UUID] = None
    presupuesto_base: Optional[float] = Field(default=None, gt=0)
    presupuesto_maximo: float = Field(..., gt=0)
    plazo_base_dias: Optional[int] = Field(default=None, gt=0)
    plazo_maximo_dias: Optional[int] = Field(default=None, gt=0)
    variables: List[VariableRiesgoInput] = Field(..., min_length=1, max_length=100)
    iteraciones: int = Field(default=10_000, ge=100, le=1_000_000)
    seed: Optional[int] = Field(default=None, ge=0, le=2_147_483_647)
    confidence_level: float = Field(default=0.95, ge=0.80, le=0.999)
    correlaciones: Dict[str, Dict[str, float]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_contract(self) -> "SimulacionRequest":
        if self.presupuesto_id is None and self.presupuesto_base is None:
            raise ValueError("Se requiere presupuesto_base o presupuesto_id.")
        if self.presupuesto_base is not None and self.presupuesto_maximo < self.presupuesto_base:
            raise ValueError("presupuesto_maximo no puede ser menor que presupuesto_base.")
        if self.plazo_maximo_dias is not None and self.plazo_base_dias is None:
            raise ValueError("plazo_maximo_dias requiere plazo_base_dias.")
        if self.plazo_base_dias is not None and self.plazo_maximo_dias is not None and self.plazo_maximo_dias < self.plazo_base_dias:
            raise ValueError("plazo_maximo_dias no puede ser menor que plazo_base_dias.")
        if self.plazo_base_dias is not None and not any(v.impacto in {"plazo_pct", "plazo_dias", "costo_y_plazo_pct"} for v in self.variables):
            raise ValueError("Se proporcionó plazo_base_dias pero ninguna variable tiene impacto de plazo.")
        return self


async def _obtener_run(db: AsyncSession, task_id: str, tenant_id: UUID) -> MonteCarloRun:
    run = await db.scalar(
        select(MonteCarloRun).where(
            MonteCarloRun.task_id == task_id,
            MonteCarloRun.tenant_id == tenant_id,
        )
    )
    if run is None:
        raise TareaNoEncontradaException()
    return run


@router.post("/simular")
async def simular_riesgo(
    data: SimulacionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key", max_length=128),
    _rate_limit: bool = Depends(rate_limit_strict),
):
    service = MonteCarloService(db)
    payload = data.model_dump(mode="json")
    run, existing = await service.crear_corrida(
        user=current_user,
        payload=payload,
        idempotency_key=idempotency_key,
    )

    try:
        if run.estado == EstadoMonteCarlo.PENDIENTE.value:
            await service.publicar_pendiente(run)
    except Exception as exc:
        # La intención ya quedó durable en MonteCarloRun. Un fallo del
        # broker no la convierte en ERROR ni libera el uso reservado: el
        # reconciliador del propio dominio la republicará con el mismo task_id.
        raise MegalodonException(
            ErrorCode.MONTECARLO_ERROR,
            "La simulación quedó pendiente y será republicada automáticamente.",
            status_code=503,
            details={"run_id": str(run.id), "task_id": run.task_id},
        ) from exc

    await db.refresh(run)
    return {
        "run_id": str(run.id),
        "task_id": run.task_id,
        "status": run.estado,
        "progreso": run.progreso,
        "idempotent_replay": existing,
        "message": (
            "Simulación registrada para procesamiento."
            if run.estado in {
                EstadoMonteCarlo.PENDIENTE.value,
                EstadoMonteCarlo.ENCOLADO.value,
            }
            else "Simulación recuperada."
        ),
    }


@router.get("/simular/{task_id}/status")
async def consultar_simulacion(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _rate_limit: bool = Depends(rate_limit_standard),
):
    run = await _obtener_run(db, task_id, current_user.tenant_id)
    response: Dict[str, Any] = {
        "run_id": str(run.id),
        "task_id": run.task_id,
        "status": run.estado,
        "progreso": run.progreso,
        "estado": run.estado,
        "iteraciones": run.iteraciones,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "execution_ms": run.execution_ms,
    }
    if run.estado == EstadoMonteCarlo.COMPLETADO.value:
        response["result"] = run.resultado
    elif run.estado == EstadoMonteCarlo.ERROR.value:
        response["error"] = {
            "codigo": run.error_codigo,
            "mensaje": run.error_mensaje,
        }
    return response


@router.post("/simular/{task_id}/cancel")
async def cancelar_simulacion(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _rate_limit: bool = Depends(rate_limit_standard),
):
    service = MonteCarloService(db)
    run = await service.cancelar(task_id, current_user.tenant_id)
    if run.estado == EstadoMonteCarlo.CANCELADO.value:
        try:
            celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")
        except Exception as exc:
            # La fila de BD ya está en CANCELADO; registrar el fallo del
            # revoke para diagnóstico sin revertir el estado de negocio.
            import structlog
            structlog.get_logger().warning("montecarlo_revoke_failed", task_id=task_id, error=str(exc))
    return {
        "run_id": str(run.id),
        "task_id": task_id,
        "status": run.estado,
    }


@router.get("/simulaciones")
async def listar_simulaciones(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
    _rate_limit: bool = Depends(rate_limit_standard),
):
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    result = await db.execute(
        select(MonteCarloRun)
        .where(MonteCarloRun.tenant_id == current_user.tenant_id)
        .order_by(MonteCarloRun.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    runs = result.scalars().all()
    return {
        "items": [
            {
                "run_id": str(run.id),
                "task_id": run.task_id,
                "estado": run.estado,
                "progreso": run.progreso,
                "iteraciones": run.iteraciones,
                "presupuesto_base": float(run.presupuesto_base),
                "presupuesto_maximo": float(run.presupuesto_maximo),
                "plazo_base_dias": run.plazo_base_dias,
                "plazo_maximo_dias": run.plazo_maximo_dias,
                "presupuesto_id": str(run.presupuesto_id) if run.presupuesto_id else None,
                "programa_id": str(run.programa_id) if run.programa_id else None,
                "expediente_id": str(run.expediente_id) if run.expediente_id else None,
                "created_at": run.created_at,
                "finished_at": run.finished_at,
            }
            for run in runs
        ],
        "limit": limit,
        "offset": offset,
    }
