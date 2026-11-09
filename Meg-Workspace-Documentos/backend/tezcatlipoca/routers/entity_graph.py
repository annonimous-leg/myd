"""Entity Graph Router - Conectado a OSINT."""
from core.rate_limit import rate_limit_standard, rate_limit_strict
from typing import Dict, Any

from fastapi import APIRouter, Request, Depends

from services.osint_recon.osint_engine import OSINTReconEngine
from db.models import User
from routers.auth import get_current_user, require_role

router = APIRouter()


def _get_osint_engine(request: Request) -> OSINTReconEngine | None:
    return getattr(request.app.state, "osint_engine", None)


def _build_graph(entity: str, expanded: Dict[str, Any]) -> Dict[str, Any]:
    connections = expanded.get("connections", []) or []
    nodes = [{"id": entity, "type": "root", "label": entity}]
    edges = []

    for idx, conn in enumerate(connections):
        conn_type = conn.get("type", "connection")
        node_id = f"{entity}:{conn_type}:{idx}"
        nodes.append({
            "id": node_id,
            "type": conn_type,
            "label": conn_type,
            "data": conn.get("data", {})
        })
        edges.append({
            "source": entity,
            "target": node_id,
            "type": conn_type
        })

    return {
        "entity": entity,
        "depth": expanded.get("depth", 1),
        "nodes": nodes,
        "edges": edges,
        "connections": connections,
        "source": "osint"
    }


@router.post("/expand")
async def expand_entity(request: Dict[str, Any], req: Request, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_strict)):
    engine = _get_osint_engine(req)
    entity = request.get("entity", "")
    depth = request.get("depth", 1)

    if not engine:
        return {
            "entity": entity,
            "depth": depth,
            "nodes": [{"id": entity, "type": "root", "label": entity}] if entity else [],
            "edges": [],
            "connections": [],
            "error": "OSINT engine not initialized"
        }

    expanded = await engine.expand_entity(entity, depth)
    return _build_graph(entity, expanded)


@router.get("/{entity_id}")
async def get_entity(entity_id: str, req: Request, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)):
    engine = _get_osint_engine(req)
    if not engine:
        return {
            "id": entity_id,
            "type": "unknown",
            "properties": {},
            "relations": [],
            "error": "OSINT engine not initialized"
        }

    lookup = await engine.lookup(entity_id, "auto")
    return {
        "id": entity_id,
        "type": lookup.get("type", "unknown"),
        "properties": lookup,
        "relations": lookup.get("connections", []),
        "source": "osint"
    }
