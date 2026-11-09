from copy import deepcopy
from app.engines.procurement.consistency import ProcurementConsistencyEngine


def budget():
    return {'economic': {'partidas': [{'importe': 100}], 'direct_cost': 100,
                         'indirect_cost': 10, 'profit': 11, 'risk': 0, 'tax': 19.36,
                         'budget_total': 140.36, 'letter_total': 140.36},
            'schedule': {'activities': [{'budget': 100}]}}


def test_direct_lines_and_complete_proposal_use_their_own_cost_basis():
    assert ProcurementConsistencyEngine().validate(budget()) == []


def test_inconsistent_budget_components_remain_blocked():
    model = deepcopy(budget())
    model['economic']['tax'] = 18
    assert 'ECON-BUDGET-COMPONENTS' in {x['code'] for x in ProcurementConsistencyEngine().validate(model)}


def test_proposal_letter_cannot_omit_charges():
    model = deepcopy(budget())
    model['economic']['letter_total'] = 100
    assert 'ECON-LETTER-TOTAL' in {x['code'] for x in ProcurementConsistencyEngine().validate(model)}
