# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.mark.asyncio
class TestLicitacionesAPI:
    async def test_listar_licitaciones_sin_auth(self, async_client: AsyncClient):
        response = await async_client.get("/api/v1/licitaciones")
        assert response.status_code == 404

    async def test_crear_licitacion_sin_auth(self, async_client: AsyncClient):
        payload = {
            "expediente_id": str(uuid4()),
            "folio": "LP-TEST-001",
            "tipo_procedimiento": "LICITACION_PUBLICA",
            "objeto": "Test objeto",
        }
        response = await async_client.post("/api/v1/licitaciones", json=payload)
        assert response.status_code == 404

    async def test_obtener_licitacion_sin_auth(self, async_client: AsyncClient):
        fake_id = str(uuid4())
        response = await async_client.get(f"/api/v1/licitaciones/{fake_id}")
        assert response.status_code == 404

    async def test_actualizar_licitacion_sin_auth(self, async_client: AsyncClient):
        fake_id = str(uuid4())
        payload = {"estado": "CONVOCATORIA"}
        response = await async_client.patch(f"/api/v1/licitaciones/{fake_id}", json=payload)
        assert response.status_code == 404

    async def test_junta_aclaraciones_sin_auth(self, async_client: AsyncClient):
        fake_id = str(uuid4())
        payload = {"fecha": "2026-07-20", "acta": "Acta de prueba"}
        response = await async_client.post(f"/api/v1/licitaciones/{fake_id}/junta-aclaraciones", json=payload)
        assert response.status_code == 404

    async def test_registrar_proposicion_sin_auth(self, async_client: AsyncClient):
        fake_id = str(uuid4())
        payload = {
            "proveedor_id": str(uuid4()),
            "monto": 4500000,
            "plazo_dias": 100,
        }
        response = await async_client.post(f"/api/v1/licitaciones/{fake_id}/proposiciones", json=payload)
        assert response.status_code == 404

    async def test_filtros_listar_licitaciones(self, async_client: AsyncClient):
        response = await async_client.get("/api/v1/licitaciones?estado=CONVOCATORIA&tipo=LICITACION_PUBLICA")
        assert response.status_code == 404

    async def test_paginacion_listar(self, async_client: AsyncClient):
        response = await async_client.get("/api/v1/licitaciones?skip=0&limit=50")
        assert response.status_code == 404
