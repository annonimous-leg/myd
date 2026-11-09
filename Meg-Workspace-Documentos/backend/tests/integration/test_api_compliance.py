# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.mark.asyncio
class TestComplianceAPI:
    async def test_listar_reglas_sin_auth(self, async_client: AsyncClient):
        response = await async_client.get("/api/v1/compliance/reglas")
        assert response.status_code == 401

    async def test_crear_regla_sin_auth(self, async_client: AsyncClient):
        payload = {
            "nombre": "Regla test",
            "tipo_procedimiento": "LICITACION_PUBLICA",
            "etapa": "CONVOCATORIA",
        }
        response = await async_client.post("/api/v1/compliance/reglas", json=payload)
        assert response.status_code == 401

    async def test_crear_inconformidad_sin_auth(self, async_client: AsyncClient):
        payload = {
            "expediente_id": str(uuid4()),
            "titulo": "Test",
            "descripcion": "Desc",
        }
        response = await async_client.post("/api/v1/compliance/inconformidades", json=payload)
        assert response.status_code == 401

    async def test_actualizar_inconformidad_sin_auth(self, async_client: AsyncClient):
        fake_id = str(uuid4())
        payload = {"estado": "EN_ANALISIS"}
        response = await async_client.patch(f"/api/v1/compliance/inconformidades/{fake_id}", json=payload)
        assert response.status_code == 401

    async def test_crear_sancion_sin_auth(self, async_client: AsyncClient):
        payload = {
            "proveedor_id": str(uuid4()),
            "tipo": "MULTA",
            "motivo": "Incumplimiento",
        }
        response = await async_client.post("/api/v1/compliance/sanciones", json=payload)
        assert response.status_code == 401

    async def test_endpoints_existen(self, async_client: AsyncClient):
        """Verifica que los endpoints respondan (aunque sea 401)."""
        endpoints = [
            ("GET", "/api/v1/compliance/reglas"),
            ("POST", "/api/v1/compliance/reglas"),
            ("POST", "/api/v1/compliance/inconformidades"),
            ("POST", "/api/v1/compliance/sanciones"),
        ]
        for method, path in endpoints:
            if method == "GET":
                response = await async_client.get(path)
            else:
                response = await async_client.post(path, json={})
            assert response.status_code in [401, 422], f"{method} {path} devolvio {response.status_code}"
