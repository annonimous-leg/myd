from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.user import Tenant, User, UserRole
from app.services.auth_service import AuthService
from tezcatlipoca.db.models import SystemSetting


@pytest.fixture
async def tenant_admin(db_session):
    suffix = uuid4().hex[:10]
    tenant = Tenant(name="Tenant settings isolation", slug=f"settings-{suffix}", is_active=True)
    db_session.add(tenant)
    await db_session.flush()
    email = f"settings-admin-{suffix}@example.test"
    user = User(
        email=email,
        hashed_password=AuthService(db_session).hash_password("Test-password-123!"),
        full_name="Settings Tenant Admin",
        role=UserRole.ADMIN,
        tenant_id=tenant.id,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    return tenant, email


async def _admin_headers(async_client, email: str) -> dict[str, str]:
    response = await async_client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": "Test-password-123!"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_tenant_admin_cannot_read_global_settings(async_client, db_session, tenant_admin):
    tenant, email = tenant_admin
    db_session.add_all([
        SystemSetting(tenant_id=None, key="platform-provider-secret", value={"api_key": "must-not-leak"}),
        SystemSetting(tenant_id=str(tenant.id), key="tenant-workspace-mode", value={"mode": "professional"}),
    ])
    await db_session.commit()

    response = await async_client.get(
        "/api/tezcatlipoca/settings/",
        headers=await _admin_headers(async_client, email),
    )

    assert response.status_code == 200, response.text
    settings = response.json()["settings"]
    assert "tenant-workspace-mode" in settings
    assert "platform-provider-secret" not in settings


@pytest.mark.asyncio
async def test_tenant_admin_cannot_delete_global_settings(async_client, db_session, tenant_admin):
    _tenant, email = tenant_admin
    global_setting = SystemSetting(
        tenant_id=None,
        key=f"platform-protected-{uuid4().hex}",
        value={"secret": "must-remain"},
    )
    db_session.add(global_setting)
    await db_session.commit()
    key = global_setting.key

    response = await async_client.delete(
        f"/api/tezcatlipoca/settings/{key}",
        headers=await _admin_headers(async_client, email),
    )

    assert response.status_code == 404, response.text
    remaining = await db_session.scalar(
        select(SystemSetting).where(SystemSetting.tenant_id.is_(None), SystemSetting.key == key)
    )
    assert remaining is not None
