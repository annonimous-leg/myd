from __future__ import annotations

import hashlib
import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode, MegalodonException
from app.core.entitlements import EntitlementsService
from app.models.expediente import ExpedienteObra
from app.models.montecarlo import EstadoMonteCarlo, MonteCarloRun
from app.models.presupuesto import Presupuesto
from app.models.programacion import ProgramaObra
from app.models.user import Tenant, User


class MonteCarloService:
    """Capa de negocio SaaS para corridas Monte Carlo."""

    def __init__(self, db: AsyncSession, tenant_id: UUID | None = None):
        self.db = db
        self.tenant_id = tenant_id

    def _effective_tenant(self, tenant_id: UUID | None = None) -> UUID:
        value = tenant_id or self.tenant_id
        if value is None:
            raise MegalodonException(ErrorCode.AUTH_ERROR, "Contexto tenant requerido para MonteCarloService", status_code=403)
        return value

    @staticmethod
    def request_hash(payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def _get_tenant(self, tenant_id: UUID) -> Tenant:
        tenant = await self.db.get(Tenant, tenant_id)
        if tenant is None or not tenant.is_active:
            raise MegalodonException(ErrorCode.AUTH_ERROR, "Tenant no disponible.", status_code=403)
        return tenant

    async def _validate_context(
        self,
        tenant_id: UUID,
        expediente_id: Optional[UUID],
        presupuesto_id: Optional[UUID],
        programa_id: Optional[UUID],
    ) -> tuple[Optional[UUID], Optional[UUID], Optional[UUID]]:
        expediente = None
        presupuesto = None
        programa = None

        if expediente_id is not None:
            expediente = await self.db.scalar(
                select(ExpedienteObra).where(
                    ExpedienteObra.id == expediente_id,
                    ExpedienteObra.tenant_id == tenant_id,
                )
            )
            if expediente is None:
                raise MegalodonException(ErrorCode.TAREA_NO_ENCONTRADA, "Expediente no encontrado en el tenant.", status_code=404)

        if presupuesto_id is not None:
            presupuesto = await self.db.scalar(select(Presupuesto).join(ExpedienteObra, ExpedienteObra.id == Presupuesto.expediente_id).where(Presupuesto.id == presupuesto_id, ExpedienteObra.tenant_id == tenant_id))
            if presupuesto is None:
                raise MegalodonException(ErrorCode.TAREA_NO_ENCONTRADA, "Presupuesto no encontrado.", status_code=404)
            if expediente is not None and presupuesto.expediente_id != expediente.id:
                raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "El presupuesto no pertenece al expediente.", status_code=422)
            budget_expediente = await self.db.scalar(
                select(ExpedienteObra).where(
                    ExpedienteObra.id == presupuesto.expediente_id,
                    ExpedienteObra.tenant_id == tenant_id,
                )
            )
            if budget_expediente is None:
                raise MegalodonException(ErrorCode.TAREA_NO_ENCONTRADA, "Presupuesto fuera del tenant.", status_code=404)
            expediente_id = budget_expediente.id

        if programa_id is not None:
            programa = await self.db.scalar(select(ProgramaObra).join(ExpedienteObra, ExpedienteObra.id == ProgramaObra.expediente_id).where(ProgramaObra.id == programa_id, ExpedienteObra.tenant_id == tenant_id))
            if programa is None:
                raise MegalodonException(ErrorCode.TAREA_NO_ENCONTRADA, "Programa de obra no encontrado.", status_code=404)
            program_expediente = await self.db.scalar(
                select(ExpedienteObra).where(
                    ExpedienteObra.id == programa.expediente_id,
                    ExpedienteObra.tenant_id == tenant_id,
                )
            )
            if program_expediente is None:
                raise MegalodonException(ErrorCode.TAREA_NO_ENCONTRADA, "Programa fuera del tenant.", status_code=404)
            if expediente_id is not None and programa.expediente_id != expediente_id:
                raise MegalodonException(ErrorCode.VALIDACION_FALLIDA, "El programa no pertenece al expediente.", status_code=422)
            expediente_id = program_expediente.id

        return expediente_id, presupuesto_id, programa_id

    async def recuperar_por_idempotencia(self, tenant_id: UUID, idempotency_key: str, request_hash: str) -> MonteCarloRun | None:
        run = await self.db.scalar(
            select(MonteCarloRun).where(
                MonteCarloRun.tenant_id == tenant_id,
                MonteCarloRun.idempotency_key == idempotency_key,
            )
        )
        if run is not None and run.request_hash != request_hash:
            raise MegalodonException(
                ErrorCode.PARAMETRO_INVALIDO,
                "La Idempotency-Key ya fue usada con una carga diferente.",
                status_code=409,
            )
        return run

    async def crear_corrida(
        self,
        *,
        user: User,
        payload: dict[str, Any],
        idempotency_key: Optional[str],
    ) -> tuple[MonteCarloRun, bool]:
        await self._get_tenant(user.tenant_id)
        request_hash = self.request_hash(payload)

        if idempotency_key:
            existente = await self.recuperar_por_idempotencia(user.tenant_id, idempotency_key, request_hash)
            if existente is not None:
                return existente, True

        expediente_id, presupuesto_id, programa_id = await self._validate_context(
            user.tenant_id,
            payload.get("expediente_id"),
            payload.get("presupuesto_id"),
            payload.get("programa_id"),
        )

        # Si el presupuesto es la fuente de verdad y no se envió base explícita,
        # se utiliza el monto aprobado/actual persistido.
        presupuesto_base = payload.get("presupuesto_base")
        if presupuesto_base is None and presupuesto_id:
            presupuesto = await self.db.scalar(
                select(Presupuesto)
                .join(ExpedienteObra, ExpedienteObra.id == Presupuesto.expediente_id)
                .where(
                    Presupuesto.id == presupuesto_id,
                    ExpedienteObra.tenant_id == user.tenant_id,
                )
            )
            if presupuesto is None:
                raise MegalodonException(
                    ErrorCode.TAREA_NO_ENCONTRADA,
                    "Presupuesto no encontrado en el tenant.",
                    status_code=404,
                )
            presupuesto_base = float(presupuesto.monto_total)
        if not presupuesto_base or presupuesto_base <= 0:
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "Se requiere un presupuesto_base > 0 o un presupuesto_id válido.")
        if float(payload["presupuesto_maximo"]) < float(presupuesto_base):
            raise MegalodonException(
                ErrorCode.PARAMETRO_INVALIDO,
                "presupuesto_maximo no puede ser menor que el presupuesto base efectivo.",
            )

        if payload.get("plazo_base_dias") is None and programa_id is not None:
            programa = await self.db.scalar(
                select(ProgramaObra)
                .join(ExpedienteObra, ExpedienteObra.id == ProgramaObra.expediente_id)
                .where(
                    ProgramaObra.id == programa_id,
                    ExpedienteObra.tenant_id == user.tenant_id,
                )
            )
            if programa and programa.duracion_plan_dias:
                payload["plazo_base_dias"] = int(programa.duracion_plan_dias)
        if payload.get("plazo_maximo_dias") is not None and payload.get("plazo_base_dias") is None:
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "plazo_maximo_dias requiere plazo_base_dias o programa_id con duración plan.")
        if payload.get("plazo_base_dias") is not None and payload.get("plazo_maximo_dias") is not None and payload["plazo_maximo_dias"] < payload["plazo_base_dias"]:
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "plazo_maximo_dias no puede ser menor que el plazo base efectivo.")

        variables = payload.get("variables") or []
        nombres = [str(v.get("nombre", "")).strip() for v in variables]
        if len(nombres) != len(set(nombres)):
            raise MegalodonException(ErrorCode.PARAMETRO_INVALIDO, "Las variables de riesgo deben tener nombres únicos.")

        limite = int(payload.get("iteraciones", 10_000))
        if limite > 100_000:
            entitlements = EntitlementsService(self.db)
            tenant = await self._get_tenant(user.tenant_id)
            plan = entitlements.calcular_plan_efectivo(tenant)
            limites = await entitlements.obtener_limites(plan)
            if not limites or not limites.permite_jobs_pesados:
                raise MegalodonException(
                    ErrorCode.VALIDACION_FALLIDA,
                    "Las simulaciones de alta carga requieren un plan con jobs pesados habilitados.",
                    status_code=402,
                    details={"plan": plan, "iteraciones": limite, "umbral": 100_000},
                )

        entitlements = EntitlementsService(self.db)
        tenant = await self._get_tenant(user.tenant_id)
        await entitlements.verificar_y_registrar_uso(
            tenant, "corridas_costeo", 1, auto_commit=False
        )

        task_id = str(uuid4())
        run = MonteCarloRun(
            tenant_id=user.tenant_id,
            creado_por_id=user.id,
            task_id=task_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            expediente_id=expediente_id,
            presupuesto_id=presupuesto_id,
            programa_id=programa_id,
            estado=EstadoMonteCarlo.PENDIENTE.value,
            progreso=0,
            iteraciones=limite,
            seed=int(payload["seed"] if payload.get("seed") is not None else secrets.randbelow(2_147_483_647)),
            presupuesto_base=float(presupuesto_base),
            presupuesto_maximo=float(payload["presupuesto_maximo"]),
            plazo_base_dias=payload.get("plazo_base_dias"),
            plazo_maximo_dias=payload.get("plazo_maximo_dias"),
            variables=payload["variables"],
            configuracion=payload,
        )
        self.db.add(run)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            if idempotency_key:
                existente = await self.recuperar_por_idempotencia(user.tenant_id, idempotency_key, request_hash)
                if existente is not None:
                    return existente, True
            raise
        await self.db.refresh(run)
        return run, False

    async def revertir_reserva_por_fallo_enqueue(self, tenant_id: UUID) -> None:
        tenant = await self._get_tenant(tenant_id)
        await EntitlementsService(self.db).revertir_uso(tenant, "corridas_costeo", 1)

    async def marcar_encolado(self, run_id: UUID, tenant_id: UUID | None = None) -> bool:
        """Confirma publicación sin degradar un worker que ya arrancó.

        El broker puede entregar el mensaje antes de que el request vuelva de
        send_task(). Por eso PENDIENTE -> ENCOLADO es condicional: si el
        worker ya movió la corrida a EN_PROCESO, esta confirmación tardía no
        puede regresarla ni poner el progreso en cero.
        """
        run = await self.db.scalar(
            select(MonteCarloRun)
            .where(
                MonteCarloRun.id == run_id,
                MonteCarloRun.tenant_id == self._effective_tenant(tenant_id),
            )
            .with_for_update().execution_options(populate_existing=True)
        )
        if run is None:
            return False
        if run.estado != EstadoMonteCarlo.PENDIENTE.value:
            return False
        run.estado = EstadoMonteCarlo.ENCOLADO.value
        run.progreso = 0
        await self.db.commit()
        return True

    @staticmethod
    def _token_vigente(run: MonteCarloRun, token: UUID) -> bool:
        return (
            run.estado == EstadoMonteCarlo.EN_PROCESO.value
            and run.execution_token is not None
            and run.execution_token == token
            and run.lease_expires_at is not None
            and (
                run.lease_expires_at.replace(tzinfo=timezone.utc)
                if run.lease_expires_at.tzinfo is None
                else run.lease_expires_at
            ) > datetime.now(timezone.utc)
        )

    @staticmethod
    def _next_lease() -> datetime:
        # Celery hard limit is 1200 s; grace accounts for delivery delay.
        return datetime.now(timezone.utc) + timedelta(seconds=1320)

    async def marcar_en_proceso(self, run_id: str, tenant_id: UUID | None = None) -> UUID | None:
        run = await self.db.scalar(
            select(MonteCarloRun).where(
                MonteCarloRun.id == UUID(run_id),
                MonteCarloRun.tenant_id == self._effective_tenant(tenant_id),
            ).with_for_update().execution_options(populate_existing=True)
        )
        if run is None or run.estado not in {
            EstadoMonteCarlo.PENDIENTE.value,
            EstadoMonteCarlo.ENCOLADO.value,
        }:
            await self.db.rollback()
            return None
        token = uuid4()
        run.attempt = (run.attempt or 0) + 1
        run.execution_token = token
        run.lease_expires_at = self._next_lease()
        run.estado = EstadoMonteCarlo.EN_PROCESO.value
        run.started_at = datetime.now(timezone.utc)
        run.finished_at = None
        run.progreso = max(run.progreso, 1)
        run.error_codigo = None
        run.error_mensaje = None
        await self.db.commit()
        return token

    async def actualizar_progreso(
        self, task_id: str, progreso: int, *,
        token: UUID, tenant_id: UUID | None = None,
    ) -> bool:
        run = await self.db.scalar(
            select(MonteCarloRun).where(
                MonteCarloRun.task_id == task_id,
                MonteCarloRun.tenant_id == self._effective_tenant(tenant_id),
            ).with_for_update().execution_options(populate_existing=True)
        )
        if run is None or not self._token_vigente(run, token):
            await self.db.rollback()
            return False
        run.progreso = max(run.progreso, max(0, min(99, int(progreso))))
        run.lease_expires_at = self._next_lease()
        await self.db.commit()
        return True

    async def completar(
        self, task_id: str, resultado: dict[str, Any], execution_ms: int, *,
        token: UUID, tenant_id: UUID | None = None,
    ) -> bool:
        """Run outcome and budget projection form one DB transaction."""
        try:
            run = await self.db.scalar(
                select(MonteCarloRun).where(
                    MonteCarloRun.task_id == task_id,
                    MonteCarloRun.tenant_id == self._effective_tenant(tenant_id),
                ).with_for_update().execution_options(populate_existing=True)
            )
            if run is None or not self._token_vigente(run, token):
                await self.db.rollback()
                return False
            if run.presupuesto_id is not None:
                presupuesto = await self.db.scalar(
                    select(Presupuesto).where(
                        Presupuesto.id == run.presupuesto_id,
                        Presupuesto.tenant_id == run.tenant_id,
                        Presupuesto.expediente_id == run.expediente_id,
                    ).with_for_update().execution_options(populate_existing=True)
                )
                if presupuesto is None:
                    raise MegalodonException(
                        ErrorCode.VALIDACION_FALLIDA,
                        "No existe el presupuesto asociado a la simulación.",
                    )
                presupuesto.resultado_montecarlo = {
                    "run_id": str(run.id),
                    "task_id": run.task_id,
                    "created_at": run.created_at.isoformat()
                    if run.created_at else None,
                    **resultado,
                }
            # Waiting for the budget lock may have consumed the remaining lease.
            if not self._token_vigente(run, token):
                await self.db.rollback()
                return False
            run.estado = EstadoMonteCarlo.COMPLETADO.value
            run.progreso = 100
            run.resultado = resultado
            run.execution_ms = execution_ms
            run.finished_at = datetime.now(timezone.utc)
            run.execution_token = None
            run.lease_expires_at = None
            await self.db.commit()
            return True
        except Exception:
            await self.db.rollback()
            raise

    async def cancelar(self, task_id: str, tenant_id: UUID) -> MonteCarloRun:
        run = await self.db.scalar(
            select(MonteCarloRun).where(
                MonteCarloRun.task_id == task_id,
                MonteCarloRun.tenant_id == tenant_id,
            ).with_for_update().execution_options(populate_existing=True)
        )
        if run is None:
            raise MegalodonException(
                ErrorCode.TAREA_NO_ENCONTRADA,
                "La simulación no existe en este tenant.",
                status_code=404,
            )
        if run.estado in {
            EstadoMonteCarlo.COMPLETADO.value,
            EstadoMonteCarlo.ERROR.value,
            EstadoMonteCarlo.CANCELADO.value,
        }:
            return run
        before = run.estado
        run.estado = EstadoMonteCarlo.CANCELADO.value
        if before in {EstadoMonteCarlo.PENDIENTE.value, EstadoMonteCarlo.ENCOLADO.value}:
            run.progreso = 0
        run.execution_token = None
        run.lease_expires_at = None
        run.finished_at = datetime.now(timezone.utc)
        await self.db.commit()
        return run

    async def esta_cancelada(self, task_id: str, tenant_id: UUID | None = None) -> bool:
        run = await self.db.scalar(select(MonteCarloRun.estado).where(MonteCarloRun.task_id == task_id, MonteCarloRun.tenant_id == self._effective_tenant(tenant_id)))
        return run == EstadoMonteCarlo.CANCELADO.value

    async def fallar(
        self, task_id: str, exc: Exception, execution_ms: int = 0, *,
        token: UUID, tenant_id: UUID | None = None,
    ) -> bool:
        run = await self.db.scalar(
            select(MonteCarloRun).where(
                MonteCarloRun.task_id == task_id,
                MonteCarloRun.tenant_id == self._effective_tenant(tenant_id),
            ).with_for_update().execution_options(populate_existing=True)
        )
        if run is None or not self._token_vigente(run, token):
            await self.db.rollback()
            return False
        run.estado = EstadoMonteCarlo.ERROR.value
        run.error_codigo = getattr(
            getattr(exc, "code", None), "value", "MONTECARLO_ERROR"
        )
        run.error_mensaje = str(exc)
        run.finished_at = datetime.now(timezone.utc)
        run.execution_ms = execution_ms
        run.execution_token = None
        run.lease_expires_at = None
        await self.db.commit()
        return True

    async def preparar_reintento(
        self, task_id: str, *, token: UUID, tenant_id: UUID | None = None,
    ) -> bool:
        run = await self.db.scalar(
            select(MonteCarloRun).where(
                MonteCarloRun.task_id == task_id,
                MonteCarloRun.tenant_id == self._effective_tenant(tenant_id),
            ).with_for_update().execution_options(populate_existing=True)
        )
        if run is None or not self._token_vigente(run, token):
            await self.db.rollback()
            return False
        run.estado = EstadoMonteCarlo.ENCOLADO.value
        run.progreso = 0
        run.started_at = None
        run.execution_token = None
        run.lease_expires_at = None
        await self.db.commit()
        return True

    @staticmethod
    def payload_worker(run: MonteCarloRun) -> dict[str, Any]:
        payload = dict(run.configuracion or {})
        payload["presupuesto_base"] = float(run.presupuesto_base)
        payload["seed"] = run.seed
        payload["_run_id"] = str(run.id)
        payload["_tenant_id"] = str(run.tenant_id)
        if run.plazo_base_dias is not None:
            payload["plazo_base_dias"] = run.plazo_base_dias
        if run.plazo_maximo_dias is not None:
            payload["plazo_maximo_dias"] = run.plazo_maximo_dias
        return payload

    async def publicar_pendiente(self, run: MonteCarloRun) -> bool:
        """Publica una intención durable sin tabla universal de jobs.

        El lock es local a MonteCarloRun: serializa replays/reconciliadores del
        mismo run. El worker puede aceptar PENDIENTE, así que una caída después
        de que el broker acepte pero antes del commit sigue siendo recuperable.
        """
        locked = await self.db.scalar(
            select(MonteCarloRun)
            .where(
                MonteCarloRun.id == run.id,
                MonteCarloRun.tenant_id == run.tenant_id,
            )
            .with_for_update().execution_options(populate_existing=True)
        )
        if locked is None or locked.estado != EstadoMonteCarlo.PENDIENTE.value:
            await self.db.rollback()
            return False

        from app.workers.celery_app import celery_app

        try:
            celery_app.send_task(
                "app.workers.montecarlo_tasks.ejecutar_simulacion",
                args=[locked.task_id, str(locked.id), self.payload_worker(locked)],
                task_id=locked.task_id,
            )
        except Exception:
            await self.db.rollback()
            raise

        locked.estado = EstadoMonteCarlo.ENCOLADO.value
        locked.progreso = 0
        await self.db.commit()
        return True

    @classmethod
    async def reconciliar_pendientes(
        cls,
        db: AsyncSession,
        *,
        limite: int = 50,
        stale_after_seconds: int = 1320,
    ) -> int:
        """Recupera la ventana BD->broker y ejecuciones muertas del dominio."""
        now = datetime.now(timezone.utc)

        stale = (
            await db.scalars(
                select(MonteCarloRun)
                .where(
                    MonteCarloRun.estado == EstadoMonteCarlo.EN_PROCESO.value,
                    MonteCarloRun.lease_expires_at.is_not(None),
                    MonteCarloRun.lease_expires_at < now,
                )
                .order_by(MonteCarloRun.lease_expires_at)
                .limit(limite)
                .with_for_update(skip_locked=True).execution_options(populate_existing=True)
            )
        ).all()
        for run in stale:
            run.estado = EstadoMonteCarlo.PENDIENTE.value
            run.progreso = 0
            run.started_at = None
            run.execution_token = None
            run.lease_expires_at = None
            run.error_codigo = "WORKER_LEASE_EXPIRED"
            run.error_mensaje = (
                "La ejecución excedió el límite del worker y será republicada."
            )
        if stale:
            await db.commit()

        # A broker acknowledgment does not prove that the message still
        # exists after Redis loss. Reoffer old, unclaimed ENCOLADO runs.
        # A live claim changes the status to EN_PROCESO under the same lock.
        queued_before = now - timedelta(seconds=stale_after_seconds)
        unclaimed = (
            await db.scalars(
                select(MonteCarloRun)
                .where(
                    MonteCarloRun.estado == EstadoMonteCarlo.ENCOLADO.value,
                    MonteCarloRun.execution_token.is_(None),
                    MonteCarloRun.updated_at < queued_before,
                )
                .order_by(MonteCarloRun.updated_at)
                .limit(limite)
                .with_for_update(skip_locked=True).execution_options(populate_existing=True)
            )
        ).all()
        for run in unclaimed:
            run.estado = EstadoMonteCarlo.PENDIENTE.value
            run.progreso = 0
            run.error_codigo = "QUEUE_DELIVERY_EXPIRED"
            run.error_mensaje = "La publicación no fue reclamada; se intentará entregar otra vez."
        if unclaimed:
            await db.commit()

        ids = (
            await db.scalars(
                select(MonteCarloRun.id)
                .where(MonteCarloRun.estado == EstadoMonteCarlo.PENDIENTE.value)
                .order_by(MonteCarloRun.created_at)
                .limit(limite)
            )
        ).all()

        publicados = 0
        for run_id in ids:
            run = await db.scalar(
                select(MonteCarloRun).where(
                    MonteCarloRun.id == run_id,
                    MonteCarloRun.estado == EstadoMonteCarlo.PENDIENTE.value,
                )
            )
            if run is None:
                continue
            service = cls(db, run.tenant_id)
            try:
                if await service.publicar_pendiente(run):
                    publicados += 1
            except Exception:
                # Sigue PENDIENTE. El siguiente tick reintenta sin convertir
                # una caída del broker en un ERROR de negocio.
                await db.rollback()
        return publicados
