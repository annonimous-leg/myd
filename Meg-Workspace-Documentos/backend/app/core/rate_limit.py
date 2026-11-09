# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Rate limiting con Redis + sliding window.

La política de fallo se comparte con token_revocation.py:
- fail-open: permitir cuando Redis falla, pero loguear el incidente;
- fail-closed: responder 503 si la protección no puede verificarse.
"""
from __future__ import annotations

import time
from uuid import uuid4
from typing import Optional

import structlog
from fastapi import Request, HTTPException

from app.config import settings
from app.core.redis_client import get_redis

logger = structlog.get_logger()


class RateLimiter:
    """Rate limiter basado en Redis con sliding window."""

    def __init__(self, redis_client=None):
        self.redis = redis_client if redis_client is not None else get_redis()
        self.enabled = self.redis is not None

    async def is_allowed(
        self,
        key: str,
        max_requests: int = 100,
        window_seconds: int = 60,
    ) -> Optional[bool]:
        """Devuelve True/False o None si la verificación no fue posible."""
        if not self.enabled:
            return None

        now = int(time.time())
        window_start = now - window_seconds
        member = f"{now}:{uuid4().hex}"

        try:
            pipe = await self.redis.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zcard(key)
            pipe.zadd(key, {member: now})
            pipe.expire(key, window_seconds)
            results = await pipe.execute()
            current_count = int(results[1] or 0)
            allowed = current_count < max_requests
            logger.debug(
                "rate_limit_checked",
                key=key,
                current_count=current_count,
                max_requests=max_requests,
                window_seconds=window_seconds,
                allowed=allowed,
            )
            return allowed
        except Exception as exc:  # pragma: no cover - backend failure path
            logger.warning(
                "rate_limit_backend_error",
                key=key,
                error=str(exc),
                max_requests=max_requests,
                window_seconds=window_seconds,
            )
            return None


rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    global rate_limiter
    if rate_limiter is None:
        rate_limiter = RateLimiter()
    else:
        if not rate_limiter.enabled:
            rate_limiter.redis = get_redis()
            rate_limiter.enabled = rate_limiter.redis is not None
    return rate_limiter


async def rate_limit_dependency(
    request: Request,
    max_requests: int = 100,
    window_seconds: int = 60,
):
    limiter = get_rate_limiter()

    client_ip = request.client.host if request.client else "unknown"
    # Dependencies run after route matching, so use the route template rather
    # than the concrete URL. UUID/path parameters must share one quota bucket.
    route = request.scope.get("route")
    endpoint = getattr(route, "path", None) or request.url.path
    # The same path may use a 100/min read policy and a 10/min write policy.
    # Reads must not exhaust the write quota before its first operation.
    method = request.method.upper()
    key = f"rate_limit:{client_ip}:{method}:{endpoint}"

    allowed = await limiter.is_allowed(key, max_requests, window_seconds)
    if allowed is None:
        if settings.security_protection_fail_closed:
            logger.error(
                "rate_limit_unavailable_fail_closed",
                client_ip=client_ip,
                endpoint=endpoint,
                max_requests=max_requests,
                window_seconds=window_seconds,
            )
            raise HTTPException(
                status_code=503,
                detail="Servicio de rate limiting no disponible",
            )
        logger.warning(
            "rate_limit_unavailable_fail_open",
            client_ip=client_ip,
            endpoint=endpoint,
            max_requests=max_requests,
            window_seconds=window_seconds,
        )
        return True

    if not allowed:
        logger.warning(
            "rate_limit_exceeded",
            client_ip=client_ip,
            endpoint=endpoint,
            max_requests=max_requests,
            window_seconds=window_seconds,
        )
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Max {max_requests} requests per {window_seconds}s",
            headers={"Retry-After": str(window_seconds)},
        )
    return True


async def rate_limit_strict(request: Request):
    return await rate_limit_dependency(request, max_requests=10, window_seconds=60)


async def rate_limit_standard(request: Request):
    return await rate_limit_dependency(request, max_requests=100, window_seconds=60)
