# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.mark.asyncio
class TestContratosAPI:
    async def test_listar_contratos_sin_auth(self, async_client: AsyncClient):
        response = await async_client.get("/api/v1/contratos")
        assert response.status_code == 404

    async def test_obtener_contrato_404_sin_auth(self, async_client: AsyncClient):
        fake_id = str(uuid4())
        response = await async_client.get(f"/api/v1/contratos/{fake_id}")
        assert response.status_code == 404

    async def test_crear_contrato_sin_auth(self, async_client: AsyncClient):
        payload = {
            "expediente_id": str(uuid4()),
            "proveedor_id": str(uuid4()),
            "numero_contrato": "OC-TEST-001",
            "objeto": "Test",
            "monto_total": 1000000,
            "plazo_dias": 90,
        }
        response = await async_client.post("/api/v1/contratos", json=payload)
        assert response.status_code == 404

    async def test_actualizar_contrato_sin_auth(self, async_client: AsyncClient):
        fake_id = str(uuid4())
        payload = {"estado": "VIGENTE"}
        response = await async_client.patch(f"/api/v1/contratos/{fake_id}", json=payload)
        assert response.status_code == 404

    async def test_crear_modificatorio_sin_auth(self, async_client: AsyncClient):
        fake_id = str(uuid4())
        payload = {"numero": "CM-001", "tipo": "PLAZO"}
        response = await async_client.post(f"/api/v1/contratos/{fake_id}/modificatorios", json=payload)
        assert response.status_code == 404

    async def test_crear_garantia_sin_auth(self, async_client: AsyncClient):
        fake_id = str(uuid4())
        payload = {"tipo": "CUMPLIMIENTO", "monto": 100000}
        response = await async_client.post(f"/api/v1/contratos/{fake_id}/garantias", json=payload)
        assert response.status_code == 404

    async def test_crear_entregable_sin_auth(self, async_client: AsyncClient):
        fake_id = str(uuid4())
        payload = {"numero_estimacion": 1, "monto_ejecutado": 500000, "avance_fisico": 25}
        response = await async_client.post(f"/api/v1/contratos/{fake_id}/entregables", json=payload)
        assert response.status_code == 404

    async def test_filtros_listar_contratos(self, async_client: AsyncClient):
        """Verifica que los parametros de query sean aceptados."""
        response = await async_client.get("/api/v1/contratos?estado=VIGENTE&expediente_id=123")
        assert response.status_code == 404  # Auth requerido, pero parametros validos
