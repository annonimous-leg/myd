import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engines.procurement.reference_cases import ConaguaPtArCaseParser
from app.engines.procurement.compiler import ProcurementArtifactCompiler
from app.engines.procurement.consistency import ProcurementConsistencyEngine


GUIDE_CASE = Path(__file__).parent / 'fixtures' / 'procurement' / 'CONAGUA_PTAR_GUIDE_CASE_2026.md'


def test_conagua_case_extracts_all_guided_annexes():
    text = GUIDE_CASE.read_text(encoding='utf-8')
    case = ConaguaPtArCaseParser().parse(text)
    expected = {*(f'AT-{i:02d}' for i in range(1, 14)), *(f'AE-{i:02d}' for i in range(1, 13))}
    assert set(case.sections) == expected
    assert len(case.economic['partidas']) == 27
    assert any(p['numero'] == '2.01.006' and p['conceptos'] for p in case.economic['partidas'])
    assert len(case.economic['indirect_costs']['items']) == 9
    assert len(case.economic['material_schedule']) == 9
    assert len(case.economic['labor_schedule']) == 9
    assert len(case.economic['equipment_schedule']) == 8


def test_conagua_reference_case_compiles_all_annex_working_artifacts():
    case = ConaguaPtArCaseParser().parse(GUIDE_CASE.read_text(encoding='utf-8'))
    model = {
        'identifier': case.facts['identifier'],
        'title': case.facts['object'],
        'facts': case.facts,
        'technical': case.technical,
        'economic': case.economic,
        'schedule': case.schedule,
        'bidder': case.bidder,
        'jurisdiction_code': case.facts['jurisdiction_code'],
        'revision': 1,
    }
    compiler = ProcurementArtifactCompiler()
    for code in [*(f'AT-{i:02d}' for i in range(1, 14)), *(f'AE-{i:02d}' for i in range(1, 13))]:
        assert len(compiler.compile_annex_pdf(code, code, model)) > 500


def test_conagua_reference_case_exposes_the_catalog_total_inconsistency():
    case = ConaguaPtArCaseParser().parse(GUIDE_CASE.read_text(encoding='utf-8'))
    findings = ProcurementConsistencyEngine().validate({
        'economic': case.economic,
        'schedule': case.schedule,
        'technical': case.technical,
        'documents': [],
    })
    assert any(item['code'] == 'ECON-CATALOG-TOTAL' for item in findings)


def test_requirement_condition_accepts_rule_val_form():
    from app.engines.procurement.requirements import ProcurementRequirementMapper
    assert ProcurementRequirementMapper._matches({"conditions": [{"field": "contract_type", "op": "eq", "val": "UNIT_PRICES"}]}, {"contract_type": "UNIT_PRICES"})
    assert not ProcurementRequirementMapper._matches({"conditions": [{"field": "contract_type", "op": "eq", "val": "LUMP_SUM"}]}, {"contract_type": "UNIT_PRICES"})
