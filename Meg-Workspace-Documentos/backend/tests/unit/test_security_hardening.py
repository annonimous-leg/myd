from __future__ import annotations

import os
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.security_headers import SecurityHeadersMiddleware


def test_security_headers_are_added():
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, production=True)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/ping")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Strict-Transport-Security"].startswith("max-age=31536000")
    assert "Content-Security-Policy" in response.headers


def test_production_settings_reject_loopback_and_sqlite():
    with pytest.raises(ValueError):
        Settings(
            ENVIRONMENT="production",
            DATABASE_URL="sqlite+aiosqlite:///./local.db",
            REDIS_URL="redis://localhost:6379/0",
            CELERY_BROKER_URL="redis://localhost:6379/1",
            CELERY_RESULT_BACKEND="redis://localhost:6379/2",
            SECRET_KEY="x" * 32,
            CORS_ALLOWED_ORIGINS=["http://localhost:5173"],
        )


def test_production_settings_accept_postgres_and_external_origins():
    s = Settings(
        ENVIRONMENT="production",
        DATABASE_URL="postgresql+asyncpg://user:pass@db.example.com:5432/megalodon",
        DATABASE_SSL_MODE="verify-full",
        REDIS_URL="redis://redis.example.com:6379/0",
        CELERY_BROKER_URL="redis://redis.example.com:6379/1",
        CELERY_RESULT_BACKEND="redis://redis.example.com:6379/2",
        SECRET_KEY="x" * 32,
        CORS_ALLOWED_ORIGINS=["https://app.example.com"],
        SUPABASE_URL="https://storage.example.com",
        SUPABASE_SERVICE_KEY="production-service-key",
    )
    assert s.is_production is True
    assert s.database_async_url.startswith("postgresql+asyncpg://")
