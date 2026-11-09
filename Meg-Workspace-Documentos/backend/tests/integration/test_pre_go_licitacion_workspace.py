"""Legacy authority data stays stored; no official authority workspace is exposed by Megalodon."""
from uuid import uuid4

import pytest

from app.models.licitacion import EstadoLicitacion, Licitacion, Proposicion, TipoProcedimiento
from app.models.proveedor import Proveedor, TipoPersona
from app.models.user import UserRole
from tests.conftest import _create_tenant_and_user, _login
from tests.integration.test_closure_two_tenants import make_expediente


@pytest.mark.asyncio
async def test_legacy_licitacion_rows_are_preserved_but_authority_routes_are_unavailable(async_client, db_session):
    tenant, user = await _create_tenant_and_user(
        db_session, "legacy-authority-history", "history@example.mx", role=UserRole.ADMIN,
    )
    expediente = make_expediente(tenant, user)
    db_session.add(expediente)
    await db_session.flush()

    provider = Proveedor(
        tenant_id=tenant.id,
        tipo_persona=TipoPersona.MORAL.value,
        rfc=("T" + uuid4().hex[:11]).upper(),
        razon_social="Proveedor histórico",
        creado_por_id=user.id,
        actualizado_por_id=user.id,
    )
    licitacion = Licitacion(
        tenant_id=tenant.id,
        expediente_id=expediente.id,
        jurisdiction_code="MX-FED-OBRA",
        folio=f"LEG-{uuid4().hex[:8]}",
        tipo_procedimiento=TipoProcedimiento.OBRA_PUBLICA.value,
        estado=EstadoLicitacion.APERTURA.value,
        objeto="Registro histórico que se conserva",
        monto_estimado=1000,
        plazo_dias=30,
        bases="Bases históricas",
        bases_congeladas=True,
        matriz_evaluacion={"tecnico": {"experiencia": {"ponderacion": 100}}},
        creado_por_id=user.id,
        actualizado_por_id=user.id,
    )
    db_session.add_all([provider, licitacion])
    await db_session.flush()

    proposition = Proposicion(
        tenant_id=tenant.id,
        licitacion_id=licitacion.id,
        proveedor_id=provider.id,
        monto=1000,
        plazo_dias=30,
        sobres_digitales={"tecnico": {"experiencia": 100}},
        estado="RECIBIDA",
        firma_valida=True,
        integridad_valida=True,
        cumplimiento_documental=True,
        creado_por_id=user.id,
        actualizado_por_id=user.id,
    )
    db_session.add(proposition)
    await db_session.commit()

    headers = await _login(async_client, user.email)
    legacy_calls = [
        ("GET", f"/api/v1/licitaciones/{licitacion.id}"),
        ("GET", f"/api/v1/licitaciones-obra/expediente/{expediente.id}/workspace"),
        ("POST", f"/api/v1/licitaciones-obra/expediente/{expediente.id}/fallo"),
        ("POST", f"/api/v1/licitaciones-obra/expediente/{expediente.id}/contrato"),
        ("GET", "/api/v1/contratos"),
    ]
    for method, path in legacy_calls:
        response = await async_client.request(method, path, headers=headers)
        assert response.status_code == 404, f"{method} {path}: {response.status_code} {response.text}"

    # Save primary keys before expiring ORM state; reading an expired
    # attribute outside an async SQLAlchemy greenlet triggers MissingGreenlet.
    licitacion_id = licitacion.id
    proposition_id = proposition.id
    db_session.expire_all()
    preserved_licitation = await db_session.get(Licitacion, licitacion_id)
    preserved_proposition = await db_session.get(Proposicion, proposition_id)
    assert preserved_licitation is not None
    assert preserved_proposition is not None
    await db_session.refresh(preserved_licitation)
    await db_session.refresh(preserved_proposition)
    assert preserved_licitation.estado == EstadoLicitacion.APERTURA.value
    assert preserved_proposition.monto == 1000
