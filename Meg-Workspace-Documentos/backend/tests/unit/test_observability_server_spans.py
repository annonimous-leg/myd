"""Privacy and propagation invariants for HTTP telemetry."""
import os
from types import SimpleNamespace

import pytest
from starlette.requests import Request
from starlette.responses import Response

import app.core.observability as observability
from app.core.tracing import _ensure_sensitive_header_sanitization, _redact_http_span

_REDACTED = "[REDACTED]"
_SENSITIVE_ATTRIBUTES = (
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


class FakeMetricChild:
    def inc(self, *_args, **_kwargs):
        pass

    def dec(self, *_args, **_kwargs):
        pass

    def observe(self, *_args, **_kwargs):
        pass


class FakeMetricVector:
    def labels(self, **_kwargs):
        return FakeMetricChild()


class FakeOtelMetric:
    def add(self, *_args, **_kwargs):
        pass

    def record(self, *_args, **_kwargs):
        pass


class FakeSpan:
    def __init__(self, name, attributes=None):
        self.name = name
        self.attributes = dict(attributes or {})
        self.status = None
        self.exceptions = []
        self.span_context = SimpleNamespace(
            trace_id=1,
            span_id=2,
            trace_flags=SimpleNamespace(sampled=True),
        )

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def is_recording(self):
        return True

    def set_attribute(self, key, value):
        self.attributes[key] = value

    def set_status(self, status):
        self.status = status

    def record_exception(self, exception):
        self.exceptions.append(exception)

    def update_name(self, name):
        self.name = name

    def get_span_context(self):
        return self.span_context


class FakeTracer:
    def __init__(self):
        self.name = None
        self.kwargs = None
        self.span = None

    def start_as_current_span(self, name, **kwargs):
        self.name = name
        self.kwargs = kwargs
        self.span = FakeSpan(name, kwargs.get("attributes"))
        return self.span


def _request(path="/api/v1/expedientes/tenant-secret-expediente"):
    return Request({
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"access_token=query-secret",
        "headers": [
            (b"host", b"internal-api.example.invalid"),
            (b"x-request-id", b"caller-secret-token-123"),
            (b"traceparent", b"00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"),
        ],
        "client": ("203.0.113.10", 51432),
        "server": ("internal-api.example.invalid", 443),
    })


def _patch_metrics(monkeypatch):
    monkeypatch.setattr(observability, "_init_otel_metrics", lambda: None)
    monkeypatch.setattr(observability, "active_requests", FakeMetricVector())
    monkeypatch.setattr(observability, "http_requests_total", FakeMetricVector())
    monkeypatch.setattr(observability, "http_request_duration_seconds", FakeMetricVector())
    monkeypatch.setattr(observability, "_otel_active_updown", FakeOtelMetric())
    monkeypatch.setattr(observability, "_otel_request_counter", FakeOtelMetric())
    monkeypatch.setattr(observability, "_otel_duration_histogram", FakeOtelMetric())


def test_httpx_span_replaces_url_and_peer_identifiers():
    secret = "https://private.example.invalid/users/alice?token=must-not-export"
    span = FakeSpan("GET", {attribute: secret for attribute in _SENSITIVE_ATTRIBUTES})

    _redact_http_span(span)

    for attribute in _SENSITIVE_ATTRIBUTES:
        assert span.attributes[attribute] == _REDACTED
    assert "alice" not in repr(span.attributes)
    assert "must-not-export" not in repr(span.attributes)


def test_sensitive_header_redaction_preserves_existing_configuration(monkeypatch):
    monkeypatch.setenv("OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS", "x-existing-header")

    _ensure_sensitive_header_sanitization()

    patterns = os.environ["OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS"].split(",")
    assert "x-existing-header" in patterns
    assert any("authorization" in pattern and "token" in pattern for pattern in patterns)


@pytest.mark.asyncio
async def test_server_span_is_bounded_extracts_parent_and_restores_request_context(monkeypatch):
    _patch_metrics(monkeypatch)
    parent_context = object()
    extracted = {}

    def extract(carrier):
        extracted.update(carrier)
        return parent_context

    monkeypatch.setattr(observability.propagate, "extract", extract)
    tracer = FakeTracer()
    monkeypatch.setattr(observability.trace, "get_tracer", lambda *_args, **_kwargs: tracer)

    existing_token = observability.request_id_ctx.set("outer-request")
    try:
        request = _request()
        middleware = observability.RequestContextMiddleware(lambda *_args: None)

        async def call_next(current_request):
            current_request.scope["route"] = SimpleNamespace(path="/api/v1/expedientes/{expediente_id}")
            return Response("ok", status_code=200)

        response = await middleware.dispatch(request, call_next)

        assert tracer.kwargs["context"] is parent_context
        assert extracted["traceparent"].startswith("00-")
        assert tracer.span.name == "GET /api/v1/expedientes/{expediente_id}"
        assert tracer.span.attributes["http.route"] == "/api/v1/expedientes/{expediente_id}"
        assert "http.request_id" not in tracer.span.attributes
        assert not any(attribute in tracer.span.attributes for attribute in _SENSITIVE_ATTRIBUTES)
        assert "tenant-secret-expediente" not in tracer.span.name
        assert "query-secret" not in repr(tracer.span.attributes)
        assert response.headers["X-Request-ID"] == "caller-secret-token-123"
        assert observability.request_id_ctx.get() == "outer-request"
    finally:
        observability.request_id_ctx.reset(existing_token)


@pytest.mark.asyncio
async def test_server_span_does_not_record_exception_details_and_restores_context(monkeypatch):
    _patch_metrics(monkeypatch)
    tracer = FakeTracer()
    monkeypatch.setattr(observability.trace, "get_tracer", lambda *_args, **_kwargs: tracer)
    parent_context = object()
    monkeypatch.setattr(observability.propagate, "extract", lambda _carrier: parent_context)

    existing_token = observability.request_id_ctx.set("outer-error-request")
    try:
        with pytest.raises(RuntimeError, match="not forwarded"):
            await observability.RequestContextMiddleware(lambda *_args: None).dispatch(
                _request(),
                _raise_sensitive_error,
            )

        assert tracer.span.attributes["error.type"] == "RuntimeError"
        assert not tracer.span.exceptions
        assert "secret-value-991" not in repr(tracer.span.attributes)
        assert tracer.span.status.description is None
        assert observability.request_id_ctx.get() == "outer-error-request"
    finally:
        observability.request_id_ctx.reset(existing_token)


async def _raise_sensitive_error(_request):
    raise RuntimeError("request failed; details not forwarded; token=secret-value-991")
