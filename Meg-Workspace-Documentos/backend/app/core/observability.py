# Copyright © 2026 Cristian Rodriguez
# All rights reserved.

"""
Observabilidad unificada: request-id end-to-end + métricas OTel + Prometheus compat.

Este módulo conecta la lógica legacy de request-id (de tezcatlipoca) con el
SDK de OpenTelemetry. Las métricas se exportan DUAL: vía OTel Collector (para
Tempo/Grafana) Y vía endpoint /metrics en formato Prometheus (para
compatibilidad con scraping directo).

No hay duplicación funcional: OTel es la fuente de verdad; /metrics es un
adaptador de compatibilidad.
"""

import os
import time
import logging
import contextvars
from typing import Optional, Callable
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
    REGISTRY,
)
from opentelemetry import propagate, trace

from app.core.tracing import get_meter

logger = logging.getLogger(__name__)

# ─── Request ID (contextvar — funciona en async) ─────────────────────
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id")

def _fallback_route_label(_path: str) -> str:
    """Bound unmatched paths to one low-cardinality label."""
    return "/__unmatched__"


_STANDARD_HTTP_METHODS = frozenset({
    "GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT",
})


def _bounded_method_label(method: str) -> str:
    """Collapse non-standard methods to prevent attacker-controlled labels."""
    return method if method in _STANDARD_HTTP_METHODS else "OTHER"


def _matched_route_label(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", None) or _fallback_route_label(request.url.path)

# ─── Métricas Prometheus (compatibilidad legacy) ─────────────────────
# Estas métricas se registran en el REGISTRY global de prometheus-client
# y también se replican vía OTel Meter para que aparezcan en Tempo/Grafana.

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)
active_requests = Gauge(
    "http_active_requests",
    "Currently active HTTP requests",
    ["method", "endpoint"],
)

# ─── Métricas OTel (fuente de verdad) ────────────────────────────────
_otel_meter = None
_otel_request_counter = None
_otel_duration_histogram = None
_otel_active_updown = None


def _init_otel_metrics():
    """Inicializa métricas OTel una sola vez (lazy)."""
    global _otel_meter, _otel_request_counter, _otel_duration_histogram, _otel_active_updown
    if _otel_meter is not None:
        return
    _otel_meter = get_meter("app.core.observability")
    _otel_request_counter = _otel_meter.create_counter(
        "megalodon.http.requests.total",
        description="Total HTTP requests",
        unit="1",
    )
    _otel_duration_histogram = _otel_meter.create_histogram(
        "megalodon.http.request.duration",
        description="HTTP request duration",
        unit="s",
    )
    _otel_active_updown = _otel_meter.create_up_down_counter(
        "megalodon.http.active.requests",
        description="Currently active HTTP requests",
        unit="1",
    )


# ─── LogRecordFactory con request-id ─────────────────────────────────
_original_log_record_factory: Optional[Callable] = None


def install_request_id_log_factory() -> None:
    """Instala un LogRecordFactory que inyecta request_id en TODOS los logs.

    Funciona para structlog (app.*) y stdlib logging (tezcatlipoca.*) sin
    tocar cada punto de logging individualmente.
    """
    global _original_log_record_factory
    if _original_log_record_factory is not None:
        return  # Ya instalado

    _original_log_record_factory = logging.getLogRecordFactory()

    def _factory(*args, **kwargs):
        record = _original_log_record_factory(*args, **kwargs)
        try:
            record.request_id = request_id_ctx.get(None)  # type: ignore[attr-defined]
        except LookupError:
            record.request_id = None  # type: ignore[attr-defined]
        return record

    logging.setLogRecordFactory(_factory)
    logger.info("Request-ID LogRecordFactory installed")


# ─── Middleware ──────────────────────────────────────────────────────
class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware que:
    1. Lee/genera X-Request-ID (propagación end-to-end).
    2. Inyecta el id en el contexto async (visible para todo el request).
    3. Mide latencia y cuenta requests (Prometheus + OTel).
    4. Propaga el trace context de OTel en headers de salida.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Keep the existing correlation ID for logs/response, but never add it
        # to spans because callers control X-Request-ID.
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        token = request_id_ctx.set(request_id)

        try:
            # FastAPIInstrumentor is intentionally disabled for server spans.
            # Extract W3C context explicitly so our bounded span remains a child
            # of an upstream trace without recording URL, query, host or client IP.
            parent_context = propagate.extract(dict(request.headers))
            tracer = trace.get_tracer(__name__)
            method = _bounded_method_label(request.method)
            initial_route = _fallback_route_label(request.url.path)
            with tracer.start_as_current_span(
                f"{method} {initial_route}",
                context=parent_context,
                kind=trace.SpanKind.SERVER,
                attributes={
                    "http.method": method,
                    "http.route": initial_route,
                    "http.scheme": request.url.scheme,
                },
            ) as span:
                _init_otel_metrics()
                active_route = initial_route

                active_requests.labels(method=method, endpoint=active_route).inc()
                _otel_active_updown.add(1, {"method": method, "endpoint": active_route})

                start = time.perf_counter()
                try:
                    response = await call_next(request)
                    status = str(response.status_code)
                    span.set_attribute("http.status_code", response.status_code)
                    if response.status_code >= 400:
                        span.set_status(trace.Status(trace.StatusCode.ERROR))
                except Exception as exc:
                    status = "500"
                    # Exception messages and stack frames can contain request data
                    # or credentials; export the type, not the raw exception.
                    span.set_status(trace.Status(trace.StatusCode.ERROR))
                    span.set_attribute("error.type", type(exc).__name__)
                    raise
                finally:
                    duration = time.perf_counter() - start
                    route_label = _matched_route_label(request)
                    span.set_attribute("http.route", route_label)
                    span.update_name(f"{method} {route_label}")

                    # Prometheus
                    http_requests_total.labels(method=method, endpoint=route_label, status=status).inc()
                    http_request_duration_seconds.labels(method=method, endpoint=route_label).observe(duration)
                    active_requests.labels(method=method, endpoint=active_route).dec()

                    # OTel
                    _otel_request_counter.add(1, {"method": method, "endpoint": route_label, "status": status})
                    _otel_duration_histogram.record(duration, {"method": method, "endpoint": route_label})
                    _otel_active_updown.add(-1, {"method": method, "endpoint": active_route})

                # Propagate the request ID to logs/response only; it is not a span attribute.
                response.headers["X-Request-ID"] = request_id
                response.headers["traceparent"] = format_traceparent(span.get_span_context())

            return response
        finally:
            request_id_ctx.reset(token)


def format_traceparent(span_context) -> str:
    """Formatea un span context al header W3C traceparent."""
    trace_id = format(span_context.trace_id, "032x")
    span_id = format(span_context.span_id, "016x")
    flags = "01" if span_context.trace_flags.sampled else "00"
    return f"00-{trace_id}-{span_id}-{flags}"


# ─── Endpoint /metrics (FastAPI) ─────────────────────────────────────
async def metrics_endpoint(request: Request) -> Response:
    """Endpoint Prometheus-compatible. Scraping directo o vía OTel Collector."""
    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST,
    )
