from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Iterable


@dataclass(frozen=True)
class MinedRequirement:
    code: str
    category: str
    description: str
    mandatory: bool
    condition: dict[str, Any]
    source_reference: dict[str, Any]
    evidence_required: list[str]
    artifact_required: list[str]
    severity: str
    validator_code: str | None
    approver_role: str | None


class ProcurementRequirementMapper:
    """Maps requirements ONLY from the effective tender evidence supplied by the user.

    LegalRule/corpus data is deliberately not consulted here.  A tender requirement
    is authoritative only when it has evidence in the current tender package.
    Normative cross-checking belongs to the isolated normative/pre-fall layer.
    """

    @staticmethod
    def _matches(condition: dict[str, Any], facts: dict[str, Any]) -> bool:
        """Evaluate the small, explicit condition grammar used by DB rules.

        Unknown operators, absent fields, and malformed structures fail closed.
        Both ``value`` and the persisted-rule spelling ``val`` are accepted.
        """
        if not isinstance(condition, dict) or not condition:
            return False
        if "conditions" in condition:
            conditions = condition.get("conditions")
            return bool(conditions) and isinstance(conditions, list) and all(
                ProcurementRequirementMapper._matches(item, facts)
                for item in conditions
            )
        if "all_of" in condition:
            items = condition.get("all_of")
            return bool(items) and isinstance(items, list) and all(
                ProcurementRequirementMapper._matches(item, facts) for item in items
            )
        if "any_of" in condition:
            items = condition.get("any_of")
            return bool(items) and isinstance(items, list) and any(
                ProcurementRequirementMapper._matches(item, facts) for item in items
            )
        if "not" in condition:
            nested = condition.get("not")
            return isinstance(nested, dict) and not ProcurementRequirementMapper._matches(nested, facts)

        field = condition.get("field")
        operator = str(condition.get("op") or "").lower()
        if not isinstance(field, str) or not field or field not in facts:
            return False
        if "value" in condition:
            expected = condition["value"]
        elif "val" in condition:
            expected = condition["val"]
        else:
            return False
        actual = facts[field]
        try:
            if operator == "eq":
                return actual == expected
            if operator == "ne":
                return actual != expected
            if operator == "in":
                return isinstance(expected, (list, tuple, set)) and actual in expected
            if operator == "not_in":
                return isinstance(expected, (list, tuple, set)) and actual not in expected
            if operator == "gt":
                return actual > expected
            if operator == "gte":
                return actual >= expected
            if operator == "lt":
                return actual < expected
            if operator == "lte":
                return actual <= expected
        except (TypeError, ValueError):
            return False
        return False

    @staticmethod
    def _definition_signature(requirement: MinedRequirement) -> str:
        return json.dumps({
            "category": requirement.category,
            "description": requirement.description,
            "mandatory": requirement.mandatory,
            "condition": requirement.condition or {},
            "evidence_required": requirement.evidence_required or [],
            "artifact_required": requirement.artifact_required or [],
            "severity": requirement.severity,
            "validator_code": requirement.validator_code,
            "approver_role": requirement.approver_role,
        }, sort_keys=True, separators=(",", ":"), default=str)

    @staticmethod
    def _append_supporting_source(primary: dict[str, Any], additional: dict[str, Any]) -> None:
        sources = primary.get("supporting_sources")
        if not isinstance(sources, list):
            sources = [{key: value for key, value in primary.items() if key != "supporting_sources"}]
            primary["supporting_sources"] = sources
        incoming_key = json.dumps(additional, sort_keys=True, separators=(",", ":"), default=str)
        for existing in sources:
            if json.dumps(existing, sort_keys=True, separators=(",", ":"), default=str) == incoming_key:
                return
        sources.append(dict(additional))

    def derive(
        self,
        *,
        tender_id: Any,
        source_texts: Iterable[dict[str, Any]],
        facts: dict[str, Any] | None = None,
    ) -> list[MinedRequirement]:
        _ = tender_id, facts
        result: list[MinedRequirement] = []
        seen: dict[str, MinedRequirement] = {}
        for source in source_texts:
            # Extraction stage may provide structured candidate requirements.
            # Never synthesize an obligation merely because a word appears in text.
            candidates = source.get("requirements") or source.get("extracted_requirements") or []
            if not isinstance(candidates, list):
                raise ValueError("requirements extraídos debe ser una lista.")
            source_ref = {
                "source_id": source.get("source_id"),
                "source_hash": source.get("source_hash"),
                "uri": source.get("uri"),
                "document_id": source.get("document_id"),
                "revision": source.get("revision"),
            }
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    raise ValueError("Cada requisito extraído debe ser un objeto.")
                code = str(candidate.get("code") or "").strip()
                description = str(candidate.get("description") or "").strip()
                if not code or not description:
                    raise ValueError("Un requisito extraído requiere code y description.")
                evidence = candidate.get("source_reference") or {}
                if not isinstance(evidence, dict):
                    raise ValueError(f"source_reference inválido para {code}.")
                mandatory = candidate.get("mandatory", True)
                if not isinstance(mandatory, bool):
                    raise ValueError(
                        f"El requisito {code} requiere confirmación booleana explícita de obligatoriedad."
                    )
                merged_ref = {**source_ref, **evidence, "authority": "TENDER_SOURCE"}
                mined = MinedRequirement(
                    code=code,
                    category=str(candidate.get("category") or "ADMINISTRATIVO").strip().upper(),
                    description=description,
                    mandatory=mandatory,
                    condition=dict(candidate.get("condition") or {}),
                    source_reference=merged_ref,
                    evidence_required=[str(x) for x in candidate.get("evidence_required", [])],
                    artifact_required=[str(x) for x in candidate.get("artifact_required", [])],
                    severity=str(candidate.get("severity") or "BLOCKER").upper(),
                    validator_code=str(candidate["validator_code"]) if candidate.get("validator_code") else None,
                    approver_role=str(candidate["approver_role"]) if candidate.get("approver_role") else None,
                )
                previous = seen.get(code)
                if previous is not None:
                    if self._definition_signature(previous) != self._definition_signature(mined):
                        raise ValueError(
                            f"Conflicto para el código {code}: distintas fuentes confirmadas contienen "
                            "definiciones de requisito diferentes. Se requiere conciliación humana antes de derivar."
                        )
                    self._append_supporting_source(previous.source_reference, merged_ref)
                    continue
                seen[code] = mined
                result.append(mined)
        return result

