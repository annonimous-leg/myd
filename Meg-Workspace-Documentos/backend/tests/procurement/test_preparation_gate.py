from app.engines.procurement.lifecycle import TenderLifecycle
from app.engines.procurement.rules import DeterministicRuleRuntime


def test_ready_for_human_review_is_explicit_lifecycle_gate():
    TenderLifecycle.assert_transition("QA_READY", "READY_FOR_HUMAN_REVIEW")
    TenderLifecycle.assert_transition("READY_FOR_HUMAN_REVIEW", "HUMAN_APPROVAL")


def test_rule_runtime_supports_nested_paths_and_collection_counts():
    runtime = DeterministicRuleRuntime()
    facts = {"bidder": {"capital": 5_000_000}, "documents": ["A", "B", "C"]}
    assert runtime.evaluate({"id": "CAP", "conditions": [{"field": "bidder.capital", "op": "gte", "val": 4_000_000}]}, facts).matched
    assert runtime.evaluate({"id": "DOCS", "conditions": [{"field": "documents", "op": "count_gte", "val": 3}]}, facts).matched
    assert not runtime.evaluate({"id": "CAP2", "conditions": [{"field": "bidder.capital", "op": "lt", "val": 4_000_000}]}, facts).matched


def test_ready_gate_is_distinct_from_human_approval():
    assert TenderLifecycle.transition("QA_READY", "READY_FOR_HUMAN_REVIEW") == "READY_FOR_HUMAN_REVIEW"
    assert TenderLifecycle.transition("READY_FOR_HUMAN_REVIEW", "HUMAN_APPROVAL") == "HUMAN_APPROVAL"
