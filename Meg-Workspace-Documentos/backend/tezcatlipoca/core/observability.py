from __future__ import annotations
import json
import logging
import time
import uuid
from typing import Any

def build_logger(name: str = "tu_osint.enterprise") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger

def json_log(event: str, **payload: Any) -> str:
    body = {"event": event, "ts": time.time(), **payload}
    return json.dumps(body, ensure_ascii=False, default=str)

def correlate_request(request) -> str:
    return request.headers.get("X-Request-ID") or str(uuid.uuid4())
