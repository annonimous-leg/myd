# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""Tests del flujo de auth real (no solo 401).

ANTES de este archivo: los 15 tests de integración existentes eran
todos `test_*_sin_auth` -- confirmaban que las rutas protegidas
rechazan al usuario sin token, pero ninguno confirmaba que el sistema
funciona correctamente ESTANDO autenticado. El fixture auth_headers
que hubiera permitido esto hacía login contra un usuario que ningún
fixture creaba nunca, así que siempre devolvía headers vacíos en
silencio -- y de cualquier forma, ningún test lo usaba.

Requiere Postgres de test corriendo (ver TEST_DATABASE_URL en
conftest.py) y Redis (REDIS_URL en el entorno) para las pruebas de
revocación -- no se pudo ejecutar nada de esto en el entorno donde se
escribió, sin red ni Postgres/Redis disponibles. Antes de confiar en
este archivo, correrlo de verdad:
    pytest tests/integration/test_auth_flow.py -v
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_happy_path(async_client: AsyncClient, tenant_a_user):
    """Login con credenciales correctas -> 200, token usable contra /me."""
    tenant, user = tenant_a_user

    response = await async_client.post("/api/v1/auth/login", data={
        "username": user.email,
        "password": "testpass123",
    })
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"

    me = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == user.email


@pytest.mark.asyncio
async def test_login_wrong_password_rejected(async_client: AsyncClient, tenant_a_user):
    """Contraseña incorrecta -> 401, no 500 ni 200."""
    _, user = tenant_a_user
    response = await async_client.post("/api/v1/auth/login", data={
        "username": user.email,
        "password": "esta-no-es-la-contraseña",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_bearer_token(async_client: AsyncClient, auth_headers):
    """Antes de esta Fase: logout() no recibía el token, no podía
    revocar nada -- el mismo Bearer seguía siendo válido después de
    'cerrar sesión' hasta su expiración natural. Este test falla si
    esa regresión vuelve a pasar."""
    # El token funciona antes de logout
    me_before = await async_client.get("/api/v1/auth/me", headers=auth_headers)
    assert me_before.status_code == 200

    logout_resp = await async_client.post("/api/v1/auth/logout", headers=auth_headers)
    assert logout_resp.status_code == 200

    # El MISMO token ya no debe funcionar
    me_after = await async_client.get("/api/v1/auth/me", headers=auth_headers)
    assert me_after.status_code == 401


@pytest.mark.asyncio
async def test_refresh_rotates_and_revokes_old_token(async_client: AsyncClient, tenant_a_user):
    """El refresh_token usado debe quedar inservible después de
    refrescar (rotación) -- si alguien lo reutiliza (robo/replay),
    ya no debe servir para sacar un token nuevo otra vez."""
    _, user = tenant_a_user
    login_resp = await async_client.post("/api/v1/auth/login", data={
        "username": user.email,
        "password": "testpass123",
    })
    refresh_token = login_resp.json()["refresh_token"]

    first_refresh = await async_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert first_refresh.status_code == 200

    second_refresh = await async_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert second_refresh.status_code == 401, (
        "El refresh_token ya usado debería estar revocado (rotación) "
        "y no debería poder volver a canjearse por tokens nuevos."
    )
