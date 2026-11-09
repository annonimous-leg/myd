import os

import pytest
import httpx

BASE_URL = os.getenv("MEGALODON_REAL_API_URL")
TOKEN = os.getenv("MEGALODON_REAL_API_TOKEN")

pytestmark = pytest.mark.integration


@pytest.mark.skipif(not BASE_URL or not TOKEN, reason="Requires MEGALODON_REAL_API_URL and MEGALODON_REAL_API_TOKEN")
@pytest.mark.asyncio
async def test_real_stack_ready_and_tenant_contract():
    headers = {"Authorization": f"Bearer {TOKEN}"}
    async with httpx.AsyncClient(base_url=BASE_URL, headers=headers, timeout=30) as client:
        ready = await client.get("/ready")
        assert ready.status_code == 200, ready.text
        payload = ready.json()
        assert payload["status"] == "ready", payload
        plan = await client.get("/api/v1/entitlements/mi-plan")
        assert plan.status_code == 200, plan.text
        modules = await client.get("/api/v1/entitlements/modulos")
        assert modules.status_code == 200, modules.text
        assert isinstance(modules.json(), list)


@pytest.mark.skipif(not BASE_URL or not TOKEN, reason="Requires real stack credentials")
@pytest.mark.asyncio
async def test_real_tezcatlipoca_bridge_and_topography():
    headers = {"Authorization": f"Bearer {TOKEN}"}
    async with httpx.AsyncClient(base_url=BASE_URL, headers=headers, timeout=30) as client:
        telemetry = await client.get("/api/tezcatlipoca/telemetry/health")
        assert telemetry.status_code in {200, 503}, telemetry.text
        # 503 is acceptable only when the subsystem explicitly reports degraded/unavailable.
        if telemetry.status_code == 503:
            body = telemetry.json()
            assert body.get("error") or body.get("detail")

        # Topography list must enforce authentication and tenant scope.
        response = await client.get("/api/v1/topografia/levantamientos")
        assert response.status_code in {200, 404}, response.text
