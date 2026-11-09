"""Megalodon exposes bidder proposal preparation, not official contract administration."""
import pytest

from app.main import app


def test_official_contract_commands_are_not_published_by_megalodon():
    paths = set(app.openapi()["paths"])
    assert not any(
        path == "/api/v1/contratos" or path.startswith("/api/v1/contratos/")
        for path in paths
    )
    assert "/api/v1/procurement/tenders" in paths
    assert "/api/v1/procurement/tenders/{tender_id}/submission" in paths


@pytest.mark.asyncio
async def test_legacy_contract_commands_return_not_found(async_client):
    responses = [
        await async_client.get("/api/v1/contratos"),
        await async_client.post("/api/v1/contratos", json={
            "numero_contrato": "CI-OUT-OF-SCOPE",
            "objeto": "Prueba de límite de producto",
            "monto_total": 1000,
            "plazo_dias": 30,
        }),
    ]
    assert [response.status_code for response in responses] == [404, 404]
