from app.engines.procurement.source_extract import TenderSourceExtractor, ExtractedSource


def cfg():
    return {
        "dependency_code": "CONAGUA",
        "source_roles": {
            "CONVOCATORIA": {"formats": {"DOCX": {
                "sections": [{"headings": ["REQUISITOS DE PARTICIPACIÓN"], "item_pattern": r"^\s*(?P<id>R-\d+)\s*[-:]\s*(?P<description>.+)$", "category": "TECNICA"}],
                "table_rules": [{"id_headers": ["clave"], "description_headers": ["descripción"], "mandatory_headers": ["obligatorio"]},]
            }}}
        }
    }


def test_section_extraction_preserves_official_identifier_and_location():
    e = ExtractedSource("bases.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "", None, {"format": "docx", "blocks": [
        {"text": "REQUISITOS DE PARTICIPACIÓN", "line": 10, "field": "docx_paragraph"},
        {"text": "R-01 - Presentar programa de trabajo", "line": 11, "field": "docx_paragraph"},
    ]})
    out = TenderSourceExtractor().extract_requirement_candidates(e, source_id="s", source_hash="a"*64, source_role="CONVOCATORIA", extraction_config=cfg(), format_code="DOCX", flow_code="PTAR", dependency_code="CONAGUA", document_version="2", source_revision=7)
    assert out[0]["code"] == "R-01"
    assert out[0]["source_reference"]["line_start"] == 11
    assert out[0]["source_reference"]["document_version"] == "2"
    assert out[0]["mandatory"] is None


def test_table_extraction_maps_id_description_mandatory_and_coordinates():
    e = ExtractedSource("formato.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "", None, {"format": "docx", "blocks": [
        {"text": "Clave", "table": 2, "row": 1, "cell": 1, "line": 1},
        {"text": "Descripción", "table": 2, "row": 1, "cell": 2, "line": 2},
        {"text": "Obligatorio", "table": 2, "row": 1, "cell": 3, "line": 3},
        {"text": "R-02", "table": 2, "row": 2, "cell": 1, "line": 4},
        {"text": "Presentar experiencia", "table": 2, "row": 2, "cell": 2, "line": 5},
        {"text": "Sí", "table": 2, "row": 2, "cell": 3, "line": 6},
    ]})
    out = TenderSourceExtractor().extract_requirement_candidates(e, source_id="s", source_hash="b"*64, source_role="CONVOCATORIA", extraction_config=cfg(), format_code="DOCX", flow_code="PTAR", dependency_code="CONAGUA")
    assert any(x["code"] == "R-02" and x["mandatory"] is True and x["source_reference"]["table"] == 2 and x["source_reference"]["row"] == 2 for x in out)


def test_relations_require_explicit_target_and_never_infer_target():
    e = ExtractedSource("aclaracion.pdf", "application/pdf", "", 1, {"format": "pdf", "blocks": [
        {"text": "Se modifica R-02: nueva condición", "page": 4, "line": 20},
        {"text": "Se modifica el calendario por ajuste de fechas", "page": 5, "line": 30},
    ]})
    out = TenderSourceExtractor().extract_source_relations(e, source_id="s", source_hash="c"*64, source_role="ACLARACION", dependency_code="CONAGUA", flow_code="PTAR", document_version="3", source_revision=8)
    assert out[0]["relation_type"] == "MODIFICA" and out[0]["resolved"] is True and out[0]["target_identifier"] == "R-02"
    assert out[1]["relation_type"] == "MODIFICA" and out[1]["resolved"] is False
