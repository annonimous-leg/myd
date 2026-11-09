"""Redis client for caching, rate limiting, and token blacklist.

Provides:
- Token blacklist with TTL (auto-expires when JWT expires)
- Distributed rate limiting
- Response caching for expensive API calls
- WebSocket pub/sub for multi-instance deployments
"""

import os
import json
from typing import Optional, Any
from datetime import datetime, timezone

from fastapi import HTTPException

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def _redis_failure_policy() -> str:
    return os.getenv("REDIS_FAILURE_POLICY", "fail_open").strip().lower()

class RedisClient:
    """Async Redis client wrapper."""

    def __init__(self):
        self._client: Optional[Any] = None
        self._available = REDIS_AVAILABLE

    async def connect(self):
        """Connect to Redis."""
        if not self._available:
            return False
        try:
            self._client = redis.from_url(REDIS_URL, decode_responses=True)
            await self._client.ping()
            return True
        except Exception as e:
            print(f"[Redis] Connection failed: {e}")
            self._client = None
            return False

    async def disconnect(self):
        """Disconnect from Redis."""
        if self._client:
            await self._client.aclose()
            self._client = None

    # ─── Token Blacklist ───

    async def blacklist_token(self, jti: str, expires_at: datetime) -> bool:
        """Add a token JTI to the blacklist with TTL."""
        if not self._client:
            return False
        try:
            ttl = int((expires_at - datetime.now(timezone.utc)).total_seconds())
            if ttl > 0:
                await self._client.setex(f"blacklist:{jti}", ttl, "1")
            return True
        except Exception:
            return False

    async def is_token_blacklisted(self, jti: str) -> bool:
        """Check if a token JTI is blacklisted."""
        if not self._client:
            return False
        try:
            return await self._client.exists(f"blacklist:{jti}") > 0
        except Exception:
            return False

    # ─── Rate Limiting ───

    async def check_rate_limit(self, key: str, max_requests: int, window_seconds: int) -> tuple[bool, int]:
        """Check if rate limit is exceeded. Returns (allowed, remaining)."""
        if not self._client:
            if _redis_failure_policy() == "fail_closed":
                raise HTTPException(status_code=503, detail="Redis no disponible: rate limiter en fail-closed")
            return True, max_requests

        try:
            pipe = self._client.pipeline()
            now = datetime.now(timezone.utc).timestamp()
            window_start = now - window_seconds

            # Remove old entries
            pipe.zremrangebyscore(f"ratelimit:{key}", 0, window_start)
            # Count current entries
            pipe.zcard(f"ratelimit:{key}")
            # Add current request
            pipe.zadd(f"ratelimit:{key}", {str(now): now})
            # Set expiry on the key
            pipe.expire(f"ratelimit:{key}", window_seconds)

            results = await pipe.execute()
            current_count = results[1]

            allowed = current_count < max_requests
            remaining = max(0, max_requests - current_count - 1)

            return allowed, remaining
        except Exception:
            if _redis_failure_policy() == "fail_closed":
                raise HTTPException(status_code=503, detail="Redis no disponible: rate limiter en fail-closed")
            return True, max_requests

    # ─── Response Caching ───

    async def cache_response(self, key: str, data: Any, ttl_seconds: int = 300) -> bool:
        """Cache an API response."""
        if not self._client:
            return False
        try:
            await self._client.setex(f"cache:{key}", ttl_seconds, json.dumps(data))
            return True
        except Exception:
            return False

    async def get_cached_response(self, key: str) -> Optional[Any]:
        """Get a cached API response."""
        if not self._client:
            return None
        try:
            cached = await self._client.get(f"cache:{key}")
            return json.loads(cached) if cached else None
        except Exception:
            return None

    # ─── WebSocket Pub/Sub (multi-instance) ───

    async def publish(self, channel: str, message: dict) -> bool:
        """Publish a message to a channel."""
        if not self._client:
            return False
        try:
            await self._client.publish(channel, json.dumps(message))
            return True
        except Exception:
            return False

    async def subscribe(self, channel: str):
        """Subscribe to a channel. Returns pubsub object."""
        if not self._client:
            return None
        try:
            pubsub = self._client.pubsub()
            await pubsub.subscribe(channel)
            return pubsub
        except Exception:
            return None

# Global instance
redis_client = RedisClient()
