"""Real HTTP + database identity changes, session invalidation and isolation."""
import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func, event

from app.models.user import User, UserRole
from app.models.audit_ledger import AuditLedger
from app.modules.audit.service import AuditService
from app.services.identity_service import IdentityService
from tests.conftest import _login, AsyncSessionLocalTest


async def add_user(db, tenant, email, role=UserRole.TECNICO):
    from uuid import uuid4
    from app.services.auth_service import AuthService
    user = User(tenant_id=tenant.id, email=f"{uuid4().hex}@{email}",
                full_name="Identity integration", role=role, is_active=True,
                hashed_password=AuthService(db).hash_password("testpass123"))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def make_admin(db, tenant_a_user):
    tenant, user = tenant_a_user
    user.role = UserRole.ADMIN
    await db.commit()
    return tenant, user


@pytest.mark.asyncio
async def test_authoritative_list_includes_users_without_shadow_and_scopes_tenant(
        async_client, db_session, tenant_a_user, tenant_b_user):
    tenant, admin = await make_admin(db_session, tenant_a_user)
    member = await add_user(db_session, tenant, "example.mx")
    headers = await _login(async_client, admin.email)
    users = await async_client.get("/api/v1/users", headers=headers)
    assert users.status_code == 200, users.text
    assert {u["id"] for u in users.json()} == {str(admin.id), str(member.id)}
    count = await async_client.get("/api/tezcatlipoca/auth/users/count", headers=headers)
    assert count.json() == {"total_users": 2}
    dashboard = await async_client.get("/api/admin/dashboard", headers=headers)
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["users"]["total"] == 2
    assert "revoked_tokens" not in dashboard.json()
    assert (await async_client.get("/api/admin/users", headers=headers)).status_code == 404
    assert (await async_client.patch(f"/api/admin/users/{member.id}", headers=headers,
                                    json={"tier": "admin"})).status_code == 404
    assert (await async_client.get("/api/v1/users?skip=-1", headers=headers)).status_code == 422


@pytest.mark.asyncio
async def test_changes_persist_and_old_access_refresh_never_return_on_reenable(
        async_client, db_session, tenant_a_user):
    tenant, admin = await make_admin(db_session, tenant_a_user)
    member = await add_user(db_session, tenant, "example.mx")
    login = await async_client.post("/api/v1/auth/login",
                                   data={"username": member.email, "password": "testpass123"})
    tokens = login.json()
    member_headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    # Materialize a mirror before changing the authority.
    assert (await async_client.get("/api/tezcatlipoca/auth/me", headers=member_headers)).status_code == 200
    headers = await _login(async_client, admin.email)
    response = await async_client.patch(f"/api/v1/users/{member.id}", headers=headers,
                                       json={"role": "revisor", "reason": "Reasignación aprobada"})
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "revisor"
    for path in ["/api/v1/auth/me", "/api/tezcatlipoca/auth/me"]:
        assert (await async_client.get(path, headers=member_headers)).status_code == 401
    assert (await async_client.post("/api/v1/auth/refresh",
                                   json={"refresh_token": tokens["refresh_token"]})).status_code == 401
    new_headers = await _login(async_client, member.email)
    mirror = await async_client.get("/api/tezcatlipoca/auth/me", headers=new_headers)
    assert mirror.status_code == 200 and mirror.json()["tier"] == "restricted"
    for active in [False, True]:
        response = await async_client.patch(f"/api/v1/users/{member.id}", headers=headers,
                                           json={"is_active": active, "reason": "Cambio de acceso autorizado"})
        assert response.status_code == 200, response.text
    for path in ["/api/v1/auth/me", "/api/tezcatlipoca/auth/me"]:
        assert (await async_client.get(path, headers=new_headers)).status_code == 401
    fresh = await _login(async_client, member.email)
    assert (await async_client.get("/api/v1/auth/me", headers=fresh)).status_code == 200
    await db_session.refresh(member)
    assert member.role == "revisor" and member.is_active and member.auth_version == 3
    records = list(await db_session.scalars(select(AuditLedger).where(
        AuditLedger.tenant_id == tenant.id, AuditLedger.entidad_id == str(member.id))))
    assert len(records) == 3 and all(r.user_id == admin.id for r in records)
    integrity = await AuditService(db_session).verificar_integridad_cadena(
        "USUARIO", str(member.id), tenant_id=tenant.id)
    assert integrity["valido"], integrity


@pytest.mark.asyncio
async def test_permissions_and_cross_tenant_targets_are_closed(
        async_client, db_session, tenant_a_user, tenant_b_user):
    _, admin = await make_admin(db_session, tenant_a_user)
    headers = await _login(async_client, admin.email)
    response = await async_client.patch(f"/api/v1/users/{tenant_b_user[1].id}", headers=headers,
                                       json={"role": "admin", "reason": "Intento ajeno"})
    assert response.status_code == 404
    for body in [
        {"role": "superadmin", "reason": "Intento de elevación"},
        {"is_active": False, "reason": "Intento sobre sí mismo"},
    ]:
        response = await async_client.patch(f"/api/v1/users/{admin.id}", headers=headers, json=body)
        assert response.status_code == 403, response.text
    other = await _login(async_client, tenant_b_user[1].email)
    assert (await async_client.get("/api/v1/users", headers=other)).status_code == 403
    assert (await async_client.patch(f"/api/v1/users/{admin.id}", headers=other,
                                    json={"role": "lector", "reason": "Sin permiso"})).status_code == 403


@pytest.mark.asyncio
async def test_platform_identity_and_last_tenant_administrator_are_protected(
        async_client, db_session, tenant_a_user):
    tenant, admin = await make_admin(db_session, tenant_a_user)
    platform = await add_user(db_session, tenant, "platform.mx", UserRole.SUPERADMIN)
    headers = await _login(async_client, admin.email)
    denied = await async_client.patch(f"/api/v1/users/{platform.id}", headers=headers,
                                     json={"is_active": False, "reason": "Intento de tenant"})
    assert denied.status_code == 403
    platform_headers = await _login(async_client, platform.email)
    last = await async_client.patch(f"/api/v1/users/{admin.id}", headers=platform_headers,
                                   json={"role": "lector", "reason": "No debe dejar huérfano"})
    assert last.status_code == 409, last.text


@pytest.mark.asyncio
async def test_update_contract_rejects_empty_unknown_null_and_coerced_state(
        async_client, db_session, tenant_a_user):
    tenant, admin = await make_admin(db_session, tenant_a_user)
    member = await add_user(db_session, tenant, "example.mx")
    headers = await _login(async_client, admin.email)
    for body in [
        {"reason": "Sin cambio"}, {"role": "lector", "reason": "   "},
        {"role": None, "reason": "Nulo"}, {"is_active": None, "reason": "Nulo"},
        {"is_active": "false", "reason": "Coerción"},
        {"tier": "full", "reason": "Campo ajeno"},
        {"role": "lector", "tenant_id": str(tenant.id), "reason": "Campo ajeno"},
    ]:
        response = await async_client.patch(f"/api/v1/users/{member.id}", headers=headers, json=body)
        assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_audit_write_failure_rolls_back_identity_and_session_version(
        db_session, tenant_a_user):
    tenant, admin = await make_admin(db_session, tenant_a_user)
    member = await add_user(db_session, tenant, "example.mx")
    member_id, tenant_id = member.id, tenant.id

    def fail_audit(*args):
        raise RuntimeError("Storage failure during audit insert")

    event.listen(AuditLedger, "before_insert", fail_audit)
    try:
        with pytest.raises(RuntimeError, match="Storage failure"):
            await IdentityService(db_session).update_user(
                actor=admin, user_id=member_id, role=UserRole.LECTOR,
                is_active=None, reason="Atomicidad")
    finally:
        event.remove(AuditLedger, "before_insert", fail_audit)
    await db_session.refresh(member)
    assert member.role == "tecnico" and member.auth_version == 0
    assert await db_session.scalar(select(func.count()).select_from(AuditLedger).where(
        AuditLedger.tenant_id == tenant_id, AuditLedger.entidad_id == str(member_id))) == 0


@pytest.mark.asyncio
async def test_concurrent_admin_disable_rechecks_actor_after_tenant_lock(
        db_session, tenant_a_user):
    if db_session.bind.dialect.name != "postgresql":
        pytest.skip("Row-lock concurrency requires real PostgreSQL")
    tenant, admin_a = await make_admin(db_session, tenant_a_user)
    admin_b = await add_user(db_session, tenant, "example.mx", UserRole.ADMIN)
    gate = asyncio.Event()
    async with AsyncSessionLocalTest() as db_a, AsyncSessionLocalTest() as db_b:
        # Both actors are deliberately read before either transaction commits.
        actor_a = await db_a.get(User, admin_a.id)
        actor_b = await db_b.get(User, admin_b.id)

        async def disable(db, actor, target_id):
            await gate.wait()
            try:
                await IdentityService(db).update_user(
                    actor=actor, user_id=target_id, role=None, is_active=False,
                    reason="Deshabilitación concurrente")
                return "committed"
            except HTTPException as exc:
                assert exc.status_code == 403
                return "rejected"
        tasks = [asyncio.create_task(disable(db_a, actor_a, admin_b.id)),
                 asyncio.create_task(disable(db_b, actor_b, admin_a.id))]
        gate.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=20)
    assert sorted(results) == ["committed", "rejected"]
    assert await db_session.scalar(select(func.count()).select_from(User).where(
        User.tenant_id == tenant.id, User.role == "admin", User.is_active.is_(True))) == 1


@pytest.mark.asyncio
async def test_tokens_without_identity_version_require_new_login(
        async_client, db_session, tenant_a_user):
    import jwt
    from app.config import settings
    tokens = (await async_client.post("/api/v1/auth/login", data={
        "username": tenant_a_user[1].email, "password": "testpass123"})).json()
    for kind in ["access", "refresh"]:
        payload = jwt.decode(tokens[f"{kind}_token"], settings.SECRET_KEY,
                             algorithms=[settings.ALGORITHM])
        del payload["auth_version"]
        old = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        if kind == "access":
            response = await async_client.get("/api/v1/auth/me",
                                              headers={"Authorization": f"Bearer {old}"})
        else:
            response = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": old})
        assert response.status_code == 401, response.text


@pytest.mark.asyncio
async def test_cookie_admin_changes_require_exact_browser_origin(
        async_client, db_session, tenant_a_user):
    tenant, admin = await make_admin(db_session, tenant_a_user)
    member = await add_user(db_session, tenant, "example.mx")
    response = await async_client.post("/api/v1/auth/session/login",
                                      data={"username": admin.email, "password": "testpass123"},
                                      headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 200
    path = f"/api/v1/users/{member.id}"
    body = {"role": "lector", "reason": "Cambio de navegador"}
    for headers in [{}, {"Origin": "null"}, {"Origin": "http://test.attacker.com"},
                    {"Origin": "http://evil.test"}, {"Origin": "https://attacker.invalid",
                     "X-Forwarded-Host": "attacker.invalid"},
                    [("Origin", "http://localhost:5173"), ("Origin", "http://attacker.invalid")]]:
        response = await async_client.patch(path, json=body, headers=headers)
        assert response.status_code == 403, response.text
    response = await async_client.patch(path, json=body, headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 200, response.text
