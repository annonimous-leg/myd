# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""Aislamiento por tenant a través del puente Megalodon -> Tezcatlipoca.

Esto es lo que nunca se pudo probar en este entorno (sin Postgres, sin
Redis, sin poder levantar el servidor) durante las Fases 2 y 3: que un
usuario de un tenant NO puede ver ni tocar los snapshots creados por un
usuario de otro tenant, usando el flujo real (login en Megalodon,
mismo Bearer contra /api/tezcatlipoca/*).

Prerrequisitos para correr esto de verdad:
  - Postgres de test (TEST_DATABASE_URL en conftest.py)
  - Redis corriendo en REDIS_URL (Tezcatlipoca ahora revisa el mismo
    store de revocación de Megalodon -- si Redis no está arriba,
    is_jti_revoked() truena, no da un falso "no revocado")
  - DATABASE_URL SIN configurar en el entorno de test, para que
    Tezcatlipoca caiga en su SQLite local por default (ver
    tezcatlipoca/db/models.py) y no intente hablarle con el driver
    async de Postgres a través de su engine síncrono.

    pytest tests/integration/test_tezcatlipoca_tenant_isolation.py -v
"""
import pytest
from httpx import AsyncClient


async def _login(async_client: AsyncClient, email: str, password: str = "testpass123") -> dict:
    response = await async_client.post("/api/v1/auth/login", data={
        "username": email,
        "password": password,
    })
    assert response.status_code == 200, f"login falló: {response.status_code} {response.text}"
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_snapshot_not_visible_across_tenants(
    async_client: AsyncClient, tenant_a_user, tenant_b_user
):
    """Usuario A crea un snapshot. Usuario B (tenant distinto) no debe
    poder listarlo ni leerlo por ID -- ni aunque adivine el ID exacto."""
    _, user_a = tenant_a_user
    _, user_b = tenant_b_user

    headers_a = await _login(async_client, user_a.email)
    headers_b = await _login(async_client, user_b.email)

    create_resp = await async_client.post(
        "/api/tezcatlipoca/snapshots/create",
        headers=headers_a,
        json={"name": "sitio-obra-tenant-a", "layers": [], "viewport": None},
    )
    assert create_resp.status_code == 200, create_resp.text
    snapshot_id = create_resp.json()["id"]

    # A sí lo ve
    list_a = await async_client.get("/api/tezcatlipoca/snapshots/", headers=headers_a)
    assert any(s["id"] == snapshot_id for s in list_a.json())

    get_a = await async_client.get(f"/api/tezcatlipoca/snapshots/{snapshot_id}", headers=headers_a)
    assert get_a.status_code == 200

    # B NO lo ve en su lista
    list_b = await async_client.get("/api/tezcatlipoca/snapshots/", headers=headers_b)
    assert all(s["id"] != snapshot_id for s in list_b.json()), (
        "Fuga entre tenants: el usuario del tenant B ve un snapshot "
        "creado por el tenant A en /snapshots/"
    )

    # B tampoco lo puede leer por ID directo -- 404, no 403 (no
    # confirmamos que el ID existe en otro tenant)
    get_b = await async_client.get(f"/api/tezcatlipoca/snapshots/{snapshot_id}", headers=headers_b)
    assert get_b.status_code == 404, (
        f"Fuga entre tenants: GET directo por ID devolvió {get_b.status_code} "
        f"en vez de 404 para un snapshot de otro tenant."
    )

    # B tampoco lo puede borrar
    delete_b = await async_client.delete(f"/api/tezcatlipoca/snapshots/{snapshot_id}", headers=headers_b)
    assert delete_b.status_code == 404


@pytest.mark.asyncio
async def test_wormhole_dead_drop_roundtrip_and_tenant_isolation(
    async_client: AsyncClient, tenant_a_user, tenant_b_user
):
    """Valida DOS cosas a la vez: (1) el bug real que se encontró en
    Fase 3 -- antes create_dead_drop() solo guardaba un hash,
    get_dead_drop() nunca podía devolver el mensaje original -- y (2)
    que el mensaje no es legible desde otro tenant."""
    _, user_a = tenant_a_user
    _, user_b = tenant_b_user
    headers_a = await _login(async_client, user_a.email)
    headers_b = await _login(async_client, user_b.email)

    secret_message = "coordenadas-sensibles-solo-para-tenant-a"
    create_resp = await async_client.post(
        "/api/tezcatlipoca/wormhole/dead-drop/create",
        headers=headers_a,
        json={"payload": secret_message, "ttl_minutes": 60, "max_reads": 5},
    )
    assert create_resp.status_code == 200, create_resp.text
    drop_id = create_resp.json()["drop_id"]

    # A sí puede leer el mensaje real (antes de Fase 3 esto era
    # imposible sin importar quién lo pidiera: solo existía el hash)
    read_a = await async_client.get(f"/api/tezcatlipoca/wormhole/dead-drop/{drop_id}", headers=headers_a)
    assert read_a.status_code == 200
    assert read_a.json()["payload"] == secret_message

    # B, de otro tenant, no puede leerlo aunque tenga el ID exacto
    read_b = await async_client.get(f"/api/tezcatlipoca/wormhole/dead-drop/{drop_id}", headers=headers_b)
    assert read_b.status_code == 404
