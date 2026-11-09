from app.engines.procurement.source_extract import ExtractedSource, TenderSourceExtractor

def _source(text: str):
    return ExtractedSource("convocatoria.txt", "text/plain", text, None, {"format": "txt"})

def test_only_explicit_configured_section_items_become_candidates():
    ext = TenderSourceExtractor()
    cfg = {"source_roles": {"CONVOCATORIA": {
        "headings": ["REQUISITOS DE PARTICIPACIÓN"],
        "stop_headings": ["ANEXOS"],
        "item_pattern": r"^\s*(?:[-•*]|\d+[.)]|[A-Za-z][.)])\s+(.+?)\s*$",
        "category": "ADMINISTRATIVO",
        "mandatory_default": None,
    }}}
    rows = ext.extract_requirement_candidates(
        _source("Objeto de la obra\nREQUISITOS DE PARTICIPACIÓN\n1. Presentar constancia fiscal vigente\n2. Acreditar experiencia específica\nANEXOS\nTexto libre que no debe entrar"),
        source_id="src-1", source_hash="abcdef123456", source_role="CONVOCATORIA", extraction_config=cfg,
    )
    assert len(rows) == 2
    assert rows[0]["status"] == "REVIEW_REQUIRED"
    assert rows[0]["mandatory"] is None
    assert rows[0]["source_reference"]["authority"] == "TENDER_SOURCE"

def test_no_configuration_means_no_requirements_are_invented():
    ext = TenderSourceExtractor()
    rows = ext.extract_requirement_candidates(
        _source("REQUISITOS\n1. Presentar documento obligatorio"),
        source_id="src-1", source_hash="abcdef123456", source_role="CONVOCATORIA", extraction_config={},
    )
    assert rows == []

def test_structured_reference_contains_document_location_and_mapping():
    ext = TenderSourceExtractor()
    src = ExtractedSource(
        "bases.pdf", "application/pdf", "REQUISITOS\n1. Presentar propuesta técnica",
        1, {"format": "pdf", "blocks": [{"text": "REQUISITOS", "page": 1, "line": 1}, {"text": "1. Presentar propuesta técnica", "page": 1, "line": 2}]},
    )
    cfg = {"source_roles": {"CONVOCATORIA": {"formats": {"PDF": {
        "headings": ["REQUISITOS"], "stop_headings": [],
        "item_pattern": r"^\s*\d+[.)]\s+(.+?)\s*$", "category": "TECNICA", "mandatory_default": None,
    }}}}}
    rows = ext.extract_requirement_candidates(src, source_id="src", source_hash="abcdef123456", source_role="CONVOCATORIA", extraction_config=cfg, format_code="PDF", flow_code="CARRETERAS", document_version="Rev2")
    ref = rows[0]["source_reference"]
    assert ref["document"] == "bases.pdf"
    assert ref["document_version"] == "Rev2"
    assert ref["page"] == 1
    assert ref["section"] == "REQUISITOS"
    assert ref["text_original"] == "1. Presentar propuesta técnica"
    assert rows[0]["mapping"]["dependency_code"] is None
    assert rows[0]["mapping"]["flow_code"] == "CARRETERAS"
    assert rows[0]["mapping"]["format_code"] == "PDF"
