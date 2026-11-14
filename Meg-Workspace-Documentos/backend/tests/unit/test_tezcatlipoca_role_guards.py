"""Static route contracts for Tezcatlipoca authorization.

The check is deliberately independent of a live database and ensures that
reader-tier users cannot invoke mutation endpoints by skipping route guards.
"""
from fastapi.routing import APIRoute

from routers.snapshots import router as snapshots_router
from routers.wormhole import router as wormhole_router


def _protected(router, path: str, method: str) -> bool:
    route = next(
        route for route in router.routes
        if isinstance(route, APIRoute) and route.path == path and method in route.methods
    )
    return any(
        getattr(dependency.call, "__name__", "") == "_check_role"
        for dependency in route.dependant.dependencies
    )


def test_snapshot_mutations_require_operational_role():
    assert _protected(snapshots_router, "/create", "POST")
    assert _protected(snapshots_router, "/{snapshot_id}", "DELETE")
    assert not _protected(snapshots_router, "/", "GET")


def test_wormhole_resource_mutations_require_operational_role():
    assert _protected(wormhole_router, "/tunnel/create", "POST")
    assert _protected(wormhole_router, "/tunnel/{tunnel_id}/close", "POST")
    assert _protected(wormhole_router, "/dead-drop/create", "POST")


def test_health_does_not_reveal_counts_from_other_tenants():
    import inspect
    from routers.wormhole import health
    body = inspect.getsource(health)
    assert '"active_tunnels":' not in body
    assert '"active_drops":' not in body
