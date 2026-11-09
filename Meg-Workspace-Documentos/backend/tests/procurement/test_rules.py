from app.engines.procurement.rules import DeterministicRuleRuntime


def test_rule_runtime_is_deterministic():
    runtime = DeterministicRuleRuntime()
    rule = {
        "id": "COST-001",
        "conditions": [
            {"field": "contract_type", "op": "eq", "val": "UNIT_PRICES"},
            {"field": "budget", "op": "gt", "val": 0},
        ],
        "message": "La estructura económica es aplicable.",
        "severity": "BLOCKER",
    }
    a = runtime.evaluate(rule, {"contract_type": "UNIT_PRICES", "budget": 100})
    b = runtime.evaluate(rule, {"contract_type": "UNIT_PRICES", "budget": 100})
    assert a == b
    assert a.matched is True
