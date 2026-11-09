from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    matched: bool
    message: str
    severity: str
    rule_version: int | None = None
    evaluated_conditions: tuple[dict[str, Any], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CompiledRule:
    rule_id: str
    version: int
    definition: dict[str, Any]
    compiled_hash: str


@dataclass(frozen=True)
class CompiledDecisionRow:
    row_id: str
    order: int
    conditions: tuple[tuple[tuple[str, ...], str, Any], ...]
    action: dict[str, Any]
    message: str | None = None
    severity: str = "INFO"


@dataclass(frozen=True)
class CompiledDecisionTable:
    table_id: str
    version: int
    hit_policy: str
    rows: tuple[CompiledDecisionRow, ...]
    row_index_field: tuple[str, ...] | None
    row_index: dict[str, tuple[int, ...]]
    source_definition: dict[str, Any]
    compiled_hash: str


@dataclass(frozen=True)
class DecisionTableResult:
    table_id: str
    version: int
    matched: bool
    selected_row_ids: tuple[str, ...]
    actions: tuple[dict[str, Any], ...]
    evaluated_rows: tuple[dict[str, Any], ...]
    message: str
    error: str | None = None
    status: str = "MATCH"


class RuleCompilationError(ValueError):
    """The declarative rule is syntactically or semantically invalid."""


class DeterministicRuleCompiler:
    """Compile/validate declarative rules before runtime evaluation.

    This intentionally mirrors the useful OpenL boundary: a rule definition is
    validated and normalized before it can be executed. No Python/SQL/eval is
    generated from user input.
    """

    def __init__(self, runtime: DeterministicRuleRuntime | None = None):
        self.runtime = runtime or DeterministicRuleRuntime()

    def compile(self, definition: dict[str, Any], *, version: int = 1) -> CompiledRule:
        if not isinstance(definition, dict):
            raise RuleCompilationError("La definición de regla debe ser un objeto JSON.")
        rule_id = str(definition.get("id") or "").strip()
        if not rule_id:
            raise RuleCompilationError("La regla requiere id.")
        raw_conditions = definition.get("conditions", [])
        if not isinstance(raw_conditions, list) or not raw_conditions:
            raise RuleCompilationError(f"La regla {rule_id} requiere al menos una condición.")
        normalized = {
            "id": rule_id,
            "version": int(version),
            "message": str(definition.get("message") or "Rule not satisfied"),
            "severity": str(definition.get("severity") or "BLOCKER").upper(),
            "logic": str(definition.get("logic") or "ALL").upper(),
            "conditions": [],
        }
        if normalized["logic"] not in {"ALL", "ANY"}:
            raise RuleCompilationError("logic debe ser ALL o ANY.")
        for condition in raw_conditions:
            normalized["conditions"].append(self._validate_condition(condition, rule_id))
        # ALL/ANY are commutative, so canonicalize condition order for stable
        # hashes while preserving the executable semantics.
        normalized["conditions"].sort(key=lambda item: (item["field"], item["op"], json.dumps(item.get("val"), sort_keys=True, default=str)))
        # Deterministic canonical representation used as the executable/source hash.
        payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
        return CompiledRule(rule_id, int(version), normalized, hashlib.sha256(payload).hexdigest())

    def test(self, compiled: CompiledRule, cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for index, case in enumerate(cases):
            if not isinstance(case, dict):
                raise RuleCompilationError(f"Test case {index + 1} de {compiled.rule_id} no es un objeto.")
            facts = case.get("facts", {})
            expected = bool(case.get("expected", False))
            actual = self.runtime.evaluate(compiled.definition, facts).matched
            results.append({"index": index + 1, "expected": expected, "actual": actual, "passed": expected == actual})
        return results

    def compile_decision_table(
        self, definition: dict[str, Any], *, version: int = 1
    ) -> CompiledDecisionTable:
        """Compile a deterministic decision table without executing user code.

        This is the Megalodon analogue of OpenL's DecisionTable ->
        AlgorithmBuilder boundary: all paths/operators are validated once,
        row order is frozen, and safe candidate indexing is prepared before
        runtime evaluation.
        """
        if not isinstance(definition, dict):
            raise RuleCompilationError("La tabla de decisión debe ser un objeto JSON.")
        table_id = str(definition.get("id") or "").strip()
        if not table_id:
            raise RuleCompilationError("La tabla de decisión requiere id.")
        hit_policy = str(definition.get("hit_policy") or "UNIQUE").upper()
        if hit_policy not in {"FIRST", "UNIQUE", "ALL"}:
            raise RuleCompilationError("hit_policy debe ser FIRST, UNIQUE o ALL.")
        raw_rows = definition.get("rows")
        if not isinstance(raw_rows, list) or not raw_rows:
            raise RuleCompilationError(f"La tabla {table_id} requiere rows.")

        rows: list[CompiledDecisionRow] = []
        for order, raw_row in enumerate(raw_rows):
            if not isinstance(raw_row, dict):
                raise RuleCompilationError(f"Fila {order + 1} de {table_id} no es un objeto.")
            row_id = str(raw_row.get("id") or f"R{order + 1}").strip()
            if not row_id:
                raise RuleCompilationError(f"Fila {order + 1} de {table_id} requiere id.")
            raw_conditions = raw_row.get("conditions")
            if not isinstance(raw_conditions, list) or not raw_conditions:
                raise RuleCompilationError(f"Fila {row_id} requiere conditions.")
            compiled_conditions = []
            for condition in raw_conditions:
                normalized = self._validate_condition(condition, f"{table_id}:{row_id}")
                compiled_conditions.append(
                    (tuple(str(normalized["field"]).split(".")), normalized["op"], normalized.get("val"))
                )
            action = raw_row.get("action", {})
            if not isinstance(action, dict):
                raise RuleCompilationError(f"action de {table_id}:{row_id} debe ser objeto.")
            rows.append(
                CompiledDecisionRow(
                    row_id=row_id,
                    order=order,
                    conditions=tuple(compiled_conditions),
                    action=dict(action),
                    message=str(raw_row.get("message")) if raw_row.get("message") is not None else None,
                    severity=str(raw_row.get("severity") or "INFO").upper(),
                )
            )

        # Duplicate row IDs make diagnostics and test selection ambiguous.
        row_ids = [row.row_id for row in rows]
        if len(row_ids) != len(set(row_ids)):
            raise RuleCompilationError(f"row id duplicado en {table_id}.")

        index_field: tuple[str, ...] | None = None
        row_index: dict[str, tuple[int, ...]] = {}
        first_conditions = [row.conditions[0] for row in rows]
        if first_conditions and all(fc[0] == first_conditions[0][0] and fc[1] == "eq" for fc in first_conditions):
            index_field = first_conditions[0][0]
            mutable_index: dict[str, list[int]] = {}
            for position, row in enumerate(rows):
                value = row.conditions[0][2]
                key = self._stable_index_key(value)
                mutable_index.setdefault(key, []).append(position)
            row_index = {key: tuple(values) for key, values in mutable_index.items()}

        normalized_source = {
            "id": table_id,
            "version": int(version),
            "hit_policy": hit_policy,
            "rows": [
                {
                    "id": row.row_id,
                    "order": row.order,
                    "conditions": [
                        {"field": ".".join(path), "op": op, "val": value}
                        for path, op, value in row.conditions
                    ],
                    "action": row.action,
                    "message": row.message,
                    "severity": row.severity,
                }
                for row in rows
            ],
        }
        payload = json.dumps(normalized_source, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
        return CompiledDecisionTable(
            table_id=table_id,
            version=int(version),
            hit_policy=hit_policy,
            rows=tuple(rows),
            row_index_field=index_field,
            row_index=row_index,
            source_definition=normalized_source,
            compiled_hash=hashlib.sha256(payload).hexdigest(),
        )

    @staticmethod
    def _stable_index_key(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)

    def test_decision_table(
        self, compiled: CompiledDecisionTable, cases: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Execute Testmethod-like cases against the real runtime.

        Each case supplies facts and an expected row id/list or ``None`` for
        an expected miss. The production evaluator is the same evaluator used
        outside tests.
        """
        results: list[dict[str, Any]] = []
        for index, case in enumerate(cases):
            if not isinstance(case, dict):
                raise RuleCompilationError(f"Test case {index + 1} de {compiled.table_id} no es un objeto.")
            facts = case.get("facts", {})
            expected = case.get("expected")
            expected_action = case.get("expected_action")
            result = self.runtime.evaluate_decision_table(compiled, facts)
            actual: Any
            if compiled.hit_policy == "ALL":
                actual = list(result.selected_row_ids)
            elif compiled.hit_policy == "UNIQUE":
                actual = result.selected_row_ids[0] if len(result.selected_row_ids) == 1 else None
            else:
                actual = result.selected_row_ids[0] if result.selected_row_ids else None
            action_ok = expected_action is None or (len(result.actions) == 1 and result.actions[0] == expected_action)
            expected_error = case.get("expected_error")
            if expected_error is not None:
                error_ok = result.error == expected_error
            elif expected is None:
                error_ok = result.status == "NO_MATCH" and result.error == "DECISION_MISS: ninguna fila coincide."
            else:
                error_ok = result.error is None
            passed = actual == expected and action_ok and error_ok
            results.append({
                "index": index + 1,
                "expected": expected,
                "actual": actual,
                "expected_action": expected_action,
                "actual_action": result.actions[0] if len(result.actions) == 1 else list(result.actions),
                "passed": passed,
                "error": result.error,
                "expected_error": expected_error,
            })
        return results

    def _validate_condition(self, condition: Any, rule_id: str) -> dict[str, Any]:
        if not isinstance(condition, dict):
            raise RuleCompilationError(f"Condición inválida en {rule_id}.")
        field = str(condition.get("field") or "").strip()
        op = str(condition.get("op") or "").strip().lower()
        if not field:
            raise RuleCompilationError(f"Condición sin field en {rule_id}.")
        if op not in self.runtime.OPS:
            raise RuleCompilationError(f"Operador no soportado: {op}.")
        if op == "between":
            value = condition.get("val")
            if not isinstance(value, (list, tuple)) or len(value) != 2:
                raise RuleCompilationError(f"between requiere [min,max] en {rule_id}.")
        if op == "in" and not isinstance(condition.get("val"), (list, tuple, set)):
            raise RuleCompilationError(f"in requiere una lista de valores en {rule_id}.")
        if op in {"count_gte", "count_lte"}:
            try:
                if int(condition.get("val")) < 0:
                    raise ValueError
            except Exception as exc:
                raise RuleCompilationError(f"{op} requiere entero no negativo en {rule_id}.") from exc
        return {"field": field, "op": op, "val": condition.get("val")}


class DeterministicRuleRuntime:
    """Typed deterministic evaluator; no ML, network, eval, or fallbacks."""

    OPS = {
        "eq", "neq", "gt", "gte", "lt", "lte", "contains", "in",
        "exists", "not_exists", "not_empty", "count_gte", "count_lte", "between",
    }

    def evaluate_decision_table(self, table: CompiledDecisionTable, facts: dict[str, Any]) -> DecisionTableResult:
        if not isinstance(facts, dict):
            raise TypeError("facts debe ser un objeto JSON.")

        candidate_positions: list[int]
        if table.row_index_field is not None:
            present, value = self._resolve_path(facts, table.row_index_field)
            candidate_positions = list(table.row_index.get(
                DeterministicRuleCompiler._stable_index_key(value), ()
            )) if present else []
        else:
            candidate_positions = list(range(len(table.rows)))

        evaluated: list[dict[str, Any]] = []
        selected: list[CompiledDecisionRow] = []
        for position in candidate_positions:
            row = table.rows[position]
            row_evals = []
            matched = True
            for path, op, right in row.conditions:
                present, left = self._resolve_path(facts, path)
                try:
                    ok = self._compare(op, present, left, right)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Decision table {table.table_id}:{row.row_id}: comparison failed for {'.'.join(path)}: {exc}") from exc
                row_evals.append({
                    "field": ".".join(path),
                    "op": op,
                    "expected": right,
                    "observed": left,
                    "present": present,
                    "matched": ok,
                })
                if not ok:
                    matched = False
                    break
            evaluated.append({"row_id": row.row_id, "matched": matched, "conditions": row_evals})
            if matched:
                selected.append(row)
                if table.hit_policy == "FIRST":
                    break

        if table.hit_policy == "UNIQUE" and len(selected) > 1:
            error = "DECISION_CONFLICT: UNIQUE requiere exactamente una fila coincidente."
            return DecisionTableResult(
                table_id=table.table_id, version=table.version, matched=False,
                selected_row_ids=tuple(r.row_id for r in selected),
                actions=tuple(r.action for r in selected), evaluated_rows=tuple(evaluated),
                message=error, error=error, status="CONFLICT",
            )

        selected_ids = tuple(r.row_id for r in selected)
        error = None if selected else "DECISION_MISS: ninguna fila coincide."
        status = "MATCH" if selected else "NO_MATCH"
        message = ", ".join(selected_ids) if selected else error
        return DecisionTableResult(
            table_id=table.table_id,
            version=table.version,
            matched=bool(selected),
            selected_row_ids=selected_ids,
            actions=tuple(r.action for r in selected),
            evaluated_rows=tuple(evaluated),
            message=message,
            error=error,
            status=status,
        )

    def evaluate(self, rule: dict[str, Any], facts: dict[str, Any]) -> RuleResult:
        rid = str(rule["id"])
        version = int(rule["version"]) if rule.get("version") is not None else None
        conditions = rule.get("conditions", [])
        logic = str(rule.get("logic") or "ALL").upper()
        evaluations: list[dict[str, Any]] = []
        for c in conditions:
            op = str(c["op"]).lower()
            if op not in self.OPS:
                raise ValueError(f"Unsupported rule operator: {op}")
            present, left = self._resolve(facts, c["field"])
            right = c.get("val")
            try:
                ok = self._compare(op, present, left, right)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Rule {rid}: comparison failed for {c['field']}: {exc}") from exc
            evaluations.append({
                "field": c["field"],
                "op": op,
                "expected": right,
                "observed": left,
                "present": present,
                "matched": ok,
            })
        matched = all(e["matched"] for e in evaluations) if logic == "ALL" else any(e["matched"] for e in evaluations)
        default_message = "Rule satisfied" if matched else "Rule not satisfied"
        return RuleResult(
            rid, matched, str(rule.get("message", default_message)), str(rule.get("severity", "INFO" if matched else "BLOCKER")),
            version, tuple(evaluations),
        )

    @staticmethod
    def _resolve(facts: dict[str, Any], path: str) -> tuple[bool, Any]:
        return DeterministicRuleRuntime._resolve_path(facts, tuple(str(path).split(".")))

    @staticmethod
    def _resolve_path(facts: dict[str, Any], path: tuple[str, ...]) -> tuple[bool, Any]:
        if len(path) == 1 and path[0] in facts:
            return True, facts[path[0]]
        current: Any = facts
        for part in path:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return False, None
        return True, current

    @staticmethod
    def _compare(op: str, present: bool, left: Any, right: Any) -> bool:
        if op == "exists": return present
        if op == "not_exists": return not present
        if op == "eq": return present and left == right
        if op == "neq": return present and left != right
        if op == "gt": return present and left is not None and left > right
        if op == "gte": return present and left is not None and left >= right
        if op == "lt": return present and left is not None and left < right
        if op == "lte": return present and left is not None and left <= right
        if op == "contains": return present and left is not None and right in left
        if op == "in": return present and left in right
        if op == "not_empty": return present and left not in (None, "", [], {}, ())
        if op == "count_gte": return isinstance(left, (list, tuple, set, dict)) and len(left) >= int(right)
        if op == "count_lte": return isinstance(left, (list, tuple, set, dict)) and len(left) <= int(right)
        if op == "between": return present and left is not None and isinstance(right, (list, tuple)) and len(right) == 2 and right[0] <= left <= right[1]
        raise ValueError(op)
