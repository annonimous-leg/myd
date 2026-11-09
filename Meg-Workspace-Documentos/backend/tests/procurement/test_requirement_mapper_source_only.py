from app.engines.procurement.requirements import ProcurementRequirementMapper


def test_requirement_mapper_accepts_only_extracted_tender_candidates():
    mapper = ProcurementRequirementMapper()
    rows = mapper.derive(
        tender_id="tender",
        source_texts=[{
            "source_id": "doc-1",
            "source_hash": "abc",
            "requirements": [{
                "code": "AT-01",
                "category": "TECNICO",
                "description": "Presentar programa de trabajo",
                "mandatory": True,
                "source_reference": {"page": 4, "section": "AT-01"},
                "artifact_required": ["AT-01"],
            }],
        }],
    )
    assert len(rows) == 1
    assert rows[0].source_reference["authority"] == "TENDER_SOURCE"
    assert rows[0].source_reference["page"] == 4


def test_requirement_mapper_does_not_turn_legal_words_into_requirements():
    mapper = ProcurementRequirementMapper()
    assert mapper.derive(tender_id="tender", source_texts=[{"text": "Es obligatorio presentar garantía."}]) == []
