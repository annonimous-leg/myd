"""Open-Meteo - Clima y calidad del aire sin autenticación."""
import aiohttp
import structlog
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta

from services.feed_resilience import PersistentFeedCache, STATUS_LIVE

logger = structlog.get_logger("tezcatlipoca.weather.open_meteo")

# Antes no había NINGÚN caché: cada llamada pegaba directo a la red,
# incluso para la misma lat/lon consultada hace 5 segundos. El clima
# no cambia a esa velocidad -- un TTL corto evita gastar cuota del
# tier gratuito (10K/día) sin perder frescura real.
_CACHE_TTL = timedelta(minutes=10)


class OpenMeteoClient:
    """Cliente para Open-Meteo API (10K/día, sin auth)."""

    def __init__(self):
        self.base_url = "https://api.open-meteo.com/v1"
        self.http = aiohttp.ClientSession()
        self._mem_cache: Dict[str, Any] = {}
        self._mem_cache_time: Dict[str, datetime] = {}
        self._feed_cache = PersistentFeedCache()
        self.last_status: Dict[str, str] = {}

    async def close(self):
        if self.http and not self.http.closed:
            await self.http.close()

    @staticmethod
    def _key(kind: str, lat: float, lon: float, **extra) -> str:
        suffix = "_".join(f"{k}={v}" for k, v in sorted(extra.items()))
        return f"open_meteo_{kind}_{lat:.3f}_{lon:.3f}_{suffix}"

    async def _get_with_fallback(self, url: str, params: dict, *, cache_key: str, retries: int = 2) -> Dict[str, Any]:
        """GET con reintento corto, caché en memoria (TTL) y respaldo en
        disco si la fuente en vivo falla y no hay caché de memoria
        vigente (p. ej. proceso recién iniciado)."""
        now = datetime.now(timezone.utc)
        cached_at = self._mem_cache_time.get(cache_key)
        if cached_at and (now - cached_at) < _CACHE_TTL:
            self.last_status[cache_key] = STATUS_LIVE
            return self._mem_cache[cache_key]

        last_error = None
        for attempt in range(1, retries + 1):
            try:
                async with self.http.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                self._mem_cache[cache_key] = data
                self._mem_cache_time[cache_key] = now
                self._feed_cache.save(cache_key, data)
                self.last_status[cache_key] = STATUS_LIVE
                return data
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                logger.warning("open_meteo_attempt_failed", url=url, attempt=attempt, retries=retries, error=last_error)
                if attempt < retries:
                    import asyncio
                    await asyncio.sleep(1.0 * attempt)

        backup = self._feed_cache.load(cache_key)
        if backup is not None:
            self.last_status[cache_key] = "stale_cache"
            logger.warning("open_meteo_serving_stale_cache", url=url, fetched_at=backup.get("fetched_at"), error=last_error)
            return backup.get("data", {})

        self.last_status[cache_key] = "unavailable"
        logger.error("open_meteo_unavailable_no_backup", url=url, error=last_error)
        return {}

    async def get_forecast(self, lat: float, lon: float,
                           forecast_days: int = 3) -> Dict[str, Any]:
        """Pronóstico del tiempo."""
        url = f"{self.base_url}/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": ["temperature_2m", "windspeed_10m", "winddirection_10m", "precipitation"],
            "forecast_days": forecast_days
        }
        key = self._key("forecast", lat, lon, days=forecast_days)
        return await self._get_with_fallback(url, params, cache_key=key)

    async def get_air_quality(self, lat: float, lon: float) -> Dict[str, Any]:
        """Calidad del aire."""
        url = "https://air-quality-api.open-meteo.com/v1/air-quality"
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": ["pm10", "pm2_5", "carbon_monoxide", "nitrogen_dioxide"]
        }
        key = self._key("air_quality", lat, lon)
        return await self._get_with_fallback(url, params, cache_key=key)

    async def get_wind_at_altitude(self, lat: float, lon: float,
                                    altitude: int = 1000) -> Dict[str, Any]:
        """Viento a altitud específica (para dispersión de ceniza)."""
        url = f"{self.base_url}/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": [f"windspeed_{altitude}hPa", f"winddirection_{altitude}hPa"]
        }
        key = self._key("wind", lat, lon, alt=altitude)
        return await self._get_with_fallback(url, params, cache_key=key)
