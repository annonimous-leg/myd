"""HTTP acceptance for tenant-scoped BIM drawing requests and downloads."""
from uuid import UUID

import pytest
from app.models.bim import DibujoBIM, ElementoBIM
from tests.conftest import _login
from tests.integration.test_bim_regressions import model as make_model


@pytest.mark.asyncio
async def test_drawing_http_flow_is_tenant_scoped_and_pending_download_is_blocked(
    async_client, db_session, tenant_a_user, tenant_b_user, monkeypatch
):
    tenant, user = tenant_a_user
    _, other_user = tenant_b_user
    expediente, model = await make_model(db_session, tenant, user)
    model.estado_procesamiento = "COMPLETADO"
    model.version_ifc = "IFC4"
    db_session.add(ElementoBIM(
        modelo_id=model.id,
        global_id="2xKq-http-fixture-0001",
        express_id=1,
        tipo="IfcWall",
        nombre="HTTP fixture wall",
    ))
    await db_session.commit()

    owner_headers = await _login(async_client, user.email)
    other_headers = await _login(async_client, other_user.email)
    endpoint = f"/api/v1/bim/{expediente.id}/modelos/{model.id}/dibujos"

    created = await async_client.post(
        endpoint,
        json={
            "tipo": "PLAN",
            "titulo": "Planta HTTP",
            "parametros": {"elevacion_m": 1.5},
            "formatos": ["PDF"],
        },
        headers=owner_headers,
    )
    assert created.status_code == 202, created.text
    drawing = created.json()
    assert drawing["estado"] == "PENDIENTE"
    assert drawing["modelo_id"] == str(model.id)
    assert drawing["expediente_id"] == str(expediente.id)
    assert drawing["sha256_pdf"] is None

    listed = await async_client.get(endpoint, headers=owner_headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [drawing["id"]]

    pending_download = await async_client.get(
        endpoint + f"/{drawing['id']}/descarga",
        params={"formato": "PDF"},
        headers=owner_headers,
    )
    assert pending_download.status_code == 409

    foreign_read = await async_client.get(
        endpoint + f"/{drawing['id']}",
        headers=other_headers,
    )
    assert foreign_read.status_code == 404

    foreign_list = await async_client.get(endpoint, headers=other_headers)
    assert foreign_list.status_code == 404



    from app.integrations import supabase_storage

    persisted = await db_session.get(DibujoBIM, UUID(drawing["id"]))
    persisted.estado = "COMPLETADO"
    persisted.ruta_pdf = f"tenant/{tenant.id}/{expediente.id}/{model.id}/drawings/{persisted.id}/drawing.pdf"
    await db_session.commit()

    class SignedStorage:
        async def url_firmada(self, path, ttl):
            assert path == persisted.ruta_pdf
            assert ttl == 3600
            return "https://storage.example.invalid/signed.pdf"

    monkeypatch.setattr(supabase_storage, "storage_bim", SignedStorage)
    url = endpoint + f"/{drawing['id']}/descarga"
    response = await async_client.get(url, params={"formato": "PDF"}, headers=owner_headers)
    assert response.status_code == 200, response.text
    assert response.json()["url"].endswith("/signed.pdf")
    response = await async_client.get(url, params={"formato": "PDF"}, headers=other_headers)
    assert response.status_code == 404
