from app.engines.procurement.rules import (
    DeterministicRuleCompiler,
    DeterministicRuleRuntime,
    RuleCompilationError,
)


def sample_table(hit_policy="FIRST"):
    return {
        "id": "PROC-SELECT-001",
        "hit_policy": hit_policy,
        "rows": [
            {"id": "R-LOW", "conditions": [{"field": "amount", "op": "lt", "val": 1_000_000}], "action": {"procedure": "DIRECT"}},
            {"id": "R-MID", "conditions": [{"field": "amount", "op": "gte", "val": 1_000_000}, {"field": "amount", "op": "lt", "val": 10_000_000}], "action": {"procedure": "INVITATION"}},
            {"id": "R-HIGH", "conditions": [{"field": "amount", "op": "gte", "val": 10_000_000}], "action": {"procedure": "PUBLIC_TENDER"}},
        ],
    }


def test_decision_table_selects_first_matching_row_deterministically():
    compiler = DeterministicRuleCompiler(); runtime = DeterministicRuleRuntime()
    compiled = compiler.compile_decision_table(sample_table(), version=4)
    result = runtime.evaluate_decision_table(compiled, {"amount": 2_500_000})
    assert result.matched is True
    assert result.selected_row_ids == ("R-MID",)
    assert result.actions == ({"procedure": "INVITATION"},)


def test_decision_table_preserves_row_order_for_overlapping_rules():
    compiler = DeterministicRuleCompiler(); runtime = DeterministicRuleRuntime()
    table = {"id": "OVERLAP", "hit_policy": "FIRST", "rows": [
        {"id": "R1", "conditions": [{"field": "amount", "op": "gte", "val": 1}], "action": {"x": 1}},
        {"id": "R2", "conditions": [{"field": "amount", "op": "gte", "val": 1}], "action": {"x": 2}},
    ]}
    result = runtime.evaluate_decision_table(compiler.compile_decision_table(table), {"amount": 5})
    assert result.selected_row_ids == ("R1",)


def test_unique_policy_reports_rule_conflict():
    compiler = DeterministicRuleCompiler(); runtime = DeterministicRuleRuntime()
    table = {"id": "UNIQUE", "hit_policy": "UNIQUE", "rows": [
        {"id": "R1", "conditions": [{"field": "amount", "op": "gte", "val": 1}], "action": {"x": 1}},
        {"id": "R2", "conditions": [{"field": "amount", "op": "gte", "val": 1}], "action": {"x": 2}},
    ]}
    result = runtime.evaluate_decision_table(compiler.compile_decision_table(table), {"amount": 5})
    assert result.matched is False
    assert result.status == "CONFLICT"
    assert result.error and result.error.startswith("DECISION_CONFLICT")
    assert result.selected_row_ids == ("R1", "R2")


def test_compile_prepares_safe_equality_index_without_changing_semantics():
    compiler = DeterministicRuleCompiler()
    table = {"id": "INDEXED", "rows": [
        {"id": "R-A", "conditions": [{"field": "category", "op": "eq", "val": "A"}], "action": {"p": 1}},
        {"id": "R-B", "conditions": [{"field": "category", "op": "eq", "val": "B"}], "action": {"p": 2}},
    ]}
    compiled = compiler.compile_decision_table(table)
    assert compiled.row_index_field == ("category",)
    assert len(compiled.row_index) == 2


def test_testmethod_calls_the_real_runtime():
    compiler = DeterministicRuleCompiler(); compiled = compiler.compile_decision_table(sample_table())
    results = compiler.test_decision_table(compiled, [
        {"facts": {"amount": 100_000}, "expected": "R-LOW", "expected_action": {"procedure": "DIRECT"}},
        {"facts": {"amount": 5_000_000}, "expected": "R-MID", "expected_action": {"procedure": "INVITATION"}},
        {"facts": {"amount": 25_000_000}, "expected": "R-HIGH", "expected_action": {"procedure": "PUBLIC_TENDER"}},
        {"facts": {"amount": None}, "expected": None},
    ])
    assert all(r["passed"] for r in results)
    assert results[-1]["error"] == "DECISION_MISS: ninguna fila coincide."


def test_compile_rejects_duplicate_row_ids():
    compiler = DeterministicRuleCompiler()
    table = {"id": "BAD", "rows": [
        {"id": "R1", "conditions": [{"field": "x", "op": "eq", "val": 1}]},
        {"id": "R1", "conditions": [{"field": "x", "op": "eq", "val": 2}]},
    ]}
    try:
        compiler.compile_decision_table(table)
    except RuleCompilationError:
        return
    raise AssertionError("duplicate row ids must be rejected during compilation")
