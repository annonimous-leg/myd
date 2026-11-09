from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet


class InvalidTenderTransition(ValueError):
    """Raised when a tender state transition violates the domain state machine."""


@dataclass(frozen=True)
class TransitionRule:
    source: str
    targets: FrozenSet[str]


class TenderLifecycle:
    """Deterministic state machine for the tender-preparation aggregate.

    The business flow is explicit and closed: no arbitrary state mutation is
    accepted by the application layer. Exception states are entered only by
    dedicated commands (block, observe, supersede, cancel, expire).
    """

    _NORMAL = {
        "DISCOVERED": frozenset({"INGESTED", "CANCELLED", "EXPIRED"}),
        "INGESTED": frozenset({"JURISDICTIONED", "OBSERVED", "BLOCKED"}),
        "JURISDICTIONED": frozenset({"REQUIREMENTS_MAPPED", "OBSERVED", "BLOCKED"}),
        "REQUIREMENTS_MAPPED": frozenset({"BIDDER_READY", "OBSERVED", "BLOCKED"}),
        "BIDDER_READY": frozenset({"TECHNICAL_MODEL_READY", "OBSERVED", "BLOCKED"}),
        "TECHNICAL_MODEL_READY": frozenset({"QUANTIFIED", "OBSERVED", "BLOCKED"}),
        "QUANTIFIED": frozenset({"ECONOMIC_MODEL_READY", "OBSERVED", "BLOCKED"}),
        "ECONOMIC_MODEL_READY": frozenset({"SCHEDULE_READY", "OBSERVED", "BLOCKED"}),
        "SCHEDULE_READY": frozenset({"DOCUMENTS_READY", "OBSERVED", "BLOCKED"}),
        "DOCUMENTS_READY": frozenset({"CROSS_VALIDATED", "OBSERVED", "BLOCKED"}),
        "CROSS_VALIDATED": frozenset({"QA_READY", "OBSERVED", "BLOCKED"}),
        "QA_READY": frozenset({"READY_FOR_HUMAN_REVIEW", "HUMAN_APPROVAL", "BLOCKED"}),
        "READY_FOR_HUMAN_REVIEW": frozenset({"HUMAN_APPROVAL", "BLOCKED"}),
        "HUMAN_APPROVAL": frozenset({"SIGNED", "SUBMISSION_READY", "BLOCKED"}),
        "SIGNED": frozenset({"SUBMISSION_READY", "BLOCKED"}),
        "SUBMISSION_READY": frozenset({"SUBMITTED", "BLOCKED"}),
        "SUBMITTED": frozenset({"ARCHIVED"}),
        "ARCHIVED": frozenset(),
        "OBSERVED": frozenset({"INGESTED", "JURISDICTIONED", "REQUIREMENTS_MAPPED", "BLOCKED", "CANCELLED"}),
        "BLOCKED": frozenset({"OBSERVED", "CANCELLED"}),
        "SUPERSEDED": frozenset(),
        "CANCELLED": frozenset(),
        "EXPIRED": frozenset(),
    }


    @classmethod
    def assert_transition(cls, source: str, target: str) -> None:
        src = str(source).upper()
        dst = str(target).upper()
        allowed = cls._NORMAL.get(src)
        if allowed is None:
            raise InvalidTenderTransition(f"Estado no reconocido: {source!r}")
        if dst not in allowed:
            raise InvalidTenderTransition(f"Transición no permitida: {src} -> {dst}")

    @classmethod
    def transition(cls, source: str, target: str) -> str:
        cls.assert_transition(source, target)
        return target
