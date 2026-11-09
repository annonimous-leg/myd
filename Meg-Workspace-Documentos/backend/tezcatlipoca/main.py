"""ASGI alias for the single Megalodon runtime.

Tezcatlipoca routes, identity, readiness and resource cleanup are owned by
app.main. Keeping a second FastAPI instance here created a divergent startup
and authorization policy. Existing ASGI imports resolve to the canonical app.
"""
from app.main import app

__all__ = ["app"]
