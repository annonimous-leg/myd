from __future__ import annotations
import os

import time
from datetime import datetime, timezone

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from db.models import ApiLog, AsyncSessionLocal
from .event_bus import EventBus
from .observability import build_logger, correlate_request
from .policy_engine import PolicyEngine
from .workflow import WorkflowEngine

logger = build_logger()

class EnterpriseAuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = correlate_request(request)
        start = time.perf_counter()
        request.state.request_id = request_id
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

        try:
            async with AsyncSessionLocal() as db:
                db.add(
                    ApiLog(
                        endpoint=str(request.url.path),
                        method=request.method,
                        status_code=response.status_code,
                        response_time_ms=elapsed_ms,
                        ip_address=request.client.host if request.client else None,
                        user_agent=request.headers.get("user-agent"),
                        tenant_id=getattr(request.state, "tenant_id", None),
                        user_id=getattr(request.state, "user_id", None),
                        timestamp=datetime.now(timezone.utc),
                    )
                )
                await db.commit()
        except Exception as exc:
            logger.info(f"[audit-middleware] {exc}")

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-ms"] = str(elapsed_ms)
        return response

def bootstrap_enterprise(app):
    app.state.event_bus = EventBus(redis_url=os.getenv("REDIS_URL"), require_durable=os.getenv("ENVIRONMENT","development").lower()=="production")
    app.state.policy_engine = PolicyEngine()
    app.state.workflow_engine = WorkflowEngine()
    app.add_middleware(EnterpriseAuditMiddleware)
    logger.info("Enterprise bootstrap ready")
    return app
