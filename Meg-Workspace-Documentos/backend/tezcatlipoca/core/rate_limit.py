"""Rate limiting con Redis + sliding window para Tezcatlipoca.

BUG ORIGINAL (tarea C): existían DOS rate limiters caseros en memoria
por separado:
1. `tezcatlipoca/middleware/rate_limit.py` -- middleware global con un
   dict de proceso. No se usa en el entrypoint real (app/main.py monta
   los routers de tezcatlipoca directamente, nunca ejecuta
   tezcatlipoca/main.py ni su add_middleware), así que hoy es código
   muerto -- pero queda ahí, se ve como si protegiera algo, y no
   protege nada en el deploy real. Además, si alguna vez se corre
   tezcatlipoca/main.py standalone, ese dict no funciona bien con más
   de un worker (cada proceso tiene el suyo) y tiene fuga de memoria
   (nunca evictea entradas de clientes que no vuelven).
2. `geo_threats.py` tenía SU PROPIO `_check_rate_limit` con el mismo
   patrón (dict de proceso, mismos problemas), sin relación con el de
   arriba -- dos implementaciones duplicadas e inconsistentes.

AHORA: un solo mecanismo, respaldado por Redis (mismo sliding window
por sorted set que ya usa app/core/rate_limit.py en el backend
principal), reusando el RedisClient que YA existía en
tezcatlipoca/services/redis_client.py pero que nadie llamaba desde
ningún router. Se mantiene como módulo separado de
app/core/rate_limit.py (no se importa cruzado) a propósito: el propio
código de integración (ver app/main.py, comentario en la sección
"INTEGRACIÓN ZIP 4") deja explícito que la unificación de tezcatlipoca
con el resto de Megalodon es una decisión de producto pendiente, no
algo para resolver de facto compartiendo módulos internos. Rate
limiting es infraestructura pura (no toca modelo de datos/tenant), así
que replicar el patrón -- sin fusionar los módulos -- es la opción que
no prejuzga esa decisión pendiente.

Conexión perezosa (`_ensure_connected`): no depende de que el
`@router.on_event("startup")` de tezcatlipoca/routers/auth.py se
dispare en el proceso mergeado (FastAPI/Starlette no garantiza que los
on_event de un router incluido se ejecuten si el app padre define su
propio `lifespan=...` explícito, que es justo el caso de app/main.py;
no se pudo levantar un server real en este sandbox para confirmarlo
empíricamente, así que se optó por no depender de ese mecanismo en
absoluto). Cada llamada verifica la conexión y reconecta si hace falta.
"""
from __future__ import annotations

from fastapi import HTTPException, Request

from services.redis_client import redis_client

_connect_lock_owner = None


async def _ensure_connected() -> None:
    """Conecta el cliente Redis si todavía no lo está. Idempotente y
    segura de llamar en cada request: si ya hay conexión, no hace nada."""
    if redis_client._client is None:
        await redis_client.connect()


def _client_id(request: Request) -> str:
    """IP real del cliente, respetando X-Forwarded-For si hay proxy
    delante (mismo criterio que ya usaba el middleware que se retira)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _check(request: Request, max_requests: int, window_seconds: int) -> None:
    await _ensure_connected()
    key = f"{_client_id(request)}:{request.url.path}"
    allowed, remaining = await redis_client.check_rate_limit(key, max_requests, window_seconds)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Max {max_requests} requests per {window_seconds}s",
            headers={"Retry-After": str(window_seconds)},
        )


async def rate_limit_standard(request: Request) -> None:
    """100 requests / 60s por IP+endpoint. Igual que app/core/rate_limit.py."""
    await _check(request, max_requests=100, window_seconds=60)


async def rate_limit_strict(request: Request) -> None:
    """10 requests / 60s por IP+endpoint -- para endpoints de mayor
    costo/sensibilidad (igual que app/core/rate_limit.py)."""
    await _check(request, max_requests=10, window_seconds=60)
