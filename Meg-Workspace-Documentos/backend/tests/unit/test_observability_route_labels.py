"""Metric route labels must not expose attacker-controlled cardinality."""
from types import SimpleNamespace

from app.core.observability import (
    _bounded_method_label,
    _fallback_route_label,
    _matched_route_label,
)


def test_unmatched_metric_route_collapses_arbitrary_values():
    assert _fallback_route_label("/api/v1/bim/6ba7b810-9dad-41d1-80b4-00c04fd430c8/modelos/42") == "/__unmatched__"
    assert _fallback_route_label("/users/alice-secret-token-991/file-name.pdf") == "/__unmatched__"
    assert _fallback_route_label("/api/v1/auth/me") == "/__unmatched__"


def test_registered_http_methods_are_preserved():
    for method in ("GET", "POST", "PATCH", "DELETE", "OPTIONS"):
        assert _bounded_method_label(method) == method


def test_nonstandard_http_methods_collapse_to_other():
    for method in ("MADEUP", "X-ATTACKER-1", "ANOTHER_CUSTOM_METHOD"):
        assert _bounded_method_label(method) == "OTHER"


def test_matched_route_uses_registered_template_not_request_path():
    request = SimpleNamespace(
        scope={"route": SimpleNamespace(path="/api/v1/documents/{document_id}")},
        url=SimpleNamespace(path="/api/v1/documents/private-document-123"),
    )
    assert _matched_route_label(request) == "/api/v1/documents/{document_id}"


def test_missing_route_uses_bounded_fallback():
    request = SimpleNamespace(
        scope={},
        url=SimpleNamespace(path="/arbitrary/user-controlled/path"),
    )
    assert _matched_route_label(request) == "/__unmatched__"
