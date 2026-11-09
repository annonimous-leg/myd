# Copyright © 2026 Cristian Rodriguez
# All rights reserved.

"""
Tracing distribuido con OpenTelemetry — producción industrial.

Este módulo configura el SDK de OpenTelemetry para exportar traces, métricas
y logs al OTel Collector. No hay vendor lock-in: el backend (Tempo, Jaeger,
SaaS) se decide en la infraestructura, no en el código.

Uso:
    from app.core.tracing import init_telemetry, shutdown_telemetry
    init_telemetry()
    # ... aplicación corre ...
    shutdown_telemetry()
"""

import os
import logging
from typing import Optional

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION, DEPLOYMENT_ENVIRONMENT
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

try:  # Optional runtime instrumentation packages may not be installed in test images.
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor
    from opentelemetry.instrumentation.celery import CeleryInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
except ModuleNotFoundError:  # pragma: no cover - exercised in lean CI images
    SQLAlchemyInstrumentor = None  # type: ignore[assignment]
    RedisInstrumentor = None  # type: ignore[assignment]
    CeleryInstrumentor = None  # type: ignore[assignment]
    HTTPXClientInstrumentor = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Resource compartido — identifica este servicio en TODOS los signals (traces, metrics, logs)
_RESOURCE: Optional[Resource] = None
_TRACER_PROVIDER: Optional[TracerProvider] = None
_METER_PROVIDER: Optional[metrics.MeterProvider] = None

# HTTP client instrumentation records URL/host/address attributes by default.
# Replace those values after each span is created, before it is exported.
_REDACTED_HTTP_SPAN_ATTRIBUTES = (
    "http.url",
    "url.full",
    "url.path",
    "url.query",
    "http.target",
    "http.host",
    "server.address",
    "client.address",
    "network.peer.address",
    "net.peer.name",
    "net.peer.ip",
    "http.client_ip",
)
_SENSITIVE_HEADER_PATTERN = (
    r".*(authorization|cookie|token|secret|api[_-]?key|password|session|credential).*"
)


def _redact_http_span(span) -> None:
    """Remove request-target and peer-identifying values from HTTP client spans."""
    if span is None or not span.is_recording():
        return
    for attribute in _REDACTED_HTTP_SPAN_ATTRIBUTES:
        span.set_attribute(attribute, "[REDACTED]")


def _sanitize_httpx_request_span(span, _request_info) -> None:
    _redact_http_span(span)


def _sanitize_httpx_response_span(span, _request_info, _response_info) -> None:
    _redact_http_span(span)


async def _sanitize_httpx_request_span_async(span, _request_info) -> None:
    _redact_http_span(span)


async def _sanitize_httpx_response_span_async(span, _request_info, _response_info) -> None:
    _redact_http_span(span)


def _ensure_sensitive_header_sanitization() -> None:
    """Preserve caller configuration and always redact common secret-bearing headers."""
    variable = "OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS"
    existing = [value.strip() for value in os.environ.get(variable, "").split(",") if value.strip()]
    if _SENSITIVE_HEADER_PATTERN not in existing:
        existing.append(_SENSITIVE_HEADER_PATTERN)
        os.environ[variable] = ",".join(existing)



def _build_resource() -> Resource:
    """Construye el recurso OTel con atributos estáticos del servicio."""
    global _RESOURCE
    if _RESOURCE is not None:
        return _RESOURCE

    _RESOURCE = Resource.create({
        SERVICE_NAME: os.getenv("OTEL_SERVICE_NAME", "megalodon-api"),
        SERVICE_VERSION: os.getenv("OTEL_SERVICE_VERSION", "4.0.0"),
        DEPLOYMENT_ENVIRONMENT: os.getenv("ENVIRONMENT", "production"),
        "service.namespace": "megalodon",
        "service.instance.id": os.getenv("HOSTNAME", "unknown"),
        "host.name": os.getenv("HOSTNAME", "unknown"),
    })
    return _RESOURCE


def init_telemetry(
    app=None,
    sqlalchemy_engine=None,
    celery_app=None,
    otlp_endpoint: Optional[str] = None,
) -> None:
    """Inicializa tracing, métricas e instrumentación automática.

    Args:
        app: FastAPI app; server spans are emitted by RequestContextMiddleware.
        sqlalchemy_engine: Engine SQLAlchemy (sync o async) para instrumentar queries.
        celery_app: App Celery para instrumentar tasks.
        otlp_endpoint: Override del endpoint OTLP. Default: OTEL_EXPORTER_OTLP_ENDPOINT env.
    """
    global _TRACER_PROVIDER, _METER_PROVIDER

    endpoint = otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
    insecure = os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() == "true"

    resource = _build_resource()

    # ─── Traces ──────────────────────────────────────────────────────
    _TRACER_PROVIDER = TracerProvider(resource=resource)
    trace.set_tracer_provider(_TRACER_PROVIDER)

    span_exporter = OTLPSpanExporter(
        endpoint=endpoint,
        insecure=insecure,
        timeout=30,
    )
    span_processor = BatchSpanProcessor(
        span_exporter,
        max_queue_size=2048,
        max_export_batch_size=512,
        schedule_delay_millis=5000,
    )
    _TRACER_PROVIDER.add_span_processor(span_processor)

    # ─── Metrics ─────────────────────────────────────────────────────
    metric_exporter = OTLPMetricExporter(
        endpoint=endpoint,
        insecure=insecure,
        timeout=30,
    )
    metric_reader = PeriodicExportingMetricReader(
        metric_exporter,
        export_interval_millis=60000,
    )
    _METER_PROVIDER = MeterProvider(
        resource=resource,
        metric_readers=[metric_reader],
    )
    metrics.set_meter_provider(_METER_PROVIDER)

    # Server spans are emitted by RequestContextMiddleware. Avoid the default
    # FastAPI server spans because they independently capture raw URL/path/peer
    # attributes and duplicate the privacy-filtered span from that middleware.
    if app is not None:
        logger.info("FastAPI request spans use privacy-filtered RequestContextMiddleware")

    if sqlalchemy_engine is not None and SQLAlchemyInstrumentor is not None:
        SQLAlchemyInstrumentor().instrument(
            engine=sqlalchemy_engine,
        )
        logger.info("SQLAlchemy instrumented with OpenTelemetry")
    elif sqlalchemy_engine is not None:
        logger.warning("SQLAlchemy instrumentation unavailable: package not installed")

    if RedisInstrumentor is not None:
        RedisInstrumentor().instrument()
        logger.info("Redis instrumented with OpenTelemetry")
    else:
        logger.warning("Redis instrumentation unavailable: package not installed")

    if celery_app is not None and CeleryInstrumentor is not None:
        CeleryInstrumentor().instrument()
        logger.info("Celery instrumented with OpenTelemetry")
    elif celery_app is not None:
        logger.warning("Celery instrumentation unavailable: package not installed")

    if HTTPXClientInstrumentor is not None:
        _ensure_sensitive_header_sanitization()
        HTTPXClientInstrumentor().instrument(
            request_hook=_sanitize_httpx_request_span,
            response_hook=_sanitize_httpx_response_span,
            async_request_hook=_sanitize_httpx_request_span_async,
            async_response_hook=_sanitize_httpx_response_span_async,
        )
        logger.info("HTTPX instrumented with URL and peer-attribute redaction")
    else:
        logger.warning("HTTPX instrumentation unavailable: package not installed")

    logger.info(f"Telemetry initialized — OTLP endpoint: {endpoint}")


def shutdown_telemetry() -> None:
    """Flush y cierre ordenado de exporters. Llámalo en lifespan shutdown."""
    global _TRACER_PROVIDER, _METER_PROVIDER

    if _TRACER_PROVIDER is not None:
        _TRACER_PROVIDER.shutdown()
        logger.info("TracerProvider shutdown complete")

    if _METER_PROVIDER is not None:
        _METER_PROVIDER.shutdown()
        logger.info("MeterProvider shutdown complete")


def get_tracer(name: str = __name__):
    """Obtiene un tracer para crear spans manuales en servicios de dominio."""
    return trace.get_tracer(name)


def get_meter(name: str = __name__):
    """Obtiene un meter para crear métricas custom en servicios de dominio."""
    return metrics.get_meter(name)
