from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[2] / "app"


def _tree(rel: str):
    return ast.parse((ROOT / rel).read_text(encoding="utf-8"))


def test_requirement_mapper_has_no_normative_dependency():
    tree = _tree("engines/procurement/requirements.py")
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    imports = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imports |= {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    assert "LegalRule" not in names | imports
    assert "legal_rule" not in {x.lower() for x in names}


def test_tender_requirement_construction_is_confined_to_source_grounded_service():
    tree = _tree("services/procurement/service.py")
    constructions = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "TenderRequirement":
            fn = next((p for p in ast.walk(tree) if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef)) and p.lineno <= node.lineno <= getattr(p, "end_lineno", p.lineno)), None)
            constructions.append((fn.name if fn else None, node.lineno))
    assert {name for name, _ in constructions} <= {"derive_requirements", "add_requirement"}
    assert len(constructions) == 2


def test_normative_juridico_engine_does_not_construct_or_import_tender_requirement():
    for rel in ["engines/juridico/motor_juridico.py", "engines/juridico/selector_procedimiento.py", "services/juridico_service.py"]:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "TenderRequirement(" not in text
        assert "from app.models.procurement import TenderRequirement" not in text


def test_source_extraction_is_declared_mechanical_no_ai():
    text = (ROOT / "engines/procurement/source_extract.py").read_text(encoding="utf-8").lower()
    for forbidden in ("openai", "anthropic", "langchain", "transformers", "ollama"):
        assert forbidden not in text
    assert "mechanical" in text or "deterministic" in text
