"""Bidder-side diagnostics and document inventory retain tenant/privacy guarantees.

The authority-side proposition review/admission/fallo workflow is not a Megalodon API.
"""
from hashlib import sha256
from uuid import UUID, uuid4

import pytest

from app.main import app
from app.models.expediente import Documento
from app.models.licitacion import EstadoLicitacion, Licitacion, Proposicion, TipoProcedimiento
from app.models.proveedor import Proveedor, TipoPersona
from app.models.validador import ValidacionPropuesta
from tests.conftest import _login
from tests.integration.test_closure_two_tenants import make_expediente


def test_proposal_diagnostic_cannot_link_an_authority_side_proposition():
    operation = app.openapi()["paths"]["/api/v1/validadores/{expediente_id}/evaluar-completo"]["post"]
    parameter_names = {parameter["name"] for parameter in operation.get("parameters", [])}
    assert "proposicion_id" not in parameter_names

    paths = set(app.openapi()["paths"])
    for prefix in ("/api/v1/licitaciones", "/api/v1/contratos", "/api/v1/licitaciones-obra"):
        assert not any(path == prefix or path.startswith(prefix + "/") for path in paths)


@pytest.mark.asyncio
async def test_proposal_diagnostic_does_not_turn_form_declarations_into_legal_facts(
    async_client, db_session, tenant_a_user,
):
    tenant, user = tenant_a_user
    expediente = make_expediente(tenant, user)
    db_session.add(expediente)
    await db_session.flush()

    # Keep a real legacy proposition row as a regression sentinel. Megalodon may
    # diagnose the bidder's declared inputs, but must not mutate this authority
    # record, verify an e-signature, or convert a form declaration into evidence.
    provider = Proveedor(
        tenant_id=tenant.id,
        tipo_persona=TipoPersona.MORAL.value,
        rfc=("T" + uuid4().hex[:11]).upper(),
        razon_social="Proveedor de prueba de inmutabilidad",
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
        objeto="Registro heredado únicamente para prueba de regresión",
        monto_estimado=1000,
        plazo_dias=30,
        bases="Bases históricas de prueba",
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
        firma_valida=None,
        integridad_valida=None,
        cumplimiento_documental=None,
        verificacion_documental=None,
        creado_por_id=user.id,
        actualizado_por_id=user.id,
    )
    db_session.add(proposition)
    await db_session.commit()

    headers = await _login(async_client, user.email)
    response = await async_client.post(
        f"/api/v1/validadores/{expediente.id}/evaluar-completo?proposicion_id={proposition.id}",
        headers=headers,
        json={"administrativo": {"efirma_valida": True}},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["expediente_id"] == str(expediente.id)
    assert payload["proposicion_id"] is None

    saved = await db_session.get(ValidacionPropuesta, UUID(payload["id"]))
    assert saved is not None
    assert saved.proposicion_id is None
    assert saved.datos_entrada["administrativo"]["efirma_valida"] is True

    await db_session.refresh(proposition)
    assert proposition.estado == "RECIBIDA"
    assert proposition.firma_valida is None
    assert proposition.integridad_valida is None
    assert proposition.cumplimiento_documental is None
    assert proposition.verificacion_documental is None


@pytest.mark.asyncio
async def test_document_inventory_is_tenant_scoped_and_hides_storage_paths(
    async_client, db_session, tenant_a_user, tenant_b_user,
):
    tenant_a, user_a = tenant_a_user
    expediente = make_expediente(tenant_a, user_a)
    db_session.add(expediente)
    await db_session.flush()

    digest = sha256(b"controlled document fixture").hexdigest()
    document = Documento(
        identificador=f"DOC-{uuid4().hex[:8]}",
        nombre="bases-de-obra.pdf",
        tipo_documental="CONVOCATORIA",
        formato="pdf",
        storage_path=f"{tenant_a.id}/{expediente.id}/private/bases-de-obra.pdf",
        storage_bucket="documentos-privados",
        size_bytes=len(b"controlled document fixture"),
        hash_sha256=digest,
        expediente_id=expediente.id,
        creado_por_id=user_a.id,
        actualizado_por_id=user_a.id,
    )
    db_session.add(document)
    await db_session.commit()

    headers = await _login(async_client, user_a.email)
    response = await async_client.get(f"/api/v1/expedientes/{expediente.id}/documentos?limit=1", headers=headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert [item["id"] for item in payload] == [str(document.id)]
    assert set(payload[0]) == {
        "id", "nombre", "tipo_documental", "formato", "size_bytes",
        "hash_sha256", "row_version", "created_at",
    }
    assert "storage_path" not in payload[0]
    assert "storage_bucket" not in payload[0]

    tenant_b, user_b = tenant_b_user
    other_headers = await _login(async_client, user_b.email)
    other = await async_client.get(
        f"/api/v1/expedientes/{expediente.id}/documentos",
        headers=other_headers,
    )
    assert other.status_code == 404
