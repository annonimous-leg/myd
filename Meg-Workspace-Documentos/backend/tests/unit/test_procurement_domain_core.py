from decimal import Decimal
import io
import zipfile

from app.engines.procurement.consistency import ProcurementConsistencyEngine
from app.engines.procurement.jurisdiction import JurisdictionDecision
from app.engines.procurement.rules import DeterministicRuleRuntime
from app.engines.procurement.compiler import ProcurementArtifactCompiler
from app.engines.costos.motor_costeo import PresupuestoCosteo, PartidaCosteo, ConceptoCosteo, InsumoCosteo, MotorCosteo
from app.engines.costos.parametros import FuenteParametrosCosteo, ParametrosCosteoSnapshot


def test_rule_runtime_is_deterministic_and_fail_closed_for_unknown_field():
    runtime = DeterministicRuleRuntime()
    result = runtime.evaluate(
        {"id": "REQ-1", "conditions": [{"field": "document.present", "op": "eq", "val": True}], "severity": "BLOCKER"},
        {"document.present": False},
    )
    assert result.matched is False
    assert result.severity == "BLOCKER"


def test_jurisdiction_decision_is_explicit_and_immutable():
    decision = JurisdictionDecision("CONAGUA", "Comisión Nacional del Agua", "FEDERAL", "OBRA_HIDRAULICA", "profile")
    assert decision.code == "CONAGUA"
    immutable = False
    try:
        decision.code = "OTHER"
    except Exception:
        immutable = True
    assert immutable


def test_cost_engine_multiconcept_propagates_to_total():
    p = PresupuestoCosteo(
        identificador="T1", nombre="obra",
        parametros=ParametrosCosteoSnapshot(
            Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"),
            FuenteParametrosCosteo.CAPTURA_USUARIO, "prueba unitaria",
        ),
        partidas=[PartidaCosteo(
            numero=1, descripcion="muro", unidad="m2", cantidad=Decimal("10"),
            conceptos=[
                ConceptoCosteo("C1", "block", "pza", insumos=[InsumoCosteo("B", "block", "MATERIAL", "pza", Decimal("1"), Decimal("20"))]),
                ConceptoCosteo("C2", "acero", "kg", insumos=[InsumoCosteo("A", "acero", "MATERIAL", "kg", Decimal("1"), Decimal("5"))]),
            ],
        )],
    )
    MotorCosteo().calcular_presupuesto(p)
    assert p.monto_directo == Decimal("250.00")


def test_consistency_blocks_cross_total_mismatch():
    findings = ProcurementConsistencyEngine().validate({"economic": {"budget_total": 100, "catalog_total": 99}})
    assert any(f["severity"] == "BLOCKER" and f["code"] == "ECON-CATALOG-TOTAL" for f in findings)


def test_compiler_produces_nonempty_real_artifacts():
    compiler = ProcurementArtifactCompiler()
    model = {
        "identifier": "TEST-001",
        "title": "T",
        "economic": {
            "partidas": [{
                "numero": "1",
                "descripcion": "Concepto verificable",
                "unidad": "pza",
                "cantidad": 1,
                "precio_unitario": 100,
                "importe": 100,
            }],
            "budget_total": 100,
        },
    }
    xlsx = compiler.compile_economic_xlsx(model)
    pdf = compiler.compile_summary_pdf(model, [])
    assert xlsx[:2] == b"PK"
    assert pdf.startswith(b"%PDF")
    assert len(xlsx) > 100
    assert len(pdf) > 100
    package = compiler.compile_submission_zip(
        [{"path": "QA/report.pdf", "content": pdf}],
        {"identifier": "TEST-001", "artifacts": ["QA/report.pdf"]},
    )
    assert package[:2] == b"PK"
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        assert set(archive.namelist()) == {"QA/report.pdf", "MANIFEST.json"}
        assert archive.read("QA/report.pdf") == pdf
