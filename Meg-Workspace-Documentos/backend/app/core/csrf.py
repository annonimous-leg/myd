"""CSRF boundary for browser cookie sessions.

Unsafe browser-session requests must carry exactly one trusted Origin. API
clients using explicit Bearer authorization are not ambiently authenticated.
The login endpoint is checked even before its first cookie exists.
"""
from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.core.deps import REFRESH_COOKIE_NAME, SESSION_COOKIE_NAME

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_BROWSER_SESSION_ENDPOINTS = {
    "/api/v1/auth/session/login",
    "/api/v1/auth/session/refresh",
}


def _canonical_origin(value: str) -> str | None:
    value = value.strip()
    if not value or value == "null":
        return None
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    if (
        parts.scheme not in {"http", "https"}
        or not parts.netloc
        or parts.path != ""
        or parts.query
        or parts.fragment
        or parts.username
        or parts.password
    ):
        return None
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}"


class BrowserOriginCSRFMiddleware(BaseHTTPMiddleware):
    """Reject unsafe cookie-authenticated requests without a trusted Origin."""

    def __init__(self, app, *, trusted_origins: Iterable[str] | None = None) -> None:
        super().__init__(app)
        source = settings.CORS_ALLOWED_ORIGINS if trusted_origins is None else trusted_origins
        self._trusted = {
            canonical
            for origin in source
            if (canonical := _canonical_origin(str(origin))) is not None
        }

    async def dispatch(self, request: Request, call_next):
        if request.method.upper() not in _UNSAFE_METHODS:
            return await call_next(request)

        is_session_endpoint = request.url.path in _BROWSER_SESSION_ENDPOINTS
        has_browser_cookie = (
            SESSION_COOKIE_NAME in request.cookies
            or REFRESH_COOKIE_NAME in request.cookies
        )
        auth_header = request.headers.get("authorization", "")
        has_explicit_bearer = auth_header.lower().startswith("bearer ")

        # Login must be protected before any cookie exists. For other routes,
        # only requests authenticated by ambient cookies need the origin gate.
        if not is_session_endpoint and (not has_browser_cookie or has_explicit_bearer):
            return await call_next(request)

        origins = request.headers.getlist("origin")
        # Trust is configuration-driven. Do not dynamically trust request.url's
        # Host: that value can be influenced by an untrusted Host header.
        trusted = self._trusted
        supplied = _canonical_origin(origins[0]) if len(origins) == 1 else None
        if supplied is None or supplied not in trusted:
            return JSONResponse(
                status_code=403,
                content={
                    "error": "CSRF_ORIGIN_REJECTED",
                    "message": "Origen de la operación autenticada no autorizado",
                },
                headers={"Cache-Control": "no-store"},
            )
        return await call_next(request)
