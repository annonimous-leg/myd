"""Connection ownership test using the installed Supabase/HTTPX clients, no network."""
import asyncio
import os
from app.integrations.supabase_storage import get_storage_client, worker_storage_scope
from app.config import settings


def test_worker_storage_connections_are_closed_and_not_reused_across_loops(monkeypatch):
    # Connection ownership uses no network and must not depend on the runner proxy.
    for name in os.environ:
        if name.lower().endswith("_proxy"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "test-key-not-a-secret")
    clients = []
    async def task():
        async with worker_storage_scope():
            client = await get_storage_client()
            assert await get_storage_client() is client
            assert not client.options.httpx_client.is_closed
            clients.append(client)
        assert client.options.httpx_client.is_closed
    asyncio.run(task())
    asyncio.run(task())
    assert clients[0] is not clients[1]
