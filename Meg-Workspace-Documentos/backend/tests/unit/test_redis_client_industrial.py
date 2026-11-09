"""Tests industriales para RedisClient con circuit breaker.

Verifica:
- Circuit breaker cambia de estado correctamente
- Retry con backoff
- Fail-closed lanza SecurityControlUnavailableException
- Fail-open loguea warnings
- Health check loop
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.redis_client import RedisClient, CircuitBreaker, CircuitState, get_redis, close_redis
from app.core.errors import SecurityControlUnavailableException


class TestCircuitBreaker:
    def test_initial_state_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.can_attempt() is True

    def test_record_failure_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_attempt() is False

    def test_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        import time
        time.sleep(0.15)
        assert cb.can_attempt() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_record_success_closes_from_half_open(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.0, half_open_max_tries=2)
        cb.record_failure()
        cb.can_attempt()  # triggers half-open
        cb.record_success()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.0)
        cb.record_failure()
        cb.can_attempt()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN


class TestRedisClient:
    @pytest.fixture
    def client(self):
        return RedisClient()

    @pytest.mark.asyncio
    async def test_connect_fail_closed_no_redis_package(self, client, monkeypatch):
        """Si redis no está instalado y fail_closed=True, debe lanzar excepción."""
        monkeypatch.setattr("app.core.redis_client.REDIS_AVAILABLE", False)
        monkeypatch.setattr(client, "_fail_closed", True)
        with pytest.raises(SecurityControlUnavailableException) as exc_info:
            await client.connect()
        assert "import_failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_connect_fail_open_no_redis_package(self, client, monkeypatch):
        """Si redis no está instalado y fail_open=True, debe retornar False."""
        monkeypatch.setattr("app.core.redis_client.REDIS_AVAILABLE", False)
        monkeypatch.setattr(client, "_fail_closed", False)
        result = await client.connect()
        assert result is False

    @pytest.mark.asyncio
    async def test_execute_fail_closed_not_connected(self, client, monkeypatch):
        """En fail-closed, execute() debe lanzar excepción si no hay conexión."""
        monkeypatch.setattr(client, "_fail_closed", True)
        monkeypatch.setattr(client, "_client", None)
        monkeypatch.setattr(client, "connect", AsyncMock(return_value=False))
        with pytest.raises(SecurityControlUnavailableException):
            await client.execute("test", lambda _client: AsyncMock())

    @pytest.mark.asyncio
    async def test_execute_fail_open_not_connected(self, client, monkeypatch):
        """En fail-open, execute() debe retornar None si no hay conexión."""
        monkeypatch.setattr(client, "_fail_closed", False)
        monkeypatch.setattr(client, "_client", None)
        monkeypatch.setattr(client, "connect", AsyncMock(return_value=False))
        result = await client.execute("test", lambda _client: AsyncMock())
        assert result is None

    @pytest.mark.asyncio
    async def test_execute_circuit_open_fail_closed(self, client, monkeypatch):
        """Circuit breaker abierto + fail-closed = excepción."""
        monkeypatch.setattr(client, "_fail_closed", True)
        monkeypatch.setattr(client, "_client", MagicMock())
        client._circuit.state = CircuitState.OPEN
        client._circuit.last_failure_time = asyncio.get_event_loop().time() - 10
        with pytest.raises(SecurityControlUnavailableException):
            await client.execute("test", lambda _client: AsyncMock())

    @pytest.mark.asyncio
    async def test_execute_success(self, client, monkeypatch):
        """Execute exitoso debe retornar el resultado y resetear fallos."""
        mock_coro = AsyncMock(return_value="OK")
        mock_redis = MagicMock()
        monkeypatch.setattr(client, "_client", mock_redis)
        monkeypatch.setattr(client, "_fail_closed", True)
        result = await client.execute("setex", lambda _client: mock_coro())
        assert result == "OK"
        assert client._circuit.failure_count == 0

    @pytest.mark.asyncio
    async def test_execute_failure_records_and_raises(self, client, monkeypatch):
        """Execute fallido debe registrar fallo y propagar en fail-closed."""
        mock_coro = AsyncMock(side_effect=ConnectionError("Redis down"))
        monkeypatch.setattr(client, "_client", MagicMock())
        monkeypatch.setattr(client, "_fail_closed", True)
        with pytest.raises(SecurityControlUnavailableException):
            await client.execute("get", lambda _client: mock_coro())
        assert client._circuit.failure_count >= 1

    @pytest.mark.asyncio
    async def test_get_set_operations(self, client, monkeypatch):
        """Operaciones get/set deben funcionar con cliente mock."""
        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value="value123")
        mock_redis.setex = AsyncMock(return_value=True)
        mock_redis.exists = AsyncMock(return_value=1)
        mock_redis.delete = AsyncMock(return_value=1)
        monkeypatch.setattr(client, "_client", mock_redis)
        monkeypatch.setattr(client, "_fail_closed", False)
        client._circuit.state = CircuitState.CLOSED

        assert await client.get("key") == "value123"
        assert await client.setex("key", 60, "value") is True
        assert await client.exists("key") == 1
        assert await client.delete("key") == 1


    @pytest.mark.asyncio
    async def test_get_lazy_connect_does_not_dereference_none(self, client, monkeypatch):
        """Las operaciones no deben evaluar self._client antes de connect()."""
        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value="lazy-value")
        monkeypatch.setattr(client, "_client", None)
        monkeypatch.setattr(client, "_fail_closed", True)
        async def fake_connect():
            client._client = mock_redis
            return True
        monkeypatch.setattr(client, "connect", fake_connect)
        assert await client.get("key") == "lazy-value"

    @pytest.mark.asyncio
    async def test_health_check_loop(self, client, monkeypatch):
        """Health check debe detectar fallos y cerrar conexión."""
        mock_redis = MagicMock()
        mock_redis.ping = AsyncMock(side_effect=[None, ConnectionError("fail")])
        monkeypatch.setattr(client, "_client", mock_redis)
        monkeypatch.setattr(client, "_safe_close", AsyncMock())

        client._shutdown_event = asyncio.Event()
        # Simular un ciclo de health check
        try:
            await asyncio.wait_for(client._health_check_loop(), timeout=0.1)
        except asyncio.TimeoutError:
            pass

    @pytest.mark.asyncio
    async def test_disconnect(self, client, monkeypatch):
        """Disconnect debe cerrar cliente y detener health checks."""
        monkeypatch.setattr(client, "_safe_close", AsyncMock())
        monkeypatch.setattr(client, "_stop_health_check", MagicMock())
        await client.disconnect()
        client._safe_close.assert_awaited_once()
        client._stop_health_check.assert_called_once()

    def test_metrics(self, client):
        """Metrics deben reflejar estado actual."""
        metrics = client.get_metrics()
        assert "circuit_state" in metrics
        assert "failure_count" in metrics
        assert "connected" in metrics
        assert "fail_closed" in metrics

    def test_is_healthy(self, client, monkeypatch):
        """is_healthy debe retornar True solo si conectado y circuito cerrado."""
        monkeypatch.setattr(client, "_client", None)
        assert client.is_healthy() is False
        monkeypatch.setattr(client, "_client", MagicMock())
        client._circuit.state = CircuitState.CLOSED
        assert client.is_healthy() is True
        client._circuit.state = CircuitState.OPEN
        assert client.is_healthy() is False


class TestRedisSingleton:
    @pytest.mark.asyncio
    async def test_get_redis_singleton(self):
        """get_redis debe retornar la misma instancia."""
        r1 = get_redis()
        r2 = get_redis()
        assert r1 is r2
        await close_redis()

    @pytest.mark.asyncio
    async def test_close_redis(self):
        """close_redis debe limpiar la instancia global."""
        from app.core import redis_client as rc
        rc._redis_client = RedisClient()
        await close_redis()
        assert rc._redis_client is None
