"""Tests de integración para política de fallo Redis.

Verifica:
- Rate limiter con Redis caído en fail-closed
- Token revocation con Redis caído
- Configuración de entorno
"""
import os
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


class TestRedisFailClosedIntegration:
    def test_env_var_fail_closed(self, monkeypatch):
        """REDIS_FAILURE_POLICY=fail_closed debe activar fail-closed."""
        monkeypatch.setenv("REDIS_FAILURE_POLICY", "fail_closed")
        # Simular recarga de config
        from app.core.redis_client import RedisClient
        client = RedisClient()
        assert client._fail_closed is True

    def test_env_var_fail_open(self, monkeypatch):
        """REDIS_FAILURE_POLICY=fail_open debe mantener fail-open."""
        monkeypatch.setenv("REDIS_FAILURE_POLICY", "fail_open")
        from app.core.redis_client import RedisClient
        client = RedisClient()
        assert client._fail_closed is False

    @pytest.mark.asyncio
    async def test_rate_limiter_fail_closed(self, monkeypatch):
        """Rate limiter en fail-closed debe rechazar cuando Redis caído."""
        from fastapi import HTTPException
        monkeypatch.setenv("REDIS_FAILURE_POLICY", "fail_closed")

        from tezcatlipoca.services.redis_client import RedisClient as TezRedis
        client = TezRedis()
        client._client = None

        with pytest.raises(HTTPException) as exc_info:
            await client.check_rate_limit("test_key", 100, 60)
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_rate_limiter_fail_open(self, monkeypatch):
        """Rate limiter en fail-open debe permitir cuando Redis caído."""
        monkeypatch.setenv("REDIS_FAILURE_POLICY", "fail_open")

        from tezcatlipoca.services.redis_client import RedisClient as TezRedis
        client = TezRedis()
        client._client = None

        allowed, remaining = await client.check_rate_limit("test_key", 100, 60)
        assert allowed is True
        assert remaining == 100


class TestSecurityControlsWithRedisDown:
    @pytest.mark.asyncio
    async def test_token_revocation_fail_closed(self, monkeypatch):
        """Token revocation debe fallar cerrado si Redis no disponible."""
        monkeypatch.setattr("app.config.settings.security_protection_fail_closed", True)
        from app.core.token_revocation import TokenRevocation
        from app.core.errors import SecurityControlUnavailableException
        failed_backend = AsyncMock()
        failed_backend.exists.side_effect = ConnectionError('Redis unavailable')
        monkeypatch.setattr('app.core.token_revocation._redis_instance', lambda: failed_backend)
        with pytest.raises(SecurityControlUnavailableException) as error:
            await TokenRevocation().is_revoked('test_jti')
        assert error.value.status_code == 503
        assert error.value.details['token_kind'] == 'access'

    def test_settings_fail_closed_flag(self, monkeypatch):
        """security_protection_fail_closed en settings."""
        monkeypatch.setattr("app.config.settings.security_protection_fail_closed", True)
        from app.core.redis_client import RedisClient
        client = RedisClient()
        assert client._fail_closed is True
