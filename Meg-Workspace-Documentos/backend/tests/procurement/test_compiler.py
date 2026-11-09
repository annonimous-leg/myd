from app.engines.procurement.compiler import ProcurementArtifactCompiler
from io import BytesIO
from types import SimpleNamespace
import zipfile
from openpyxl import load_workbook, Workbook
import pytest


def model():
    return {
        "identifier": "LIC-001",
        "title": "Obra de prueba real del motor",
        "jurisdiction_code": "FEDERAL",
        "revision": 1,
        "economic": {
            "budget_total": 110,
            "partidas": [{
                "numero": 1, "descripcion": "Movimiento de tierras", "unidad": "m3", "cantidad": 10,
                "precio_unitario": 11, "importe": 110,
                "conceptos": [{
                    "clave": "MT-001", "descripcion": "Excavación", "unidad": "m3", "cantidad": 10,
                    "costo_directo_unitario": 11,
                    "insumos": [{"clave": "MAT-01", "descripcion": "Material", "unidad": "m3", "cantidad": 10, "importe": 110}],
                }],
            }]
        },
        "schedule": {"duration_days": 10, "activities": [{"id": "A1", "wbs_code": "1.1", "name": "Excavación", "duration_days": 10, "budget": 110, "predecessors": []}]},
    }


def test_artifacts_are_reproducible():
    c = ProcurementArtifactCompiler()
    x1 = c.compile_economic_xlsx(model())
    x2 = c.compile_economic_xlsx(model())
    assert c.sha256(x1) == c.sha256(x2)
    p1 = c.compile_summary_pdf(model(), [])
    p2 = c.compile_summary_pdf(model(), [])
    assert c.sha256(p1) == c.sha256(p2)
    z1 = c.compile_submission_zip([{"path": "AE-02/v1.xlsx", "content": x1}], {"revision": 1})
    z2 = c.compile_submission_zip([{"path": "AE-02/v1.xlsx", "content": x2}], {"revision": 1})
    assert c.sha256(z1) == c.sha256(z2)


@pytest.mark.parametrize('method', ['compile_economic_xlsx', 'compile_apu_xlsx', 'compile_schedule_xlsx'])
def test_xlsx_is_reproducible_across_zip_clock_boundaries(monkeypatch, method):
    compiler = ProcurementArtifactCompiler()
    clock = SimpleNamespace(time=lambda: 0, localtime=lambda _: (2026, 1, 1, 0, 0, 0, 0, 1, 0))
    monkeypatch.setattr(zipfile, 'time', clock)
    before = getattr(compiler, method)(model())
    clock.localtime = lambda _: (2026, 10, 8, 23, 59, 59, 0, 1, 0)
    after = getattr(compiler, method)(model())
    assert before == after
    workbook = load_workbook(BytesIO(after))
    assert workbook.properties.modified.isoformat().startswith('2000-01-01')
    assert workbook.active.max_row > 1



@pytest.mark.parametrize("unsafe_path", [
    "../escape.pdf",
    "/absolute/file.pdf",
    r"C:\\windows\\system32\\payload.pdf",
    "folder/../escape.pdf",
    "folder//file.pdf",
    "folder/./file.pdf",
    "MANIFEST.json",
    "CON/contract.pdf",
    "folder/name.pdf.",
    "folder/name.pdf ",
])
def test_submission_zip_rejects_unsafe_paths(unsafe_path):
    compiler = ProcurementArtifactCompiler()
    with pytest.raises(ValueError):
        compiler.compile_submission_zip(
            [{"path": unsafe_path, "content": b"document"}],
            {"revision": 1},
        )


def test_submission_zip_rejects_case_insensitive_duplicate_paths():
    compiler = ProcurementArtifactCompiler()
    with pytest.raises(ValueError, match="duplicada"):
        compiler.compile_submission_zip(
            [
                {"path": "TEC-01/v1-Memoria.pdf", "content": b"one"},
                {"path": "tec-01/V1-memoria.pdf", "content": b"two"},
            ],
            {"revision": 1},
        )



def test_xlsx_escapes_formula_like_values_from_tender_content():
    compiler = ProcurementArtifactCompiler()
    payload = model()
    payload["economic"]["partidas"][0]["descripcion"] = '=HYPERLINK("https://example.invalid","open")'

    workbook = load_workbook(BytesIO(compiler.compile_economic_xlsx(payload)), data_only=False)
    cell = workbook["Catalogo"]["B2"]

    assert cell.data_type == "s"
    assert cell.value == '=HYPERLINK("https://example.invalid","open")'


def test_safe_xlsx_row_preserves_numbers_and_escapes_all_formula_prefixes():
    compiler = ProcurementArtifactCompiler()
    workbook = Workbook()
    worksheet = workbook.active

    compiler._append_safe_row(worksheet, ["=1+1", " +SUM(A1:A2)", "-cmd", "@value", 12.5])

    assert [worksheet.cell(row=1, column=i).data_type for i in range(1, 6)] == [
        "s", "s", "s", "s", "n"
    ]
    assert worksheet["A1"].value == "=1+1"
    assert worksheet["B1"].value == " +SUM(A1:A2)"
    assert worksheet["C1"].value == "-cmd"
    assert worksheet["D1"].value == "@value"
