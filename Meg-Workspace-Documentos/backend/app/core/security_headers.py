# Copyright © 2026 Cristian Rodriguez
# All rights reserved.

"""Seguridad HTTP de capa de transporte.

Este middleware añade cabeceras defensivas apropiadas para una API
empresarial JSON-first. No sustituye TLS, reverse proxy ni WAF: solo
endurece lo que la aplicación sí puede controlar.
"""
from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Añade cabeceras defensivas a todas las respuestas HTTP."""

    def __init__(self, app, *, production: bool | None = None) -> None:
        super().__init__(app)
        self._production = settings.is_production if production is None else bool(production)

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "no-referrer")
        headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=(), payment=(), usb=()",
        )
        headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
        headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        headers.setdefault("Cache-Control", "no-store")

        if self._production or request.url.scheme == "https":
            headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains; preload",
            )
            headers.setdefault(
                "Content-Security-Policy",
                "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            )

        return response
