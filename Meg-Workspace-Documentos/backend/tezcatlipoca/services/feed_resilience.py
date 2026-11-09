"""Feed Resilience — caché persistente en disco + reintentos acotados
para conectores de fuentes externas (threat intel, clima, etc).

Problema real que resuelve (encontrado auditando malware/aggregator.py,
malware/feodo_tracker.py, malware/urlhaus.py, malware/cisa_kev.py y
weather/open_meteo.py): todos cacheaban únicamente en memoria del
proceso (`self.cache = {}` / `self._cache = None`). Si el proceso
reinicia (deploy, crash, autoscaling) justo cuando la fuente externa
está caída, el conector arranca sin ningún dato -- y el patrón
`except Exception: return []` hace que "la fuente está caída" y "no
hay amenazas" sean indistinguibles para quien consume el dato. Para
una plataforma de inteligencia de amenazas eso es peligroso: un
`total_threats: 0` silencioso puede significar "todo limpio" o puede
significar "el feed lleva 6 horas sin poder actualizarse".

Este módulo NO reemplaza el caché en memoria de cada conector (que
sigue siendo la ruta rápida de TTL corto). Es la red de seguridad de
segundo nivel: cuando la memoria está fría (proceso recién iniciado) Y
la fuente externa no responde, se sirve el último dato bueno conocido
desde disco, marcado explícitamente como `stale_cache`, en vez de un
vacío ambiguo marcado como si fuera `live`.

No depende de FastAPI/SQLAlchemy/aiohttp -- sólo librería estándar --
para poder usarse desde cualquier conector sin arrastrar el stack
completo del backend.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, TypeVar

T = TypeVar("T")

STATUS_LIVE = "live"
STATUS_STALE_CACHE = "stale_cache"
STATUS_UNAVAILABLE = "unavailable"


@dataclass
class FeedResult:
    """Resultado de intentar obtener datos de una fuente externa.

    `status`:
      - "live": el fetch de red tuvo éxito ahora mismo.
      - "stale_cache": el fetch falló, pero hay un respaldo en disco
        (puede tener horas/días) y se sirvió ese.
      - "unavailable": el fetch falló y no existe ningún respaldo en
        disco (primera vez que se corre esta fuente, o nunca tuvo
        éxito). `data` queda en el valor `empty` provisto por el
        llamador (típicamente [] o {}), pero AHORA es explícito que
        significa "no se pudo obtener", no "se consultó y está vacío".
    """
    data: Any
    status: str
    source: str
    fetched_at: Optional[str]
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "data": self.data,
            "status": self.status,
            "source": self.source,
            "fetched_at": self.fetched_at,
            "error": self.error,
        }


class PersistentFeedCache:
    """Último resultado bueno de cada fuente, persistido en disco (JSON).

    Escritura atómica (archivo temporal + rename) para que un proceso
    que muere a la mitad de una escritura no deje un JSON corrupto por
    la mitad -- `os.replace` es atómico dentro del mismo filesystem.
    """

    def __init__(self, data_dir: Optional[str] = None):
        base = data_dir or os.getenv("TEZCATLIPOCA_FEED_CACHE_DIR", "./data/feed_cache")
        self.data_dir = Path(base)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, source: str) -> Path:
        safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in source)
        return self.data_dir / f"{safe}.json"

    def save(self, source: str, data: Any) -> None:
        path = self._path(source)
        payload = {
            "source": source,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.data_dir), prefix=f".{path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, default=str)
            os.replace(tmp_path, path)
        except Exception:
            # Guardar el respaldo es un extra, no el camino principal.
            # Si falla (disco lleno, permisos), no debe tumbar el fetch
            # que sí tuvo éxito -- se descarta el intento de respaldo.
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def load(self, source: str) -> Optional[dict]:
        path = self._path(source)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            # Respaldo corrupto == no hay respaldo utilizable. No se
            # propaga: este caché es una red de seguridad, nunca debe
            # poder romper el flujo principal.
            return None


def resolve_result(
    *,
    source: str,
    live_data: Any,
    live_ok: bool,
    error: Optional[str],
    cache: PersistentFeedCache,
    empty: Any,
) -> FeedResult:
    """Decide status final y actualiza/lee el respaldo en disco.

    Si el fetch en vivo funcionó: guarda el respaldo y devuelve "live".
    Si falló: intenta leer el último respaldo bueno; si existe, "stale_cache"
    con ese dato; si no existe ningún respaldo previo, "unavailable" con
    `empty`.
    """
    if live_ok:
        cache.save(source, live_data)
        return FeedResult(
            data=live_data, status=STATUS_LIVE, source=source,
            fetched_at=datetime.now(timezone.utc).isoformat(), error=None,
        )

    backup = cache.load(source)
    if backup is not None:
        return FeedResult(
            data=backup.get("data", empty), status=STATUS_STALE_CACHE,
            source=source, fetched_at=backup.get("fetched_at"), error=error,
        )

    return FeedResult(
        data=empty, status=STATUS_UNAVAILABLE, source=source,
        fetched_at=None, error=error,
    )


async def fetch_with_retries(
    fetch_fn: Callable[[], Awaitable[T]],
    *,
    retries: int = 2,
    base_delay: float = 1.0,
    logger=None,
    source: str = "",
) -> tuple[Optional[T], Optional[str]]:
    """Reintenta una corrutina de fetch con backoff exponencial simple.

    Devuelve (resultado, None) si tuvo éxito, o (None, mensaje_error) si
    se agotaron los intentos. No lanza -- el llamador decide qué hacer
    (típicamente: pasarlo a `resolve_result` para caer al respaldo).
    """
    last_error: Optional[str] = None
    for attempt in range(1, retries + 1):
        try:
            result = await fetch_fn()
            return result, None
        except Exception as exc:  # noqa: BLE001 - frontera con red externa
            last_error = f"{type(exc).__name__}: {exc}"
            if logger is not None:
                logger.warning(
                    "feed_fetch_attempt_failed",
                    source=source, attempt=attempt, retries=retries,
                    error=last_error,
                )
            if attempt < retries:
                await asyncio.sleep(base_delay * (2 ** (attempt - 1)))
    return None, last_error


def sync_fetch_with_retries(
    fetch_fn: Callable[[], T],
    *,
    retries: int = 2,
    base_delay: float = 1.0,
    logger=None,
    source: str = "",
) -> tuple[Optional[T], Optional[str]]:
    """Variante síncrona de `fetch_with_retries` para conectores basados
    en `requests` en vez de `aiohttp`."""
    last_error: Optional[str] = None
    for attempt in range(1, retries + 1):
        try:
            return fetch_fn(), None
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
            if logger is not None:
                logger.warning(
                    "feed_fetch_attempt_failed",
                    source=source, attempt=attempt, retries=retries,
                    error=last_error,
                )
            if attempt < retries:
                time.sleep(base_delay * (2 ** (attempt - 1)))
    return None, last_error
