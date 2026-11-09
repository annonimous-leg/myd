"""The active API cannot issue official contracting-authority decisions."""
import pytest

from app.main import app
from app.models.user import UserRole
from tests.conftest import _create_tenant_and_user, _login


def test_public_router_does_not_mount_official_licitacion_or_contract_api():
    paths = set(app.openapi()["paths"])
    assert not any(path == "/api/v1/licitaciones" or path.startswith("/api/v1/licitaciones/") for path in paths)
    assert not any(path == "/api/v1/contratos" or path.startswith("/api/v1/contratos/") for path in paths)
    assert "/api/v1/procurement/tenders" in paths


@pytest.mark.asyncio
async def test_legacy_official_commands_return_not_found(async_client):
    routes = [
        ("GET", "/api/v1/licitaciones"),
        ("POST", "/api/v1/licitaciones"),
        ("POST", "/api/v1/licitaciones/00000000-0000-0000-0000-000000000001/fallo"),
        ("GET", "/api/v1/contratos"),
        ("POST", "/api/v1/contratos"),
        ("GET", "/api/v1/licitaciones-obra/expediente/00000000-0000-0000-0000-000000000001/workspace"),
        ("POST", "/api/v1/licitaciones-obra/expediente/00000000-0000-0000-0000-000000000001/fallo"),
        ("POST", "/api/v1/licitaciones-obra/expediente/00000000-0000-0000-0000-000000000001/contrato"),
        ("POST", "/api/v1/licitaciones-obra/expediente/00000000-0000-0000-0000-000000000001/estimaciones"),
        ("POST", "/api/v1/licitaciones-obra/expediente/00000000-0000-0000-0000-000000000001/contrato/terminar"),
        ("POST", "/api/v1/licitaciones-obra/expediente/00000000-0000-0000-0000-000000000001/finiquito"),
    ]
    for method, path in routes:
        response = await async_client.request(method, path)
        assert response.status_code == 404, f"{method} {path}: {response.status_code} {response.text}"


@pytest.mark.asyncio
async def test_provider_registry_is_tenant_scoped_and_rejects_duplicates(async_client, db_session):
    identities = [
        await _create_tenant_and_user(db_session, f"provider-{i}", f"provider{i}@example.mx", role=UserRole.TECNICO)
        for i in range(2)
    ]
    payload = {"rfc": "COS260101A12", "razon_social": "Proveedor compartido", "tipo_persona": "MORAL"}
    ids = []
    for _, user in identities:
        headers = await _login(async_client, user.email)
        created = await async_client.post("/api/v1/proveedores", headers=headers, json=payload)
        assert created.status_code == 201, created.text
        ids.append(created.json()["id"])
        duplicate = await async_client.post("/api/v1/proveedores", headers=headers, json=payload)
        assert duplicate.status_code == 409, duplicate.text
        result = (await async_client.get("/api/v1/proveedores?q=COS&limit=1", headers=headers)).json()
        assert result["total"] == 1
        assert result["items"][0]["id"] == ids[-1]
    assert ids[0] != ids[1]
