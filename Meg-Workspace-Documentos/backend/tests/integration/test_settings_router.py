# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""Tests del router de settings restaurado.

Este archivo cubre el hueco que tenía el router antes:
- no había control de acceso real;
- no había persistencia;
- no había forma de demostrar en CI que el CRUD funcionaba con un
  usuario admin real.
"""
import pytest
from httpx import AsyncClient

from app.models.user import UserRole
from tests.conftest import _create_tenant_and_user, _login


@pytest.mark.asyncio
async def test_settings_rejects_non_admin(async_client: AsyncClient, tenant_a_user):
    _, user = tenant_a_user
    headers = await _login(async_client, user.email)
    response = await async_client.get("/api/tezcatlipoca/settings/", headers=headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_settings_crud_persists_for_admin(async_client: AsyncClient, db_session):
    _, admin = await _create_tenant_and_user(
        db_session,
        "settings-tenant-test",
        "admin@settings-tenant-test.mx",
        role=UserRole.ADMIN,
    )
    headers = await _login(async_client, admin.email)

    empty = await async_client.get("/api/tezcatlipoca/settings/", headers=headers)
    assert empty.status_code == 200
    assert empty.json()["settings"] == {}

    update = await async_client.post(
        "/api/tezcatlipoca/settings/",
        json={"settings": {"feature_x": True, "max_upload_mb": 25}},
        headers=headers,
    )
    assert update.status_code == 200
    assert update.json()["settings"]["feature_x"] is True

    reread = await async_client.get("/api/tezcatlipoca/settings/", headers=headers)
    assert reread.status_code == 200
    assert reread.json()["settings"]["feature_x"] is True
    assert reread.json()["settings"]["max_upload_mb"] == 25

    delete = await async_client.delete(
        "/api/tezcatlipoca/settings/feature_x",
        headers=headers,
    )
    assert delete.status_code == 200

    after_delete = await async_client.get("/api/tezcatlipoca/settings/", headers=headers)
    assert after_delete.status_code == 200
    assert "feature_x" not in after_delete.json()["settings"]
