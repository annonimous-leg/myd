"""Configure source-grounded requirement extraction per jurisdiction/profile.

Revision ID: 20260914_requirement_source_extraction
Revises: 20260914_tenant_ownership_budget_schedule
"""
from alembic import op
import json
import sqlalchemy as sa

revision = "20260914_requirement_source_extraction"
down_revision = "20260914_tenant_ownership_budget_schedule"
branch_labels = None
depends_on = None

CONFIG = {
    "source_roles": {
        "CONVOCATORIA": {
            "headings": [
                "REQUISITOS", "REQUISITOS DE PARTICIPACIÓN",
                "REQUISITOS DE PARTICIPACION",
                "DOCUMENTACIÓN QUE DEBERÁ PRESENTAR EL LICITANTE",
                "DOCUMENTACION QUE DEBERA PRESENTAR EL LICITANTE",
                "DOCUMENTACIÓN LEGAL", "DOCUMENTACIÓN TÉCNICA",
                "DOCUMENTACIÓN ECONÓMICA",
            ],
            "stop_headings": ["ANEXOS", "TRANSITORIOS", "FIRMAS", "NOTAS"],
            "item_pattern": r"^\s*(?:[-•*]|\d+[.)]|[A-Za-z][.)])\s+(.+?)\s*$",
            "category": "ADMINISTRATIVO",
            "mandatory_default": None,
        },
        "JUNTA_ACLARACIONES": {
            "headings": ["RESPUESTAS", "ACUERDOS", "ACLARACIONES", "MODIFICACIONES A LAS BASES", "PREGUNTAS Y RESPUESTAS"],
            "stop_headings": ["FIRMAS", "ANEXOS", "NOTAS"],
            "item_pattern": r"^\s*(?:[-•*]|\d+[.)]|[A-Za-z][.)])\s+(.+?)\s*$",
            "category": "ADMINISTRATIVO",
            "mandatory_default": None,
        },
        "MODIFICACION": {
            "headings": ["MODIFICACIONES", "CAMBIOS", "ANEXOS MODIFICADOS", "MODIFICACIONES A LA CONVOCATORIA"],
            "stop_headings": ["FIRMAS", "NOTAS"],
            "item_pattern": r"^\s*(?:[-•*]|\d+[.)]|[A-Za-z][.)])\s+(.+?)\s*$",
            "category": "ADMINISTRATIVO",
            "mandatory_default": None,
        },
        "ANEXO": {
            "headings": ["REQUISITOS", "DOCUMENTACIÓN", "DOCUMENTACION", "INSTRUCCIONES AL LICITANTE"],
            "stop_headings": ["FIRMAS", "NOTAS"],
            "item_pattern": r"^\s*(?:[-•*]|\d+[.)]|[A-Za-z][.)])\s+(.+?)\s*$",
            "category": "PRESENTACION",
            "mandatory_default": None,
        },
    }
}

def upgrade() -> None:
    payload = json.dumps({"source_roles": CONFIG["source_roles"]}, ensure_ascii=False)
    op.execute(sa.text("""
        UPDATE jurisdiction_profiles
           SET templates = jsonb_set(COALESCE(templates, '{}'::jsonb), '{requirement_extraction}', CAST(:payload AS jsonb), true)
         WHERE active = true
           AND code IN ('MX-FED-OBRA','MX-FED-CONAGUA-OBRA','MX-FED-SICT-OBRA','MX-LOCAL-STATE-OBRA','MX-FED-ADQ')
           AND COALESCE(templates->'requirement_extraction', '{}'::jsonb) IN ('{}'::jsonb, 'null'::jsonb)
    """).bindparams(payload=payload))

def downgrade() -> None:
    op.execute(sa.text("""
        UPDATE jurisdiction_profiles
           SET templates = templates - 'requirement_extraction'
         WHERE active = true
           AND code IN ('MX-FED-OBRA','MX-FED-CONAGUA-OBRA','MX-FED-SICT-OBRA','MX-LOCAL-STATE-OBRA','MX-FED-ADQ')
    """))
