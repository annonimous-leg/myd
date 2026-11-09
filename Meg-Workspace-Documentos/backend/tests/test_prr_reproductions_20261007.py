from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.errors import MegalodonException
from app.engines.programacion.cpm import Actividad, MotorCPM, TipoDependencia
from app.models.expediente import ExpedienteObra
from app.models.procurement import TenderPackage, TenderState
from app.models.procurement_jobs import ProcurementJob
from app.models.montecarlo import EstadoMonteCarlo, MonteCarloRun
from app.models.presupuesto import Presupuesto
from app.models.programacion import ProgramaObra
from app.models.user import User, UserRole
from app.schemas.contrato import ContratoUpdate, ConvenioModificatorioCreate, EntregableCreate
from app.schemas.procurement.schemas import ApprovalCreate
from app.services.procurement.jobs import ProcurementJobService
from app.services.procurement.service import ProcurementService
from app.services.montecarlo_service import MonteCarloService
from app.services.programacion_service import ProgramacionService


def _expediente(*, tenant_id, user_id, suffix: str) -> ExpedienteObra:
    return ExpedienteObra(
        tenant_id=tenant_id,
        creado_por_id=user_id,
        actualizado_por_id=user_id,
        identificador=f"AUDIT-{suffix}-{uuid4().hex[:8]}",
        titulo=f"Auditoria {suffix}",
        organo="ORG TEST",
        unidad_administrativa="UA TEST",
        serie_documental="OBRA_PUBLICA",
        subserie_documental="LICITACION",
        responsable_id=user_id,
    )


def _wire_successors(*activities: Actividad) -> None:
    by_id = {a.id: a for a in activities}
    for activity in activities:
        for predecessor in activity.predecesoras:
            if predecessor in by_id:
                by_id[predecessor].sucesoras.append(activity.id)


def test_cpm_project_duration_is_full_sequential_span_not_longest_activity():
    start = datetime(2026, 10, 7, 8, 0, 0)
    a = Actividad(id="A", nombre="A", duracion=2)
    b = Actividad(id="B", nombre="B", duracion=3, predecesoras=["A"])
    _wire_successors(a, b)
    motor = MotorCPM()
    motor.agregar_actividad(a)
    motor.agregar_actividad(b)

    result = motor.calcular_cpm(start, usar_calendario=False)

    assert result.duracion_total == 5


def test_cpm_honors_start_to_start_dependency():
    start = datetime(2026, 10, 7, 8, 0, 0)
    a = Actividad(id="A", nombre="A", duracion=4)
    b = Actividad(
        id="B",
        nombre="B",
        duracion=2,
        predecesoras=["A"],
        dependencias={"A": TipoDependencia.INICIO_INICIO},
    )
    _wire_successors(a, b)
    motor = MotorCPM()
    motor.agregar_actividad(a)
    motor.agregar_actividad(b)

    result = motor.calcular_cpm(start, usar_calendario=False)

    assert result.actividades["B"].inicio_temprano == start


def test_cpm_rejects_duplicate_activity_identifiers_instead_of_overwriting():
    motor = MotorCPM()
    motor.agregar_actividad(Actividad(id="A", nombre="primera", duracion=1))

    with pytest.raises(MegalodonException):
        motor.agregar_actividad(Actividad(id="A", nombre="segunda", duracion=9))


@pytest.mark.asyncio
async def test_pert_keeps_deterministic_predecessors_in_mixed_program(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    expediente = _expediente(tenant_id=tenant.id, user_id=user.id, suffix="PERT-MIXED")
    db_session.add(expediente)
    await db_session.commit()
    service = ProgramacionService(db_session, tenant.id, actor_id=user.id)
    program = await service.crear_programa(
        expediente_id=expediente.id, nombre="Programa mixto",
        fecha_inicio=datetime(2026, 10, 7, 8, 0, 0),
        actividades_data=[
            {"id": "A", "nombre": "Determinista", "duracion": 2, "predecesoras": []},
            {"id": "B", "nombre": "PERT", "duracion": 3, "duracion_optimista": 2,
             "duracion_probable": 3, "duracion_pesimista": 4, "predecesoras": ["A"]},
        ], creado_por_id=user.id, tenant_id=tenant.id,
    )
    result = await service.calcular_pert(program.id, expediente.id, tenant_id=tenant.id)
    assert result.duracion_esperada >= 5


@pytest.mark.asyncio
async def test_crear_programa_rolls_back_persisted_rows_when_cpm_rejects_cycle(
    db_session, tenant_a_user
):
    tenant, user = tenant_a_user
    expediente = _expediente(tenant_id=tenant.id, user_id=user.id, suffix="CPM-ATOMIC")
    db_session.add(expediente)
    await db_session.commit()
    await db_session.refresh(expediente)
    expediente_id = expediente.id
    tenant_id = tenant.id
    user_id = user.id

    service = ProgramacionService(db_session, tenant_id)

    with pytest.raises(MegalodonException):
        await service.crear_programa(
            expediente_id=expediente_id,
            nombre="Programa ciclico",
            fecha_inicio=datetime(2026, 10, 7, 8, 0, 0),
            actividades_data=[
                {"id": "A", "nombre": "A", "duracion": 2, "predecesoras": ["B"]},
                {"id": "B", "nombre": "B", "duracion": 3, "predecesoras": ["A"]},
            ],
            creado_por_id=user_id,
            tenant_id=tenant_id,
        )

    persisted = (
        await db_session.execute(
            select(ProgramaObra).where(
                ProgramaObra.expediente_id == expediente_id,
                ProgramaObra.tenant_id == tenant_id,
            )
        )
    ).scalars().all()
    assert persisted == []


@pytest.mark.asyncio
async def test_one_reviewer_cannot_satisfy_two_distinct_procurement_approval_roles(
    db_session, tenant_a_user, monkeypatch
):
    tenant, creator = tenant_a_user
    reviewer = User(
        email=f"audit-reviewer-{uuid4().hex[:8]}@example.mx",
        hashed_password="not-used",
        full_name="Audit Reviewer",
        role=UserRole.REVISOR,
        tenant_id=tenant.id,
        is_active=True,
        is_verified=True,
    )
    db_session.add(reviewer)
    expediente = _expediente(tenant_id=tenant.id, user_id=creator.id, suffix="APPROVAL")
    db_session.add(expediente)
    await db_session.flush()
    tender = TenderPackage(
        tenant_id=tenant.id,
        creado_por_id=creator.id,
        actualizado_por_id=creator.id,
        expediente_id=expediente.id,
        identifier=f"AUD-APP-{uuid4().hex[:8]}",
        title="Approval segregation audit",
        state=TenderState.QA_READY.value,
        canonical_model={"approvals": {"required_roles": ["LEGAL", "FINANCE"]}},
        current_revision=1,
    )
    db_session.add(tender)
    await db_session.commit()
    await db_session.refresh(reviewer)
    await db_session.refresh(tender)

    service = ProcurementService(db_session, reviewer)

    async def readiness_is_satisfied(_tender_id):
        return {"ready": True, "findings": []}

    # This regression concerns separation of duties. The jurisdiction/source
    # readiness contract is covered independently and must not mask it.
    monkeypatch.setattr(service, "readiness", readiness_is_satisfied)

    await service.approval(
        tender.id,
        ApprovalCreate(role="LEGAL", decision="APPROVED"),
    )

    with pytest.raises(MegalodonException):
        await service.approval(
            tender.id,
            ApprovalCreate(role="FINANCE", decision="APPROVED"),
        )


@pytest.mark.asyncio
async def test_procurement_job_cannot_remain_queued_without_broker_publication(
    db_session, tenant_a_user, monkeypatch
):
    tenant, user = tenant_a_user
    expediente = _expediente(tenant_id=tenant.id, user_id=user.id, suffix="OUTBOX")
    db_session.add(expediente)
    await db_session.flush()
    tender = TenderPackage(
        tenant_id=tenant.id,
        creado_por_id=user.id,
        actualizado_por_id=user.id,
        expediente_id=expediente.id,
        identifier=f"AUD-JOB-{uuid4().hex[:8]}",
        title="Durable publication audit",
        state=TenderState.QA_READY.value,
        canonical_model={"facts": {"audit": True}},
        current_revision=1,
    )
    db_session.add(tender)
    await db_session.commit()
    await db_session.refresh(tender)

    def crash_after_database_commit(*_args, **_kwargs):
        raise SystemExit("simulated process death before broker publication")

    monkeypatch.setattr(
        "app.services.procurement.jobs.celery_app.send_task",
        crash_after_database_commit,
    )

    with pytest.raises(SystemExit):
        await ProcurementJobService(db_session, user).create_or_replay(
            tender,
            "RUN",
            "audit-crash-window",
        )

    job = await db_session.scalar(
        select(ProcurementJob).where(
            ProcurementJob.tender_id == tender.id,
            ProcurementJob.tenant_id == tenant.id,
        )
    )
    assert job is not None
    assert job.status == "PENDING"
    assert job.task_id == str(job.id)

    published_task_ids = []

    def broker_accepts(*_args, **kwargs):
        published_task_ids.append(kwargs["task_id"])
        return SimpleNamespace(id=kwargs["task_id"])

    monkeypatch.setattr(
        "app.services.procurement.jobs.celery_app.send_task",
        broker_accepts,
    )
    replayed_job, replayed = await ProcurementJobService(
        db_session, user
    ).create_or_replay(
        tender,
        "RUN",
        "audit-crash-window",
    )

    assert replayed is True
    assert replayed_job.id == job.id
    assert replayed_job.status == "QUEUED"
    assert replayed_job.task_id == str(job.id)
    assert published_task_ids == [str(job.id)]


@pytest.mark.parametrize(
    ("factory", "payload"),
    [
        (ContratoUpdate, {"monto_total": -1, "plazo_dias": -1}),
        (
            ConvenioModificatorioCreate,
            {
                "numero": "AUD-1",
                "tipo": "MONTO",
                "monto_nuevo": -1,
                "plazo_nuevo": -1,
            },
        ),
        (
            EntregableCreate,
            {
                "numero_estimacion": 1,
                "monto_ejecutado": -1,
                "avance_fisico": 1,
                "avance_financiero": 1,
            },
        ),
    ],
)
def test_contract_domain_rejects_negative_money_and_duration(factory, payload):
    with pytest.raises(ValidationError):
        factory(**payload)


def _montecarlo_run(*, tenant_id, user_id, estado: str) -> MonteCarloRun:
    return MonteCarloRun(
        tenant_id=tenant_id,
        creado_por_id=user_id,
        actualizado_por_id=user_id,
        task_id=str(uuid4()),
        idempotency_key=f"audit-{uuid4().hex[:12]}",
        request_hash="a" * 64,
        estado=estado,
        progreso=17,
        iteraciones=1000,
        seed=7,
        presupuesto_base=1000,
        presupuesto_maximo=1200,
        variables=[
            {
                "nombre": "riesgo",
                "distribucion": "normal",
                "parametros": {"media": 0.0, "desviacion": 0.01},
                "impacto": "costo_pct",
            }
        ],
        configuracion={
            "presupuesto_base": 1000,
            "presupuesto_maximo": 1200,
            "iteraciones": 1000,
            "variables": [
                {
                    "nombre": "riesgo",
                    "distribucion": "normal",
                    "parametros": {"media": 0.0, "desviacion": 0.01},
                    "impacto": "costo_pct",
                }
            ],
        },
    )


@pytest.mark.asyncio
async def test_montecarlo_late_progress_cannot_resurrect_cancelled_run(
    db_session, tenant_a_user
):
    tenant, user = tenant_a_user
    run = _montecarlo_run(
        tenant_id=tenant.id,
        user_id=user.id,
        estado=EstadoMonteCarlo.CANCELADO.value,
    )
    run.progreso = 41
    db_session.add(run)
    await db_session.commit()

    changed = await MonteCarloService(
        db_session, tenant.id
    ).actualizar_progreso(run.task_id, 90, token=uuid4())

    await db_session.refresh(run)
    assert changed is False
    assert run.estado == EstadoMonteCarlo.CANCELADO.value
    assert run.progreso == 41


@pytest.mark.asyncio
async def test_montecarlo_late_enqueue_ack_cannot_downgrade_running_worker(
    db_session, tenant_a_user
):
    tenant, user = tenant_a_user
    run = _montecarlo_run(
        tenant_id=tenant.id,
        user_id=user.id,
        estado=EstadoMonteCarlo.EN_PROCESO.value,
    )
    run.progreso = 35
    db_session.add(run)
    await db_session.commit()

    changed = await MonteCarloService(
        db_session, tenant.id
    ).marcar_encolado(run.id)

    await db_session.refresh(run)
    assert changed is False
    assert run.estado == EstadoMonteCarlo.EN_PROCESO.value
    assert run.progreso == 35


@pytest.mark.asyncio
async def test_montecarlo_pending_publication_reuses_persisted_task_id(
    db_session, tenant_a_user, monkeypatch
):
    tenant, user = tenant_a_user
    run = _montecarlo_run(
        tenant_id=tenant.id,
        user_id=user.id,
        estado=EstadoMonteCarlo.PENDIENTE.value,
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    sent = []

    def accept(*args, **kwargs):
        sent.append((args, kwargs))
        return SimpleNamespace(id=kwargs["task_id"])

    monkeypatch.setattr(
        "app.workers.celery_app.celery_app.send_task",
        accept,
    )

    published = await MonteCarloService(
        db_session, tenant.id
    ).publicar_pendiente(run)

    await db_session.refresh(run)
    assert published is True
    assert run.estado == EstadoMonteCarlo.ENCOLADO.value
    assert len(sent) == 1
    assert sent[0][1]["task_id"] == run.task_id
    assert sent[0][0][0] == "app.workers.montecarlo_tasks.ejecutar_simulacion"


@pytest.mark.asyncio
async def test_montecarlo_late_failure_cannot_overwrite_cancelled_run(
    db_session, tenant_a_user
):
    tenant, user = tenant_a_user
    run = _montecarlo_run(
        tenant_id=tenant.id,
        user_id=user.id,
        estado=EstadoMonteCarlo.CANCELADO.value,
    )
    db_session.add(run)
    await db_session.commit()

    changed = await MonteCarloService(
        db_session, tenant.id
    ).fallar(run.task_id, RuntimeError("late worker"), token=uuid4())

    await db_session.refresh(run)
    assert changed is False
    assert run.estado == EstadoMonteCarlo.CANCELADO.value
    assert run.error_mensaje is None


@pytest.mark.asyncio
async def test_montecarlo_expired_worker_cannot_write_into_reclaimed_attempt(
    db_session, tenant_a_user, monkeypatch
):
    tenant, user = tenant_a_user
    run = _montecarlo_run(tenant_id=tenant.id, user_id=user.id,
                          estado=EstadoMonteCarlo.PENDIENTE.value)
    db_session.add(run)
    await db_session.commit()
    run_id, task_id = str(run.id), run.task_id
    service = MonteCarloService(db_session, tenant.id)
    old_token = await service.marcar_en_proceso(run_id)
    assert old_token is not None
    assert await service.actualizar_progreso(task_id, 20, token=old_token)
    run.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
    await db_session.commit()

    published = []
    def accept(*args, **kwargs):
        published.append(kwargs["task_id"])
        return SimpleNamespace(id=kwargs["task_id"])
    monkeypatch.setattr("app.workers.celery_app.celery_app.send_task", accept)
    count = await MonteCarloService.reconciliar_pendientes(db_session)
    assert count == len(published)
    await db_session.refresh(run)
    assert run.estado == EstadoMonteCarlo.ENCOLADO.value
    assert run.execution_token is None
    # Recovery scans all tenants; previous tests may have independent PENDING runs.
    assert published.count(task_id) == 1

    new_token = await service.marcar_en_proceso(run_id)
    assert new_token is not None and new_token != old_token
    assert run.attempt == 2
    assert not await service.actualizar_progreso(task_id, 99, token=old_token)
    assert not await service.completar(task_id, {"old": True}, 1, token=old_token)
    assert not await service.fallar(task_id, RuntimeError("old"), token=old_token)
    assert await service.actualizar_progreso(task_id, 44, token=new_token)
    assert await service.completar(task_id, {"new": True}, 17, token=new_token)
    await db_session.refresh(run)
    assert run.resultado == {"new": True}
    assert run.estado == EstadoMonteCarlo.COMPLETADO.value


@pytest.mark.asyncio
async def test_montecarlo_run_and_budget_projection_commit_together(
    db_session, tenant_a_user
):
    tenant, user = tenant_a_user
    expediente = _expediente(tenant_id=tenant.id, user_id=user.id,
                            suffix="MONTE-ATOMIC")
    db_session.add(expediente)
    await db_session.flush()
    budget = Presupuesto(
        tenant_id=tenant.id,
        expediente_id=expediente.id,
        identificador=f"MONTE-{uuid4().hex[:8]}",
        nombre="Presupuesto de verificación",
        factor_indirecto=0,
        factor_utilidad=0,
        factor_impuesto=0.16,
    )
    db_session.add(budget)
    await db_session.flush()
    run = _montecarlo_run(tenant_id=tenant.id, user_id=user.id,
                          estado=EstadoMonteCarlo.PENDIENTE.value)
    run.presupuesto_id = budget.id
    run.expediente_id = expediente.id
    db_session.add(run)
    await db_session.commit()

    service = MonteCarloService(db_session, tenant.id)
    token = await service.marcar_en_proceso(str(run.id))
    assert token is not None
    assert await service.completar(run.task_id, {"p80": 1190}, 37, token=token)
    await db_session.refresh(run)
    await db_session.refresh(budget)
    assert run.estado == EstadoMonteCarlo.COMPLETADO.value
    assert run.resultado == {"p80": 1190}
    assert budget.resultado_montecarlo["run_id"] == str(run.id)
    assert budget.resultado_montecarlo["p80"] == 1190


@pytest.mark.asyncio
async def test_montecarlo_failed_budget_commit_rolls_back_run_completion(
    db_session, tenant_a_user
):
    tenant, user = tenant_a_user
    expediente = _expediente(tenant_id=tenant.id, user_id=user.id,
                            suffix="MONTE-ROLLBACK")
    db_session.add(expediente)
    await db_session.flush()
    budget = Presupuesto(
        tenant_id=tenant.id,
        expediente_id=expediente.id,
        identificador=f"MONTE-{uuid4().hex[:8]}",
        nombre="Presupuesto de rollback",
        factor_indirecto=0,
        factor_utilidad=0,
        factor_impuesto=0.16,
    )
    db_session.add(budget)
    await db_session.flush()
    run = _montecarlo_run(tenant_id=tenant.id, user_id=user.id,
                          estado=EstadoMonteCarlo.PENDIENTE.value)
    run.presupuesto_id = budget.id
    run.expediente_id = expediente.id
    db_session.add(run)
    await db_session.commit()

    service = MonteCarloService(db_session, tenant.id)
    token = await service.marcar_en_proceso(str(run.id))
    budget.factor_impuesto = 2
    with pytest.raises(IntegrityError):
        await service.completar(run.task_id, {"p80": 1200}, 14, token=token)
    await db_session.refresh(run)
    await db_session.refresh(budget)
    assert run.estado == EstadoMonteCarlo.EN_PROCESO.value
    assert run.resultado is None
    assert budget.resultado_montecarlo is None
    assert float(budget.factor_impuesto) == 0.16


@pytest.mark.asyncio
async def test_montecarlo_old_queued_run_is_reoffered_after_broker_loss(
    db_session, tenant_a_user, monkeypatch
):
    tenant, user = tenant_a_user
    run = _montecarlo_run(
        tenant_id=tenant.id,
        user_id=user.id,
        estado=EstadoMonteCarlo.ENCOLADO.value,
    )
    run.updated_at = datetime.now(timezone.utc) - timedelta(seconds=1800)
    db_session.add(run)
    await db_session.commit()
    task_id = run.task_id
    sent = []

    def accept(*args, **kwargs):
        sent.append(kwargs["task_id"])
        return SimpleNamespace(id=kwargs["task_id"])

    monkeypatch.setattr("app.workers.celery_app.celery_app.send_task", accept)
    assert await MonteCarloService.reconciliar_pendientes(
        db_session, limite=10, stale_after_seconds=1320
    ) == 1
    await db_session.refresh(run)
    assert run.estado == EstadoMonteCarlo.ENCOLADO.value
    assert run.attempt == 0
    assert sent == [task_id]
