"""Add deterministic table/field and source-relation extraction contracts.

No legal requirements are defined here. The configuration tells the extractor how to
read structures that exist in documents supplied by the client.
"""
from alembic import op
import json
import sqlalchemy as sa

revision = "20260914_structural_source_tables_relations"
down_revision = "20260914_dependency_extraction_profiles"
branch_labels = None
depends_on = None

TABLE_RULES = [
    {
        "id_headers": ["requisito", "id", "clave", "codigo", "código", "formato", "anexo"],
        "description_headers": ["descripcion", "descripción", "requisito", "documento a presentar", "documentación", "documentacion", "campo", "concepto"],
        "mandatory_headers": ["obligatorio", "obligatoria", "requerido", "requerida", "mandatory"],
        "category": "PRESENTACION",
    }
]

RELATIONS = [
    {"code": "MODIFICA", "patterns": [r"\bse\s+modifica\b", r"\bmodificaci[oó]n\b"], "requires_explicit_target": True},
    {"code": "SUSTITUYE", "patterns": [r"\bse\s+sustituye\b", r"\ben\s+sustituci[oó]n\s+de\b"], "requires_explicit_target": True},
    {"code": "ACLARA", "patterns": [r"\bse\s+aclara\b", r"\baclaraci[oó]n\b", r"\bprecisa\b"], "requires_explicit_target": True},
]


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE jurisdiction_profiles
           SET templates = jsonb_set(
             jsonb_set(
               jsonb_set(COALESCE(templates, '{}'::jsonb), '{requirement_extraction,table_rules}', CAST(:tables AS jsonb), true),
               '{requirement_extraction,relations}', CAST(:relations AS jsonb), true
             ),
             '{requirement_extraction,structural_trace}', 'true'::jsonb, true
           )
         WHERE tenant_id IS NULL AND active = true
           AND code IN (
             'MX-FED-CONAGUA-OBRA','MX-FED-SICT-OBRA','MX-FED-CFE-OBRA','MX-FED-OBRA',
             'MX-LOCAL-STATE-OBRA','MX-LOCAL-MUNICIPAL-OBRA','MX-FED-ADQ','MX-PRIVATE-OBRA'
           )
    """).bindparams(
        tables=json.dumps(TABLE_RULES, ensure_ascii=False),
        relations=json.dumps(RELATIONS, ensure_ascii=False),
    ))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE jurisdiction_profiles
           SET templates = templates #- '{requirement_extraction,table_rules}'
         WHERE tenant_id IS NULL AND active = true
           AND code IN (
             'MX-FED-CONAGUA-OBRA','MX-FED-SICT-OBRA','MX-FED-CFE-OBRA','MX-FED-OBRA',
             'MX-LOCAL-STATE-OBRA','MX-LOCAL-MUNICIPAL-OBRA','MX-FED-ADQ','MX-PRIVATE-OBRA'
           )
    """))
