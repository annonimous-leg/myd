"""Global Rate Limiting Middleware for TU-OSINT (standalone mode).

BUG ORIGINAL: usaba un dict de proceso (`_rate_store`) como store. Dos
problemas reales: (1) no funciona correctamente con más de un
worker/réplica -- cada proceso ve su propio dict, así que el límite
nominal termina multiplicado por N_workers; (2) fuga de memoria -- una
IP que pega una sola vez y no vuelve se queda en el dict para siempre,
sin TTL ni eviction. Además el client_id mezclaba IP con
`hash(user-agent) % 10000`, y el hash de strings en Python está
aleatorizado por proceso (PYTHONHASHSEED), así que ese bucketing ni
siquiera era estable entre reinicios, y con ~119 user-agents distintos
ya es esperable una colisión (cumpleaños), lo que podía rate-limitear
en grupo a usuarios sin relación entre sí solo por compartir bucket.

AHORA: delega en core.rate_limit (Redis sliding-window, mismo mecanismo
que ya usan los routers tras la sesión de corrección de la tarea C).
Este middleware sigue sin usarse en el deploy real -- app/main.py monta
los routers de tezcatlipoca directamente y nunca ejecuta este main.py
standalone -- pero si algún día se levanta tezcatlipoca por separado
(dev, tests, o una eventual re-separación de servicios), ahora es
correcto en vez de silenciosamente aproximado.
"""
import os
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from core.rate_limit import _client_id, _ensure_connected
from services.redis_client import redis_client

RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "100"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))  # seconds

_EXEMPT_PATHS = {"/health", "/api/health", "/", "/favicon.ico"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Global rate limiting middleware applied to all requests."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        await _ensure_connected()
        key = f"{_client_id(request)}:{request.url.path}"
        allowed, remaining = await redis_client.check_rate_limit(
            key, RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW
        )

        if not allowed:
            return Response(
                content='{"detail":"Rate limit exceeded. Try again later."}',
                status_code=429,
                headers={
                    "Content-Type": "application/json",
                    "Retry-After": str(RATE_LIMIT_WINDOW),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(RATE_LIMIT_REQUESTS)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Window"] = str(RATE_LIMIT_WINDOW)
        return response
