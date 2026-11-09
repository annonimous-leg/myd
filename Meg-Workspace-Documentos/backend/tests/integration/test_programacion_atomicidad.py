"""Regression: schedule edits and CPM validation are one transaction."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.core.errors import MegalodonException
from app.models.programacion import ActividadPrograma
from app.services.programacion_service import ProgramacionService
from tests.integration.test_closure_two_tenants import make_expediente


@pytest.mark.asyncio
async def test_cycle_edit_rolls_back_activity_and_cpm(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    expediente = make_expediente(tenant, user)
    db_session.add(expediente)
    await db_session.commit()

    service = ProgramacionService(
        db_session,
        tenant.id,
        actor_id=user.id,
    )
    program = await service.crear_programa(
        expediente_id=expediente.id,
        nombre="Programa atómico",
        fecha_inicio=datetime(2026, 10, 13, tzinfo=timezone.utc),
        actividades_data=[
            {
                "id": "A",
                "nombre": "Actividad A",
                "duracion": 2,
                "predecesoras": [],
            },
            {
                "id": "B",
                "nombre": "Actividad B",
                "duracion": 2,
                "predecesoras": ["A"],
            },
        ],
        creado_por_id=user.id,
        tenant_id=tenant.id,
    )
    original_cpm = program.resultado_cpm
    program_id = program.id

    with pytest.raises(MegalodonException) as exc:
        await service.actualizar_actividad(
            program_id,
            expediente.id,
            "A",
            {"predecesoras": ["B"]},
            tenant_id=tenant.id,
        )
    assert "circular" in str(exc.value).lower()

    db_session.expire_all()
    a = await db_session.scalar(
        select(ActividadPrograma).where(
            ActividadPrograma.programa_id == program_id,
            ActividadPrograma.identificador == "A",
        )
    )
    assert a.predecesoras == []

    refreshed = await service._get_programa_con_actividades(program_id)
    assert refreshed.resultado_cpm == original_cpm
