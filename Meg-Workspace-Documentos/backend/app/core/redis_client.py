# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""Cliente Redis compartido con circuit breaker, health checks,
reconexión automática y política de fallo configurable.

En PRODUCCIÓN (FAIL_CLOSED):
- Si Redis no está disponible, TODAS las operaciones de seguridad
  (revocación de JWT, rate limiting, sesiones) RECHAZAN la operación
  con SecurityControlUnavailableException (HTTP 503).
- El circuit breaker evita que cada request intente reconectar,
  saturando logs, CPU y la red.
- Health checks periódicos detectan recuperación automática.

En DESARROLLO (FAIL_OPEN, explícito vía env var):
- Se permite operar sin Redis, pero CADA operación de seguridad que
  no pudo verificarse se loguea como WARNING con trazabilidad completa.
- NUNCA se usa en producción.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

import structlog

from app.config import settings
from app.core.errors import SecurityControlUnavailableException

logger = structlog.get_logger()

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError as _redis_import_exc:
    redis = None  # type: ignore[assignment]
    REDIS_AVAILABLE = False

CIRCUIT_FAILURE_THRESHOLD = 5
CIRCUIT_RECOVERY_TIMEOUT_SECONDS = 30.0
CIRCUIT_HALF_OPEN_MAX_TRIES = 3
RETRY_MAX_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 0.5
RETRY_MAX_DELAY_SECONDS = 8.0
HEALTH_CHECK_INTERVAL_SECONDS = 30.0


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    failure_threshold: int = CIRCUIT_FAILURE_THRESHOLD
    recovery_timeout: float = CIRCUIT_RECOVERY_TIMEOUT_SECONDS
    half_open_max_tries: int = CIRCUIT_HALF_OPEN_MAX_TRIES
    state: CircuitState = field(default=CircuitState.CLOSED)
    failure_count: int = field(default=0)
    last_failure_time: Optional[float] = field(default=None)
    half_open_tries: int = field(default=0)

    def record_success(self) -> None:
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_tries += 1
            if self.half_open_tries >= self.half_open_max_tries:
                self._close()
        else:
            self.failure_count = 0

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        if self.state == CircuitState.HALF_OPEN:
            self._open()
        elif self.failure_count >= self.failure_threshold:
            self._open()

    def can_attempt(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if self.last_failure_time is not None:
                elapsed = time.monotonic() - self.last_failure_time
                if elapsed >= self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_tries = 0
                    logger.info("circuit_breaker_half_open", control="redis")
                    return True
            return False
        if self.state == CircuitState.HALF_OPEN:
            return True
        return True

    def _open(self) -> None:
        if self.state != CircuitState.OPEN:
            self.state = CircuitState.OPEN
            logger.error("circuit_breaker_opened", control="redis", failure_count=self.failure_count)

    def _close(self) -> None:
        old = self.state
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.half_open_tries = 0
        self.last_failure_time = None
        if old != CircuitState.CLOSED:
            logger.info("circuit_breaker_closed", control="redis")


class RedisClient:
    def __init__(self) -> None:
        self._client: Optional[Any] = None
        self._circuit = CircuitBreaker()
        self._health_check_task: Optional[asyncio.Task] = None
        self._shutdown_event: Optional[asyncio.Event] = None

    @property
    def _fail_closed(self) -> bool:
        import os
        override = getattr(self, "_force_fail_closed", None)
        if override is not None:
            return bool(override)
        env_policy = os.getenv("REDIS_FAILURE_POLICY")
        if env_policy is not None:
            return env_policy.strip().lower() == "fail_closed"
        return bool(getattr(settings, "security_protection_fail_closed", False))

    @_fail_closed.setter
    def _fail_closed(self, value: bool) -> None:
        self._force_fail_closed = bool(value)

    @property
    def _redis_url(self) -> str:
        return str(getattr(settings, "REDIS_URL", "redis://localhost:6379/0"))

    async def connect(self) -> bool:
        if not REDIS_AVAILABLE:
            msg = "Redis no está instalado. En producción esto es un error crítico de despliegue."
            logger.critical("redis_import_failed", control="redis", reason=msg)
            if self._fail_closed:
                raise SecurityControlUnavailableException(
                    "Redis no disponible: paquete no instalado (import_failed)",
                    details={"control": "redis_connect", "reason": "import_failed"},
                )
            return False

        if self._client is not None:
            try:
                await self._client.ping()
                return True
            except Exception as exc:
                logger.warning("redis_ping_failed_on_reuse", error=str(exc))
                await self._safe_close()

        if not self._circuit.can_attempt():
            logger.warning("redis_circuit_open", control="redis", circuit_state=self._circuit.state.value)
            if self._fail_closed:
                raise SecurityControlUnavailableException(
                    "Redis no disponible: circuit breaker abierto",
                    details={"control": "redis_connect", "reason": "circuit_breaker_open",
                             "circuit_state": self._circuit.state.value},
                )
            return False

        last_exc: Optional[Exception] = None
        for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
            try:
                self._client = redis.from_url(self._redis_url, decode_responses=True)
                await self._client.ping()
                self._circuit.record_success()
                logger.info("redis_connected", control="redis", attempt=attempt,
                           url=self._redis_url.replace("://", "://***@"))
                self._start_health_check()
                return True
            except Exception as exc:
                last_exc = exc
                self._circuit.record_failure()
                logger.warning("redis_connection_attempt_failed", control="redis", attempt=attempt,
                              max_attempts=RETRY_MAX_ATTEMPTS, error=str(exc))
                if attempt < RETRY_MAX_ATTEMPTS:
                    delay = min(RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)), RETRY_MAX_DELAY_SECONDS)
                    await asyncio.sleep(delay)

        logger.error("redis_connection_failed_after_retries", control="redis", max_attempts=RETRY_MAX_ATTEMPTS,
                    error=str(last_exc) if last_exc else "unknown")
        if self._fail_closed:
            raise SecurityControlUnavailableException(
                "Redis no disponible después de reintentos",
                details={"control": "redis_connect", "reason": "max_retries_exceeded",
                         "error": str(last_exc) if last_exc else "unknown"},
            ) from last_exc
        return False

    async def disconnect(self) -> None:
        self._stop_health_check()
        await self._safe_close()

    async def _safe_close(self) -> None:
        if self._client is None:
            return
        try:
            await self._client.aclose()
            logger.info("redis_disconnected", control="redis")
        except Exception as exc:
            logger.error("redis_disconnect_error", control="redis", error=str(exc))
        finally:
            self._client = None

    def _start_health_check(self) -> None:
        if self._health_check_task is not None and not self._health_check_task.done():
            return
        self._shutdown_event = asyncio.Event()
        self._health_check_task = asyncio.create_task(self._health_check_loop(), name="redis_health_check")

    def _stop_health_check(self) -> None:
        if self._shutdown_event is not None:
            self._shutdown_event.set()
        if self._health_check_task is not None and not self._health_check_task.done():
            self._health_check_task.cancel()

    async def _health_check_loop(self) -> None:
        while True:
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=HEALTH_CHECK_INTERVAL_SECONDS)
                return
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                return
            if self._client is None:
                continue
            try:
                await self._client.ping()
            except Exception as exc:
                logger.warning("redis_health_check_failed", control="redis", error=str(exc))
                self._circuit.record_failure()
                await self._safe_close()

    async def execute(self, operation: str, operation_factory: Callable[[Any], Any]) -> Any:
        if self._client is None:
            connected = await self.connect()
            if not connected:
                if self._fail_closed:
                    raise SecurityControlUnavailableException(
                        f"Redis no disponible para operación '{operation}'",
                        details={"control": operation, "reason": "not_connected"},
                    )
                logger.warning("redis_operation_skipped", control=operation, reason="not_connected_fail_open")
                return None

        if not self._circuit.can_attempt():
            if self._fail_closed:
                raise SecurityControlUnavailableException(
                    f"Redis no disponible para operación '{operation}': circuito abierto",
                    details={"control": operation, "reason": "circuit_breaker_open",
                             "circuit_state": self._circuit.state.value},
                )
            logger.warning("redis_operation_skipped_circuit_open", control=operation,
                          circuit_state=self._circuit.state.value)
            return None

        try:
            result = await operation_factory(self._client)
            self._circuit.record_success()
            return result
        except Exception as exc:
            self._circuit.record_failure()
            logger.error("redis_operation_failed", control=operation, error=str(exc),
                        circuit_state=self._circuit.state.value)
            if self._fail_closed:
                raise SecurityControlUnavailableException(
                    f"Redis falló en operación '{operation}'",
                    details={"control": operation, "reason": "redis_error", "error": str(exc)},
                ) from exc
            return None

    async def get(self, key: str) -> Optional[str]:
        return await self.execute("get", lambda client: client.get(key))

    async def setex(self, key: str, seconds: int, value: str) -> bool:
        result = await self.execute("setex", lambda client: client.setex(key, seconds, value))
        return result is not None

    async def exists(self, key: str) -> int:
        result = await self.execute("exists", lambda client: client.exists(key))
        return result or 0

    async def delete(self, key: str) -> int:
        result = await self.execute("delete", lambda client: client.delete(key))
        return result or 0

    async def hset(self, key: str, mapping: dict) -> int:
        result = await self.execute("hset", lambda client: client.hset(key, mapping=mapping))
        return result or 0

    async def hgetall(self, key: str) -> dict:
        result = await self.execute("hgetall", lambda client: client.hgetall(key))
        return result or {}

    async def expire(self, key: str, seconds: int) -> bool:
        result = await self.execute("expire", lambda client: client.expire(key, seconds))
        return bool(result)

    async def eval(self, script: str, numkeys: int, *args):
        """Execute the atomic refresh-rotation script on the shared backend."""
        return await self.execute('eval', lambda client: client.eval(script, numkeys, *args))

    async def pipeline(self):
        if self._client is None:
            connected = await self.connect()
            if not connected:
                if self._fail_closed:
                    raise SecurityControlUnavailableException(
                        "Redis no disponible para crear pipeline",
                        details={"control": "pipeline", "reason": "not_connected"},
                    )
                return None
        return self._client.pipeline()

    async def publish(self, channel: str, message: str) -> int:
        result = await self.execute("publish", lambda client: client.publish(channel, message))
        return result or 0

    async def pubsub(self):
        if self._client is None:
            connected = await self.connect()
            if not connected:
                if self._fail_closed:
                    raise SecurityControlUnavailableException(
                        "Redis no disponible para crear pubsub",
                        details={"control": "pubsub", "reason": "not_connected"},
                    )
                return None
        return self._client.pubsub()

    def is_healthy(self) -> bool:
        return self._client is not None and self._circuit.state == CircuitState.CLOSED

    def get_circuit_state(self) -> str:
        return self._circuit.state.value

    def get_metrics(self) -> dict:
        return {
            "circuit_state": self._circuit.state.value,
            "failure_count": self._circuit.failure_count,
            "connected": self._client is not None,
            "fail_closed": self._fail_closed,
        }


_redis_client: Optional[RedisClient] = None


def get_redis() -> Optional[RedisClient]:
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
    return _redis_client


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.disconnect()
        _redis_client = None
        logger.info("redis_global_closed", control="redis")
