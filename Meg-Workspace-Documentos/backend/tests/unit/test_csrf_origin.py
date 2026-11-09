"""Platform-wide CSRF behavior for ambient browser cookies."""
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.csrf import BrowserOriginCSRFMiddleware
from app.core.deps import REFRESH_COOKIE_NAME, SESSION_COOKIE_NAME


@pytest.fixture
def csrf_app():
    app = FastAPI()
    app.add_middleware(
        BrowserOriginCSRFMiddleware,
        trusted_origins=["https://app.megalodon.example", "https://api.megalodon.example"],
    )

    @app.post("/mutate")
    async def mutate():
        return {"ok": True}

    @app.get("/read")
    async def read():
        return {"ok": True}

    @app.post("/api/v1/auth/session/login")
    async def session_login():
        return {"ok": True}

    @app.post("/api/v1/auth/session/refresh")
    async def session_refresh():
        return {"ok": True}

    return app


@pytest.mark.asyncio
async def test_cookie_mutation_requires_exact_trusted_origin(csrf_app):
    async with AsyncClient(
        transport=ASGITransport(app=csrf_app),
        base_url="https://api.megalodon.example",
    ) as client:
        client.cookies.set(SESSION_COOKIE_NAME, "opaque")

        missing = await client.post("/mutate")
        hostile = await client.post(
            "/mutate", headers={"Origin": "https://evil.example"}
        )
        trusted = await client.post(
            "/mutate", headers={"Origin": "https://app.megalodon.example"}
        )
        same_origin = await client.post(
            "/mutate", headers={"Origin": "https://api.megalodon.example"}
        )
        unconfigured = await client.post(
            "/mutate", headers={"Origin": "https://other-api.megalodon.example"}
        )

    assert missing.status_code == 403
    assert hostile.status_code == 403
    assert trusted.status_code == 200
    assert same_origin.status_code == 200
    assert unconfigured.status_code == 403


@pytest.mark.asyncio
async def test_refresh_cookie_is_covered_and_bearer_clients_are_not_ambient(csrf_app):
    async with AsyncClient(
        transport=ASGITransport(app=csrf_app),
        base_url="https://api.megalodon.example",
    ) as client:
        client.cookies.set(REFRESH_COOKIE_NAME, "opaque")
        blocked = await client.post("/mutate")
        bearer = await client.post(
            "/mutate", headers={"Authorization": "Bearer explicit-api-token"}
        )
        safe_read = await client.get("/read")

    assert blocked.status_code == 403
    assert bearer.status_code == 200
    assert safe_read.status_code == 200


@pytest.mark.asyncio
async def test_public_mutation_without_ambient_cookie_remains_available(csrf_app):
    async with AsyncClient(
        transport=ASGITransport(app=csrf_app),
        base_url="https://api.megalodon.example",
    ) as client:
        response = await client.post("/mutate")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_browser_login_requires_origin_before_first_cookie(csrf_app):
    async with AsyncClient(
        transport=ASGITransport(app=csrf_app),
        base_url="https://api.megalodon.example",
    ) as client:
        missing = await client.post("/api/v1/auth/session/login")
        hostile = await client.post(
            "/api/v1/auth/session/login", headers={"Origin": "https://evil.example"}
        )
        trusted = await client.post(
            "/api/v1/auth/session/login",
            headers={"Origin": "https://app.megalodon.example"},
        )
        refresh_missing = await client.post("/api/v1/auth/session/refresh")

    assert missing.status_code == 403
    assert hostile.status_code == 403
    assert trusted.status_code == 200
    assert refresh_missing.status_code == 403
