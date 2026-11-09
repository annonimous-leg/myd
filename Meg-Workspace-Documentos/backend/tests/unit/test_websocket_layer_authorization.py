"""WebSocket layer authorization must fail closed."""
import pytest
from fastapi import WebSocketDisconnect

import app.api.v1.websocket as websocket_module
from app.api.v1.websocket import ConnectionManager, _TokenWS, _puede_suscribirse_capa


class DummyWebSocket:
    def __init__(self):
        self.accepted = False
        self.cookies = {}
        self.headers = {"origin": "http://localhost:5173"}
        self.messages = []
        self.closed = None

    async def accept(self):
        self.accepted = True

    async def send_json(self, message):
        self.messages.append(message)

    async def close(self, code=1000, reason=None):
        self.closed = (code, reason)


def test_websocket_origin_requires_exact_allowlist(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        websocket_module,
        "settings",
        SimpleNamespace(CORS_ALLOWED_ORIGINS=["https://app.example.mx"]),
    )

    assert websocket_module._origin_websocket_permitido("https://app.example.mx")
    assert not websocket_module._origin_websocket_permitido("https://app.example.mx.evil.test")
    assert not websocket_module._origin_websocket_permitido("https://evil.example")
    assert not websocket_module._origin_websocket_permitido(None)
    assert not websocket_module._origin_websocket_permitido("")


@pytest.mark.asyncio
async def test_progress_websocket_rejects_untrusted_origin_before_auth(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        websocket_module,
        "settings",
        SimpleNamespace(CORS_ALLOWED_ORIGINS=["https://app.example.mx"]),
    )

    async def validation_must_not_run(_token):
        pytest.fail("Origin rejection must happen before authentication")

    monkeypatch.setattr(websocket_module, "_validar_token_ws", validation_must_not_run)
    socket = DummyWebSocket()
    socket.headers = {"origin": "https://attacker.example"}

    await websocket_module.websocket_progreso(socket)

    assert socket.accepted is False
    assert socket.closed == (1008, "Origin no permitido")


@pytest.mark.asyncio
async def test_notifications_websocket_rejects_missing_origin_before_auth(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        websocket_module,
        "settings",
        SimpleNamespace(CORS_ALLOWED_ORIGINS=["https://app.example.mx"]),
    )

    async def validation_must_not_run(_token):
        pytest.fail("Origin rejection must happen before authentication")

    monkeypatch.setattr(websocket_module, "_validar_token_ws", validation_must_not_run)
    socket = DummyWebSocket()
    socket.headers = {}

    await websocket_module.websocket_notificaciones(socket)

    assert socket.accepted is False
    assert socket.closed == (1008, "Origin no permitido")


def test_websocket_endpoints_do_not_accept_query_token_parameters():
    import inspect

    assert "token" not in inspect.signature(websocket_module.websocket_progreso).parameters
    assert "token" not in inspect.signature(websocket_module.websocket_notificaciones).parameters


def test_layer_roles_match_expected_read_tiers():
    assert _puede_suscribirse_capa(_TokenWS("1", "t", "superadmin"))
    assert _puede_suscribirse_capa(_TokenWS("1", "t", "admin"))
    assert _puede_suscribirse_capa(_TokenWS("1", "t", "tecnico"))
    assert not _puede_suscribirse_capa(_TokenWS("1", "t", "revisor"))
    assert not _puede_suscribirse_capa(_TokenWS("1", "t", "lector"))
    assert not _puede_suscribirse_capa(_TokenWS("1", "t", "invitado"))


@pytest.mark.asyncio
async def test_filtered_broadcast_never_falls_back_to_all_connections():
    manager = ConnectionManager()
    unrestricted = DummyWebSocket()
    subscribed = DummyWebSocket()

    await manager.connect(unrestricted, "u1")
    await manager.connect(subscribed, "u2")

    await manager.broadcast({"type": "layer-update", "n": 0}, set())
    await manager.broadcast({"type": "layer-update"}, {"flights"})
    assert unrestricted.messages == []
    assert subscribed.messages == []

    manager.subscribe_to_layer(subscribed, "flights")
    await manager.broadcast({"type": "layer-update", "n": 2}, {"flights"})
    assert unrestricted.messages == []
    assert subscribed.messages == [{"type": "layer-update", "n": 2}]


@pytest.mark.asyncio
async def test_reviewer_cannot_subscribe_through_websocket_endpoint(monkeypatch):
    auth = _TokenWS("u1", "tenant-a", "revisor")
    manager = ConnectionManager()
    monkeypatch.setattr(websocket_module, "manager", manager)

    async def validate_token(_token):
        return auth

    incoming = iter([
        {"action": "subscribe_layer", "layer": "flights"},
        WebSocketDisconnect(code=1000),
    ])

    async def receive_authenticated(_websocket, _token, _auth):
        item = next(incoming)
        if isinstance(item, BaseException):
            raise item
        return item

    monkeypatch.setattr(websocket_module, "_validar_token_ws", validate_token)
    monkeypatch.setattr(websocket_module, "_receive_authenticated", receive_authenticated)

    socket = DummyWebSocket()
    await websocket_module.websocket_progreso(socket)

    assert socket.accepted is True
    assert socket.messages == [{
        "type": "error",
        "error": "forbidden_layer_subscription",
        "layer": "flights",
    }]
    assert "flights" not in manager.layer_connections


@pytest.mark.asyncio
async def test_none_layer_filter_preserves_intentional_global_broadcast():
    manager = ConnectionManager()
    connected = DummyWebSocket()
    await manager.connect(connected, "u1")

    await manager.broadcast({"type": "general-event"}, None)

    assert connected.messages == [{"type": "general-event"}]
