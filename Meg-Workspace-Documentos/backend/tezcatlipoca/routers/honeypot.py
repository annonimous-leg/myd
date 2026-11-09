"""Honeypot Router - Conectado a HoneypotEngine real.

SECURITY: All endpoints now require authentication.
Only users with 'full' or 'admin' tier can inject honeypots.
"""
from core.rate_limit import rate_limit_standard, rate_limit_strict
from typing import Dict, Any

from fastapi import APIRouter, Request, Depends, HTTPException, status
from pydantic import BaseModel, Field
from db.models import User
from routers.auth import get_current_user, require_role

router = APIRouter(tags=["honeypot"])


def _get_honeypot_engine(request: Request):
    return getattr(request.app.state, "honeypot_engine", None)


def _get_peer_engine(request: Request):
    return getattr(request.app.state, "peer_engine", None)


def _coerce_truth(value: Any):
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return 1 if value >= 1 else 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "positive", "correct"}:
            return 1
        if lowered in {"0", "false", "no", "negative", "incorrect"}:
            return 0
    return None


def _extract_truth(payload: Dict[str, Any]):
    for candidate in (
        payload.get("truth"),
        payload.get("expected_truth"),
        payload.get("expected_report", {}).get("truth") if isinstance(payload.get("expected_report"), dict) else None,
        payload.get("fake_event", {}).get("truth") if isinstance(payload.get("fake_event"), dict) else None,
    ):
        truth = _coerce_truth(candidate)
        if truth is not None:
            return truth
    return None


# ─── Pydantic Models ───

class InjectRequest(BaseModel):
    node_id: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_\-]+$")
    payload: Dict[str, Any] = Field(default_factory=dict)
    difficulty: float = Field(default=0.5, ge=0.0, le=1.0)

class EvaluateRequest(BaseModel):
    node_id: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_\-]+$")
    report: Dict[str, Any] = Field(...)


# ─── Endpoints ───

@router.get("/status")
async def honeypot_status(
    request: Request,
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard)
):
    """Get honeypot engine status. (Auth required)"""
    hp = _get_honeypot_engine(request)
    if not hp:
        return {"error": "Honeypot engine not initialized"}

    suspicious_nodes = {
        node_id: hp.get_node_suspicion(node_id, len(hp.honeypots)).get('suspicion', 0.0)
        for node_id in list(hp.detected_nodes.keys())[:25]
    }

    return {
        "injected_tasks": len(hp.honeypots),
        "suspicion_scores": suspicious_nodes,
        "threshold": getattr(hp, "detection_threshold", 0.5),
        "base_rate": getattr(hp, "base_rate", 0.0),
        "adaptive_factor": getattr(hp, "adaptive_factor", 1.0),
        "covert_mode": getattr(hp, "covert_mode", False),
        "tracked_nodes": dict(list(hp.detected_nodes.items())[:25]),
        "viewer": current_user.username,
        "tier": current_user.tier
    }


@router.get("/suspicion/{node_id}")
async def get_suspicion(
    node_id: str,
    request: Request,
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard)
):
    """Get suspicion score for a specific node. (Auth required)"""
    hp = _get_honeypot_engine(request)
    if not hp:
        return {"error": "Honeypot engine not initialized"}

    suspicion_result = hp.get_node_suspicion(node_id, len(hp.honeypots))
    score = suspicion_result.get('suspicion', 0.0)
    return {
        "node_id": node_id,
        "suspicion": score,
        "suspicion_detail": suspicion_result,
        "threshold": getattr(hp, "detection_threshold", 0.5),
        "flagged": score > getattr(hp, "detection_threshold", 0.5),
        "viewer": current_user.username
    }


@router.post("/inject")
async def inject_honeypot(
    req: InjectRequest,
    request: Request,
    current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_strict)
):
    """Inject a honeypot task into a node. (Auth required - full/admin only)"""
    hp = _get_honeypot_engine(request)
    if not hp:
        return {"error": "Honeypot engine not initialized"}

    truth = _extract_truth(req.payload)
    if truth is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Could not extract truth value from payload")

    # Adaptar al contrato real de HoneypotEngine
    task_id = f"hp_{req.node_id}_{__import__('time').time()}"
    should = hp.should_inject(task_id, node_variance=req.difficulty, n_active_nodes=len(hp.detected_nodes))

    if not should:
        return {
            "status": "skipped",
            "node_id": req.node_id,
            "reason": "should_inject returned False (variance too low or base rate threshold not met)",
            "injector": current_user.username
        }

    generated = hp.generate_honeypot(task_id, task_type='binary', real_distribution={0: 1-truth, 1: truth})

    # Almacenar en el engine para evaluación posterior
    if not hasattr(hp, 'injected_by_node'):
        hp.injected_by_node = {}
    if req.node_id not in hp.injected_by_node:
        hp.injected_by_node[req.node_id] = []
    hp.injected_by_node[req.node_id].append({
        "task_id": task_id,
        "truth": truth,
        "difficulty": req.difficulty,
        "payload": req.payload,
        "generated": generated
    })

    return {
        "status": "injected",
        "node_id": req.node_id,
        "task_id": task_id,
        "truth": truth,
        "difficulty": req.difficulty,
        "generated": generated,
        "injector": current_user.username
    }


@router.post("/evaluate")
async def evaluate_node(
    req: EvaluateRequest,
    request: Request,
    current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_strict)
):
    """Evaluate a node's report against honeypots. (Auth required - full/admin only)"""
    hp = _get_honeypot_engine(request)
    if not hp:
        return {"error": "Honeypot engine not initialized"}

    report = req.report
    if not isinstance(report, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Report must be a dictionary")

    # Evaluar report contra todos los honeypots activos para este nodo
    evaluated = 0
    for task_id, hp_data in hp.honeypots.items():
        if req.node_id in hp_data.get('failed_by', []) or req.node_id in hp_data.get('detected_by', []):
            hp.evaluate_report(task_id, req.node_id, report)
            evaluated += 1

    suspicion_result = hp.get_node_suspicion(req.node_id, len(hp.honeypots))
    score = suspicion_result.get('suspicion', 0.0)

    return {
        "node_id": req.node_id,
        "suspicion": score,
        "threshold": getattr(hp, "detection_threshold", 0.5),
        "flagged": score > getattr(hp, "detection_threshold", 0.5),
        "evaluator": current_user.username
    }
