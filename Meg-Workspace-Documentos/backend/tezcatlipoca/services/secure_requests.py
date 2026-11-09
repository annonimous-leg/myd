"""Secure HTTP client for TU-OSINT external API requests.

Provides:
- Rotating User-Agent with project identification
- Jitter / random delays between requests
- Exponential backoff on 429/5xx errors
- SSL verification (always enabled)
- Timeout configuration
- Request logging
"""

import os
import random
import asyncio
import logging
from typing import Optional, Dict, Any
import aiohttp
import requests

logger = logging.getLogger("tu-osint.requests")

# ─── Configuration ───
USER_AGENT = os.getenv(
    "REQUEST_USER_AGENT",
    "TU-OSINT-Platform/2.3.5 (Research Project; security@example.com)"
)
DEFAULT_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
MAX_RETRIES = int(os.getenv("REQUEST_MAX_RETRIES", "3"))
JITTER_MIN = float(os.getenv("REQUEST_JITTER_MIN", "1.0"))
JITTER_MAX = float(os.getenv("REQUEST_JITTER_MAX", "3.0"))

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}


async def async_get(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = MAX_RETRIES,
    jitter: bool = True,
    **kwargs
) -> Dict[str, Any]:
    """Async GET with jitter, backoff, and SSL verification."""

    merged_headers = {**DEFAULT_HEADERS, **(headers or {})}

    # Jitter before request
    if jitter:
        delay = random.uniform(JITTER_MIN, JITTER_MAX)
        await asyncio.sleep(delay)

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=merged_headers,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                    ssl=True,  # Always verify SSL
                    **kwargs
                ) as response:
                    if response.status == 429:
                        # Rate limited - exponential backoff
                        backoff = 2 ** attempt
                        logger.warning(f"Rate limited by {url}, backing off {backoff}s (attempt {attempt})")
                        await asyncio.sleep(backoff)
                        continue

                    response.raise_for_status()

                    # Log successful request
                    logger.info(f"GET {url} - {response.status} (attempt {attempt})")

                    try:
                        return await response.json()
                    except:
                        text = await response.text()
                        return {"raw": text}

        except aiohttp.ClientResponseError as e:
            last_error = e
            if e.status >= 500 and attempt < retries:
                backoff = 2 ** attempt
                logger.warning(f"Server error {e.status} from {url}, retrying in {backoff}s")
                await asyncio.sleep(backoff)
                continue
            raise
        except Exception as e:
            last_error = e
            if attempt < retries:
                backoff = 2 ** attempt
                logger.warning(f"Request error to {url}: {e}, retrying in {backoff}s")
                await asyncio.sleep(backoff)
                continue
            raise

    raise last_error or Exception(f"Failed after {retries} attempts")


async def async_post(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = MAX_RETRIES,
    jitter: bool = True,
    **kwargs
) -> Dict[str, Any]:
    """Async POST with jitter, backoff, and SSL verification."""

    merged_headers = {**DEFAULT_HEADERS, **(headers or {})}

    if jitter:
        delay = random.uniform(JITTER_MIN, JITTER_MAX)
        await asyncio.sleep(delay)

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=merged_headers,
                    json=json_data,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                    ssl=True,
                    **kwargs
                ) as response:
                    if response.status == 429:
                        backoff = 2 ** attempt
                        logger.warning(f"Rate limited by {url}, backing off {backoff}s")
                        await asyncio.sleep(backoff)
                        continue

                    response.raise_for_status()
                    logger.info(f"POST {url} - {response.status} (attempt {attempt})")

                    try:
                        return await response.json()
                    except:
                        text = await response.text()
                        return {"raw": text}

        except aiohttp.ClientResponseError as e:
            last_error = e
            if e.status >= 500 and attempt < retries:
                backoff = 2 ** attempt
                await asyncio.sleep(backoff)
                continue
            raise
        except Exception as e:
            last_error = e
            if attempt < retries:
                backoff = 2 ** attempt
                await asyncio.sleep(backoff)
                continue
            raise

    raise last_error or Exception(f"Failed after {retries} attempts")


def sync_get(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = MAX_RETRIES,
    **kwargs
) -> Dict[str, Any]:
    """Sync GET with backoff and SSL verification."""

    merged_headers = {**DEFAULT_HEADERS, **(headers or {})}
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            response = requests.get(
                url,
                headers=merged_headers,
                params=params,
                timeout=timeout,
                verify=True,
                **kwargs
            )

            if response.status_code == 429:
                backoff = 2 ** attempt
                logger.warning(f"Rate limited by {url}, backing off {backoff}s")
                import time
                time.sleep(backoff)
                continue

            response.raise_for_status()
            logger.info(f"GET {url} - {response.status_code}")

            try:
                return response.json()
            except:
                return {"raw": response.text}

        except requests.exceptions.HTTPError as e:
            last_error = e
            if e.response.status_code >= 500 and attempt < retries:
                backoff = 2 ** attempt
                import time
                time.sleep(backoff)
                continue
            raise
        except Exception as e:
            last_error = e
            if attempt < retries:
                backoff = 2 ** attempt
                import time
                time.sleep(backoff)
                continue
            raise

    raise last_error or Exception(f"Failed after {retries} attempts")


def sync_post(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    data: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = MAX_RETRIES,
    **kwargs
) -> Dict[str, Any]:
    """Sync POST con el mismo backoff/rate-limit/SSL que sync_get.

    Se agregó porque conectores como URLhaus (query_url/query_host) usan
    POST con form-data, y sólo existía la variante GET -- estaban
    llamando requests.post() directo, sin ninguno de estos reintentos.
    """
    merged_headers = {**DEFAULT_HEADERS, **(headers or {})}
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            response = requests.post(
                url,
                headers=merged_headers,
                data=data,
                json=json_data,
                timeout=timeout,
                verify=True,
                **kwargs
            )

            if response.status_code == 429:
                backoff = 2 ** attempt
                logger.warning(f"Rate limited by {url}, backing off {backoff}s")
                import time
                time.sleep(backoff)
                continue

            response.raise_for_status()
            logger.info(f"POST {url} - {response.status_code}")

            try:
                return response.json()
            except Exception:
                return {"raw": response.text}

        except requests.exceptions.HTTPError as e:
            last_error = e
            if e.response is not None and e.response.status_code >= 500 and attempt < retries:
                backoff = 2 ** attempt
                import time
                time.sleep(backoff)
                continue
            raise
        except Exception as e:
            last_error = e
            if attempt < retries:
                backoff = 2 ** attempt
                import time
                time.sleep(backoff)
                continue
            raise

    raise last_error or Exception(f"Failed after {retries} attempts")
