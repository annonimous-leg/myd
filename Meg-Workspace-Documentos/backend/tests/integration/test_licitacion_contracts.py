"""Product contract: Megalodon prepares the bidder's proposal, not the authority's lifecycle."""
import pytest

from app.main import app


_FORBIDDEN_AUTHORITY_PREFIXES = (
    "/api/v1/licitaciones",
    "/api/v1/contratos",
    "/api/v1/licitaciones-obra",
)


def test_official_authority_routes_are_not_published():
    paths = set(app.openapi()["paths"])
    exposed = sorted(
        path
        for path in paths
        if any(path == prefix or path.startswith(prefix + "/") for prefix in _FORBIDDEN_AUTHORITY_PREFIXES)
    )
    assert exposed == [], f"Official authority routes must stay in the separate Portal: {exposed}"


def test_bidder_proposal_routes_remain_published():
    paths = set(app.openapi()["paths"])
    assert "/api/v1/procurement/tenders" in paths
    assert "/api/v1/procurement/tenders/{tender_id}" in paths
    assert "/api/v1/procurement/tenders/{tender_id}/sources" in paths
    assert "/api/v1/procurement/tenders/{tender_id}/requirements/candidates" in paths
    assert "/api/v1/procurement/tenders/{tender_id}/readiness" in paths
    assert "/api/v1/procurement/tenders/{tender_id}/submission/download" in paths


@pytest.mark.asyncio
async def test_legacy_authority_commands_return_not_found(async_client):
    expediente_id = "00000000-0000-0000-0000-000000000001"
    calls = [
        ("GET", "/api/v1/licitaciones"),
        ("POST", "/api/v1/licitaciones"),
        ("GET", "/api/v1/contratos"),
        ("POST", "/api/v1/contratos"),
        ("GET", f"/api/v1/licitaciones-obra/expediente/{expediente_id}/workspace"),
        ("POST", f"/api/v1/licitaciones-obra/expediente/{expediente_id}/planeacion"),
        ("POST", f"/api/v1/licitaciones-obra/expediente/{expediente_id}/fallo"),
        ("POST", f"/api/v1/licitaciones-obra/expediente/{expediente_id}/contrato"),
        ("POST", f"/api/v1/licitaciones-obra/expediente/{expediente_id}/finiquito"),
    ]
    for method, path in calls:
        response = await async_client.request(method, path)
        assert response.status_code == 404, f"{method} {path}: {response.status_code} {response.text}"
