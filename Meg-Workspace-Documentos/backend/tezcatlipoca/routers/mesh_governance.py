"""Mesh Governance Router - Conectado a SovereignShell real.

SECURITY: All endpoints now require authentication.
Only users with 'full' or 'admin' tier can create proposals and vote.
"""
from core.rate_limit import rate_limit_standard, rate_limit_strict
from fastapi import APIRouter, Request, Depends, HTTPException, status
from typing import Dict, Any
from pydantic import BaseModel, Field
from services.mesh.sovereign_shell import SovereignShell
from db.models import User
from routers.auth import get_current_user, require_role
from app.core.entitlements import PlanTipo, requiere_plan_minimo

router = APIRouter(tags=["mesh"], dependencies=[Depends(requiere_plan_minimo(PlanTipo.ENTERPRISE))])
_sovereign: SovereignShell | None = None


def set_sovereign(sovereign: SovereignShell):
    global _sovereign
    _sovereign = sovereign


def _get_sovereign(request: Request = None) -> SovereignShell | None:
    if _sovereign:
        return _sovereign
    if request is not None:
        return getattr(request.app.state, "sovereign", None)
    return None


# ─── Pydantic Models ───

class ProposalCreateRequest(BaseModel):
    type: str = Field(..., pattern=r"^(UPGRADE|UPDATE|ENABLE|DISABLE|SLASH|RESOLUTION)$")
    payload: Dict[str, Any] = Field(default_factory=dict)

class VoteRequest(BaseModel):
    vote: str = Field(..., pattern=r"^(yes|no|abstain)$")
    stake: float = Field(default=1.0, ge=0.0, le=1000000.0)


# ─── Endpoints ───

@router.get("/proposals")
async def list_proposals(
    request: Request,
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard)
):
    """List all governance proposals. (Auth required)"""
    sovereign = _get_sovereign(request)
    if not sovereign:
        return {"proposals": [], "error": "Sovereign not initialized"}
    return {
        "proposals": [
            {"id": pid, "proposer": p.proposer, "type": p.type.value, "status": p.status}
            for pid, p in sovereign.proposals.items()
        ]
    }


@router.post("/proposal")
async def create_proposal(
    req: ProposalCreateRequest,
    request: Request,
    current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_strict)
):
    """Create a new governance proposal. (Auth required - full/admin only)"""
    sovereign = _get_sovereign(request)
    if not sovereign:
        return {"error": "Sovereign not initialized"}

    from services.mesh.sovereign_shell import ProposalType
    ptype_map = {
        "UPGRADE": "upgrade_hash",
        "UPDATE": "update_param",
        "ENABLE": "enable_feature",
        "DISABLE": "disable_feature",
        "SLASH": "slash_node",
        "RESOLUTION": "resolution_market"
    }
    ptype = ProposalType[ptype_map.get(req.type, req.type)]

    # Registrar usuario como nodo si no existe
    if current_user.username not in sovereign.nodes:
        sovereign.register_node(current_user.username, "full", stake=0)

    proposal_id = sovereign.create_proposal(
        current_user.username,
        ptype,
        req.payload
    )
    return {"proposal_id": proposal_id, "status": "pending", "proposer": current_user.username}


@router.post("/proposal/{proposal_id}/vote")
async def vote_proposal(
    proposal_id: str,
    req: VoteRequest,
    request: Request,
    current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_strict)
):
    """Vote on a governance proposal. (Auth required - full/admin only)"""
    sovereign = _get_sovereign(request)
    if not sovereign:
        return {"error": "Sovereign not initialized"}

    # Registrar usuario como nodo si no existe
    if current_user.username not in sovereign.nodes:
        sovereign.register_node(current_user.username, "full", stake=req.stake)

    vote_bool = req.vote == "yes"
    sovereign.cast_vote(current_user.username, proposal_id, vote_bool)
    return {"proposal_id": proposal_id, "vote": req.vote, "stake": req.stake, "voter": current_user.username}


@router.get("/nodes")
async def list_nodes(
    request: Request,
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard)
):
    """List all mesh nodes. (Auth required)"""
    sovereign = _get_sovereign(request)
    if not sovereign:
        return {"nodes": [], "error": "Sovereign not initialized"}
    return {
        "nodes": [
            {"id": nid, "type": n.get('type', 'unknown'), "stake": n.get('stake', 0), "reputation": n.get('reputation', 0)}
            for nid, n in sovereign.nodes.items()
        ]
    }


@router.get("/node/{node_id}/score")
async def get_node_score(
    node_id: str,
    request: Request,
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard)
):
    """Get reputation score for a specific node. (Auth required)"""
    sovereign = _get_sovereign(request)
    if not sovereign:
        return {"error": "Sovereign not initialized"}

    node = sovereign.nodes.get(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    return {
        "node_id": node_id,
        "reputation": node.get('reputation', 0),
        "stake": node.get('stake', 0),
        "type": node.get('type', 'unknown'),
        "proposals_created": node.get('proposals_created', 0),
        "votes_cast": node.get('votes_cast', 0),
    }
