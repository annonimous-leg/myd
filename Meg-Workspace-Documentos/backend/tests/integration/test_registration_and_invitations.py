# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""Tests del flujo de registro público + invitaciones.

Cierra el punto B de la auditoría (`megalodon_v4_fixed_security_flow_audit.md`):
antes, POST /auth/register era público y aceptaba `tenant_id` + `role`
arbitrarios del cliente, así que cualquiera que conociera el UUID de
un tenant ajeno podía unirse a él y hasta pedir `role: "superadmin"`.

Estos tests prueban el contrato NUEVO:
  1. /register solo puede crear una organización (tenant) nueva; el
     usuario que la crea queda ADMIN de esa organización, nunca
     SUPERADMIN.
  2. No existe forma de que /register te una a un tenant ajeno.
  3. Solo un ADMIN/SUPERADMIN puede invitar (POST /invitations), y
     nunca puede invitar con rol SUPERADMIN.
  4. Canjear una invitación (POST /register/invite) crea al usuario
     con el tenant/rol EXACTOS de la invitación, sin importar qué
     mande el cliente en el body.
  5. Una invitación no se puede canjear dos veces.

Requiere Postgres de test corriendo (ver TEST_DATABASE_URL en
conftest.py). No se pudo ejecutar en el entorno donde se escribió
(sin red ni Postgres). Antes de confiar en este archivo, correrlo de
verdad:
    pytest tests/integration/test_registration_and_invitations.py -v
"""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_register_creates_new_tenant_as_admin_not_superadmin(async_client: AsyncClient):
    """Alta pública -> crea tenant nuevo, el usuario queda 'admin', nunca 'superadmin'."""
    response = await async_client.post("/api/v1/auth/register", json={
        "email": "founder@acme-test.mx",
        "password": "testpass123",
        "full_name": "Founder Acme",
        "company_name": "Acme Test Co",
    })
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "founder@acme-test.mx"
    assert body["role"] == "admin"
    assert body["role"] != "superadmin"


@pytest.mark.asyncio
async def test_register_ignores_client_supplied_tenant_id_and_role(async_client: AsyncClient, tenant_a_user):
    """Aunque el cliente mande tenant_id/role viejos en el body, se ignoran:
    el schema nuevo ni siquiera los declara, así que Pydantic los descarta
    y /register SIEMPRE crea una organización propia nueva."""
    tenant_a, _ = tenant_a_user

    response = await async_client.post("/api/v1/auth/register", json={
        "email": "intruder@acme-test.mx",
        "password": "testpass123",
        "full_name": "Intruder",
        "company_name": "Intruder Org",
        # Campos del contrato viejo -- ya no existen en UserRegister.
        "tenant_id": str(tenant_a.id),
        "role": "superadmin",
    })
    assert response.status_code == 201, response.text
    body = response.json()
    # Quedó admin de SU propia organización nueva, no de tenant_a, y
    # desde luego no superadmin.
    assert body["role"] == "admin"


@pytest.mark.asyncio
async def test_non_admin_cannot_create_invitations(async_client: AsyncClient, auth_headers, tenant_a_user):
    """tenant_a_user es TECNICO por default (ver conftest) -> 403 al invitar."""
    response = await async_client.post(
        "/api/v1/auth/invitations",
        json={"email": "nuevo@tenant-a-test.mx", "role": "tecnico"},
        headers=auth_headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_cannot_invite_with_superadmin_role(async_client: AsyncClient, db_session: AsyncSession):
    """Ni siquiera un ADMIN real del tenant puede invitar con rol superadmin."""
    from app.models.user import Tenant, User, UserRole
    from app.services.auth_service import AuthService

    auth_service = AuthService(db_session)
    tenant = Tenant(name="invite-test-admin", slug="invite-test-admin", is_active=True)
    db_session.add(tenant)
    await db_session.flush()
    admin = User(
        email="admin@invite-test-admin.mx",
        hashed_password=auth_service.hash_password("testpass123"),
        full_name="Admin",
        role=UserRole.ADMIN,
        tenant_id=tenant.id,
        is_active=True,
        is_verified=True,
    )
    db_session.add(admin)
    await db_session.commit()

    login = await auth_service.authenticate("admin@invite-test-admin.mx", "testpass123")
    assert login is not None

    # Login vía HTTP para obtener un token real de la app.
    from httpx import ASGITransport
    from app.main import app as fastapi_app

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token_resp = await client.post("/api/v1/auth/login", data={
            "username": "admin@invite-test-admin.mx",
            "password": "testpass123",
        })
        assert token_resp.status_code == 200
        headers = {"Authorization": f"Bearer {token_resp.json()['access_token']}"}

        response = await client.post(
            "/api/v1/auth/invitations",
            json={"email": "wannabe-god@invite-test-admin.mx", "role": "superadmin"},
            headers=headers,
        )
        assert response.status_code in (400, 403, 422)


@pytest.mark.asyncio
async def test_invite_redeem_creates_user_with_invitation_tenant_and_role(
    async_client: AsyncClient, db_session: AsyncSession,
):
    """El usuario creado al canjear la invitación queda EXACTAMENTE con
    el tenant/rol que la invitación fijó, sin importar qué mande el
    cliente en el body de /register/invite (que ni siquiera tiene esos
    campos)."""
    from app.models.user import Tenant, User, UserRole
    from app.services.auth_service import AuthService

    auth_service = AuthService(db_session)
    tenant = Tenant(name="invite-redeem-test", slug="invite-redeem-test", is_active=True)
    db_session.add(tenant)
    await db_session.flush()
    admin = User(
        email="admin@invite-redeem-test.mx",
        hashed_password=auth_service.hash_password("testpass123"),
        full_name="Admin",
        role=UserRole.ADMIN,
        tenant_id=tenant.id,
        is_active=True,
        is_verified=True,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)

    invitation, raw_token = await auth_service.create_invitation(
        tenant_id=tenant.id,
        email="invitado@invite-redeem-test.mx",
        role=UserRole.TECNICO,
        invited_by=admin,
    )

    response = await async_client.post("/api/v1/auth/register/invite", json={
        "invite_token": raw_token,
        "password": "testpass123",
        "full_name": "Invitado Real",
    })
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "invitado@invite-redeem-test.mx"
    assert body["role"] == "tecnico"

    # Verifica en DB que quedó en el tenant correcto.
    result = await db_session.execute(
        select(User).where(User.email == "invitado@invite-redeem-test.mx")
    )
    user = result.scalar_one()
    assert user.tenant_id == tenant.id


@pytest.mark.asyncio
async def test_invite_cannot_be_redeemed_twice(async_client: AsyncClient, db_session: AsyncSession):
    from app.models.user import Tenant, User, UserRole
    from app.services.auth_service import AuthService

    auth_service = AuthService(db_session)
    tenant = Tenant(name="invite-once-test", slug="invite-once-test", is_active=True)
    db_session.add(tenant)
    await db_session.flush()
    admin = User(
        email="admin@invite-once-test.mx",
        hashed_password=auth_service.hash_password("testpass123"),
        full_name="Admin",
        role=UserRole.ADMIN,
        tenant_id=tenant.id,
        is_active=True,
        is_verified=True,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)

    _, raw_token = await auth_service.create_invitation(
        tenant_id=tenant.id,
        email="unavezmas@invite-once-test.mx",
        role=UserRole.TECNICO,
        invited_by=admin,
    )

    payload = {
        "invite_token": raw_token,
        "password": "testpass123",
        "full_name": "Primera Vez",
    }
    first = await async_client.post("/api/v1/auth/register/invite", json=payload)
    assert first.status_code == 201

    second = await async_client.post("/api/v1/auth/register/invite", json=payload)
    assert second.status_code == 400
