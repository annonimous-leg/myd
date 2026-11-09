from pathlib import Path

BASE = Path(__file__).resolve().parents[1]

def test_procurement_has_catalog_endpoint():
    text=(BASE/"app/api/v1/procurement.py").read_text()
    assert '"/catalog"' in text

def test_tender_create_requires_jurisdiction_and_evaluation_field():
    text=(BASE/"app/schemas/procurement/schemas.py").read_text()
    assert 'evaluation_criterion: str | None = None' in text
    assert 'jurisdiction_code: str = Field(min_length=1, max_length=120)' in text

def test_legal_article_model_present():
    text=(BASE/"app/models/procurement.py").read_text()
    assert 'class LegalArticle' in text
    assert 'article_id:' in text
