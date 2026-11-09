"""Security regressions for Redis cache serialization."""
import pickle

import pytest

from app.core.cache import CacheService


DESERIALIZATION_CALLS = []


def mark_deserialization() -> None:
    DESERIALIZATION_CALLS.append("executed")


class PicklePayload:
    def __reduce__(self):
        return mark_deserialization, ()


class MemoryRedis:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def setex(self, key, ttl, value):
        self.values[key] = value


@pytest.mark.asyncio
async def test_json_safe_values_round_trip():
    redis = MemoryRedis()
    cache = CacheService(redis)
    value = {
        "folio": "OBRA-2026-001",
        "monto": "12345.670000",
        "activo": True,
        "partidas": [{"clave": "MAT-01", "cantidad": 4}],
    }

    assert await cache.set("expediente:1", value, ttl=120) is True
    assert await cache.get("expediente:1") == value
    assert isinstance(redis.values["expediente:1"], bytes)


@pytest.mark.asyncio
async def test_pickle_cache_payload_is_a_miss_without_executing_reduce():
    DESERIALIZATION_CALLS.clear()
    redis = MemoryRedis()
    redis.values["legacy:pickle"] = pickle.dumps(PicklePayload())
    cache = CacheService(redis)

    assert await cache.get("legacy:pickle") is None
    assert DESERIALIZATION_CALLS == []


@pytest.mark.asyncio
async def test_non_json_value_is_not_cached():
    redis = MemoryRedis()
    cache = CacheService(redis)

    assert await cache.set("unsupported", object()) is False
    assert "unsupported" not in redis.values
