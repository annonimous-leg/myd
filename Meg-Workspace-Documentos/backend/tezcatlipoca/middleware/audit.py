"""Audit middleware for TU-OSINT.

Logs all API requests with user identification for compliance and abuse detection.
"""

import time
import logging
from datetime import datetime, timezone
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from db.models import ApiLog, get_async_db

logger = logging.getLogger("tu-osint.audit")


class AuditMiddleware(BaseHTTPMiddleware):
    """Log every API request with user, endpoint, and timing info."""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # Process request
        response = await call_next(request)

        # Skip logging for health checks and static assets
        if request.url.path in ["/health", "/api/health", "/", "/favicon.ico"]:
            return response

        # Calculate response time
        response_time_ms = round((time.time() - start_time) * 1000, 2)

        # Get user info from request state (set by auth middleware)
        user_id = getattr(request.state, "user_id", None)
        username = getattr(request.state, "username", None)

        # Get client info
        forwarded = request.headers.get("X-Forwarded-For")
        client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
        user_agent = request.headers.get("user-agent", "")

        # Log to application logger
        logger.info(
            f"API {request.method} {request.url.path} - {response.status_code} - "
            f"{response_time_ms}ms - user={username or 'anonymous'} - ip={client_ip}"
        )

        # Store in request state for potential DB logging (async background task)
        request.state.audit_log = {
            "user_id": user_id,
            "endpoint": str(request.url.path),
            "method": request.method,
            "status_code": response.status_code,
            "response_time_ms": response_time_ms,
            "ip_address": client_ip,
            "user_agent": user_agent,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        return response
