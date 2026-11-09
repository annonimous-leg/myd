"""GET/POST quotas remain independent through the real Redis limiter."""
from uuid import uuid4

from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from app.core import rate_limit
from app.core.redis_client import RedisClient


@pytest.mark.asyncio
async def test_read_quota_does_not_consume_write_quota_and_both_limits_remain(monkeypatch):
    backend = RedisClient()
    assert await backend.connect(), 'A real Redis service is required for this regression'
    limiter = rate_limit.RateLimiter(backend)
    monkeypatch.setattr(rate_limit, 'get_rate_limiter', lambda: limiter)
    fixture = FastAPI()
    path = '/quota-regression/' + uuid4().hex
    async def respond():
        return {'ok': True}
    fixture.add_api_route(path, respond, methods=['GET'], dependencies=[Depends(rate_limit.rate_limit_standard)])
    fixture.add_api_route(path, respond, methods=['POST'], dependencies=[Depends(rate_limit.rate_limit_strict)])
    try:
        async with AsyncClient(transport=ASGITransport(app=fixture), base_url='http://test') as client:
            for _ in range(100):
                assert (await client.get(path)).status_code == 200
            for _ in range(10):
                assert (await client.post(path)).status_code == 200
            for method in (client.get, client.post):
                rejected = await method(path)
                assert rejected.status_code == 429
                assert rejected.headers['Retry-After'] == '60'
    finally:
        await backend.disconnect()


@pytest.mark.asyncio
async def test_dynamic_resource_ids_share_the_same_route_quota(monkeypatch):
    backend = RedisClient()
    assert await backend.connect(), 'A real Redis service is required for this regression'
    limiter = rate_limit.RateLimiter(backend)
    monkeypatch.setattr(rate_limit, 'get_rate_limiter', lambda: limiter)
    fixture = FastAPI()

    async def respond(item_id: str):
        return {'id': item_id}

    fixture.add_api_route(
        '/quota-by-route/{item_id}',
        respond,
        methods=['POST'],
        dependencies=[Depends(rate_limit.rate_limit_strict)],
    )
    try:
        async with AsyncClient(transport=ASGITransport(app=fixture), base_url='http://test') as client:
            for _ in range(10):
                response = await client.post(f'/quota-by-route/{uuid4()}')
                assert response.status_code == 200, response.text
            rejected = await client.post(f'/quota-by-route/{uuid4()}')
            assert rejected.status_code == 429
    finally:
        await backend.disconnect()
