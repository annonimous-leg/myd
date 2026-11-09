# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Cache con Redis para servicios de búsqueda y catálogos.

Solo se admiten valores JSON. No se debe deserializar con pickle contenido
leído del backend de caché: un valor alterado podría ejecutar código.
"""
import json
from typing import Optional, Any


class CacheService:
    """Servicio de caché Redis con serialización JSON segura."""

    def __init__(self, redis_client=None):
        self.redis = redis_client
        self.enabled = redis_client is not None

    async def get(self, key: str) -> Optional[Any]:
        """Obtiene valor JSON de caché; un dato inválido se trata como miss."""
        if not self.enabled:
            return None
        data = await self.redis.get(key)
        if data is None:
            return None
        try:
            return json.loads(data)
        except (TypeError, ValueError, UnicodeDecodeError):
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int = 300,  # 5 minutos default
    ) -> bool:
        """Guarda valores JSON; los objetos no compatibles no se cachean."""
        if not self.enabled:
            return False
        try:
            serialized = json.dumps(
                value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
            await self.redis.setex(key, ttl, serialized)
            return True
        except (TypeError, ValueError):
            return False
        except Exception:
            return False

    async def delete(self, key: str) -> bool:
        """Elimina una clave de caché."""
        if not self.enabled:
            return False
        await self.redis.delete(key)
        return True

    async def delete_pattern(self, pattern: str) -> int:
        """Elimina las claves que coinciden con un patrón."""
        if not self.enabled:
            return 0
        keys = []
        async for key in self.redis.scan_iter(match=pattern):
            keys.append(key)
        if keys:
            await self.redis.delete(*keys)
        return len(keys)

    def key(self, prefix: str, *parts) -> str:
        """Genera una clave de caché."""
        parts_str = ":".join(str(p) for p in parts)
        return f"meg:{prefix}:{parts_str}"


cache_service: Optional[CacheService] = None


def get_cache() -> CacheService:
    global cache_service
    if cache_service is None:
        cache_service = CacheService()
    return cache_service
