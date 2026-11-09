from app.engines.procurement.rules import DeterministicRuleCompiler, DeterministicRuleRuntime, RuleCompilationError


def test_compile_normalizes_and_hashes_rule_deterministically():
    compiler = DeterministicRuleCompiler()
    definition = {
        "id": "REQ-CAP-001",
        "severity": "BLOCKER",
        "message": "Capital insuficiente",
        "conditions": [
            {"field": "bidder.capital", "op": "gte", "val": 4_000_000},
            {"field": "documents", "op": "count_gte", "val": 2},
        ],
    }
    first = compiler.compile(definition, version=3)
    second = compiler.compile({**definition, "conditions": list(reversed(definition["conditions"]))}, version=3)
    assert first.version == 3
    assert first.compiled_hash == second.compiled_hash


def test_compile_rejects_unsupported_or_malformed_rules_before_runtime():
    compiler = DeterministicRuleCompiler()
    try:
        compiler.compile({"id": "BAD", "conditions": [{"field": "x", "op": "python", "val": 1}]})
        assert False, "unsupported operator must be rejected"
    except RuleCompilationError:
        pass
    try:
        compiler.compile({"id": "BAD2", "conditions": [{"field": "x", "op": "between", "val": [1]}]})
        assert False, "malformed between must be rejected"
    except RuleCompilationError:
        pass


def test_runtime_returns_explanation_for_each_condition():
    runtime = DeterministicRuleRuntime()
    result = runtime.evaluate(
        {
            "id": "REQ-CAP-001",
            "version": 2,
            "logic": "ALL",
            "conditions": [
                {"field": "bidder.capital", "op": "gte", "val": 4_000_000},
                {"field": "documents", "op": "count_gte", "val": 2},
            ],
        },
        {"bidder": {"capital": 5_000_000}, "documents": ["A", "B"]},
    )
    assert result.matched is True
    assert result.rule_version == 2
    assert len(result.evaluated_conditions) == 2
    assert all(item["matched"] for item in result.evaluated_conditions)
