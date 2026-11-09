"""Server-owned policy for artifacts crossing the bidder submission boundary.

The internal QA report is useful workspace evidence, but it is not an official
submission document and must never become a signed deliverable by default.
Submission eligibility is fail-closed: every artifact needs an explicit,
server-owned boolean policy before it can enter the external package.
"""
from __future__ import annotations

from typing import Any


def _metadata(artifact: Any) -> dict[str, Any]:
    value = getattr(artifact, "artifact_metadata", None)
    return value if isinstance(value, dict) else {}


def _code(artifact: Any) -> str:
    return str(getattr(artifact, "artifact_code", "") or "").strip().upper()


def artifact_submission_eligible(artifact: Any) -> bool:
    """Whether a generated workspace artifact belongs in the external bidder ZIP."""
    if _code(artifact) == "QA-REPORT":
        return False
    value = _metadata(artifact).get("submission_eligible")
    # Legacy/unknown artifacts must not enter an external package implicitly.
    return value if isinstance(value, bool) else False


def artifact_requires_signature(artifact: Any) -> bool:
    """Whether the configured document policy requires a PAdES signature."""
    if not artifact_submission_eligible(artifact):
        return False
    value = _metadata(artifact).get("signature_required")
    if isinstance(value, bool):
        return value
    return getattr(artifact, "media_type", None) == "application/pdf"
