"""Dependency/format/flow-specific deterministic source extraction configuration.

No normative rules are introduced here. These templates describe where to read
requirements from documents explicitly supplied by the user.
"""
from alembic import op
import json
import sqlalchemy as sa

revision = "20260914_dependency_specific_source_extraction"
down_revision = "20260914_requirement_source_extraction"
branch_labels = None
depends_on = None

BASE_ROLES = {
    "CONVOCATORIA": {"formats": ["pdf", "docx", "xlsx"], "headings": [
        "REQUISITOS", "REQUISITOS DE PARTICIPACIÓN", "REQUISITOS DE PARTICIPACION",
        "DOCUMENTACIÓN QUE DEBERÁ PRESENTAR EL LICITANTE", "DOCUMENTACION QUE DEBERA PRESENTAR EL LICITANTE",
        "DOCUMENTACIÓN LEGAL", "DOCUMENTACIÓN TÉCNICA", "DOCUMENTACIÓN ECONÓMICA",
        "DOCUMENTACION LEGAL", "DOCUMENTACION TECNICA", "DOCUMENTACION ECONOMICA",
    ]},
    "ANEXO": {"formats": ["pdf", "docx", "xlsx"], "headings": [
        "REQUISITOS", "DOCUMENTACIÓN", "DOCUMENTACION", "INSTRUCCIONES AL LICITANTE",
        "DATOS A PROPORCIONAR", "INFORMACIÓN A PRESENTAR", "INFORMACION A PRESENTAR",
    ]},
    "MODIFICACION": {"formats": ["pdf", "docx", "xlsx"], "headings": [
        "MODIFICACIONES", "CAMBIOS", "ANEXOS MODIFICADOS", "MODIFICACIONES A LA CONVOCATORIA",
        "ACLARACIÓN MODIFICATORIA", "ACLARACION MODIFICATORIA",
    ]},
    "JUNTA_ACLARACIONES": {"formats": ["pdf", "docx", "xlsx"], "headings": [
        "RESPUESTAS", "ACUERDOS", "ACLARACIONES", "MODIFICACIONES A LAS BASES",
        "PREGUNTAS Y RESPUESTAS", "RESPUESTA DE LA CONVOCANTE",
    ]},
}

# Format-specific deterministic item rules. These are extraction maps, not legal rules.
FORMAT_RULES = {
    "pdf": {"item_pattern": r"^\s*(?:[-•*]|\d+[.)]|[A-Za-z][.)])\s+(.+?)\s*$", "category": "ADMINISTRATIVO"},
    "docx": {"item_pattern": r"^\s*(?:[-•*]|\d+[.)]|[A-Za-z][.)])\s+(.+?)\s*$", "category": "ADMINISTRATIVO"},
    "xlsx": {"item_pattern": r"^\s*(?:[-•*]|\d+[.)]|[A-Za-z][.)])\s+(.+?)\s*$", "category": "PRESENTACION"},
}

PROFILES = {
    "MX-FED-CONAGUA-OBRA": {"dependency_code": "CONAGUA", "flows": ["OBRA_HIDRAULICA", "PTAR", "OBRA_PUBLICA"]},
    "MX-FED-SICT-OBRA": {"dependency_code": "SICT", "flows": ["CARRETERAS", "COMUNICACIONES", "OBRA_PUBLICA"]},
    "MX-FED-CFE-OBRA": {"dependency_code": "CFE", "flows": ["OBRA_ELECTRICA", "OBRA_PUBLICA"]},
    "MX-FED-OBRA": {"dependency_code": "FEDERAL", "flows": ["OBRA_PUBLICA", "CARRETERAS", "INFRAESTRUCTURA_ESCOLAR"]},
    "MX-LOCAL-STATE-OBRA": {"dependency_code": "ESTATAL", "flows": ["OBRA_PUBLICA", "INFRAESTRUCTURA_ESCOLAR"]},
    "MX-LOCAL-MUNICIPAL-OBRA": {"dependency_code": "MUNICIPAL", "flows": ["OBRA_PUBLICA", "INFRAESTRUCTURA_ESCOLAR"]},
    "MX-FED-ADQ": {"dependency_code": "FEDERAL_ADQUISICIONES", "flows": ["ADQUISICIONES", "SERVICIOS"]},
    "MX-PRIVATE-OBRA": {"dependency_code": "PRIVADA", "flows": ["OBRA_PRIVADA", "REMODELACION", "CONSTRUCCION"]},
}


def _config(profile):
    roles = {}
    for role, base in BASE_ROLES.items():
        role_obj = {"formats": {}}
        for fmt in base["formats"]:
            rule = dict(FORMAT_RULES[fmt])
            role_obj["formats"][fmt] = {
                **rule,
                "headings": list(base["headings"]),
                "stop_headings": ["ANEXOS", "TRANSITORIOS", "FIRMAS", "NOTAS", "FIN DE LA SECCIÓN", "FIN DE LA SECCION"],
                "mandatory_default": None,
            }
        roles[role] = role_obj
    return {
        "engine": "MECHANICAL_DETERMINISTIC",
        "ai": False,
        "dependency_code": profile["dependency_code"],
        "flow_codes": profile["flows"],
        "required_source_roles": ["CONVOCATORIA"],
        "optional_source_roles": ["ANEXO", "JUNTA_ACLARACIONES", "MODIFICACION"],
        "source_roles": roles,
        "document_version_pattern": r"(?:versi[oó]n|version|rev(?:isi[oó]n)?|revision)\s*[:#-]?\s*([A-Za-z0-9._-]+)",
        "mapping_policy": "SOURCE_TEXT_ONLY",
    }


def upgrade() -> None:
    conn = op.get_bind()
    for code, profile in PROFILES.items():
        payload = json.dumps(_config(profile), ensure_ascii=False)
        # Create the private product profile if it does not exist; it is a flow
        # profile, not a legal corpus assertion.
        if code == "MX-PRIVATE-OBRA":
            conn.execute(sa.text("""
                INSERT INTO jurisdiction_profiles
                (id, created_at, updated_at, tenant_id, code, authority, government_level, matter,
                 portal_code, profile_version, ruleset, templates, active)
                SELECT gen_random_uuid(), now(), now(), NULL, CAST(:code AS varchar(120)), 'PRIVADA', 'PRIVATE', 'PRIVATE_WORKS',
                       'INTERNAL', 1, '{}'::jsonb, '{}'::jsonb, true
                WHERE NOT EXISTS (SELECT 1 FROM jurisdiction_profiles WHERE tenant_id IS NULL AND code=CAST(:code AS varchar(120)))
            """), {"code": code})
        conn.execute(sa.text("""
            UPDATE jurisdiction_profiles
               SET templates = jsonb_set(COALESCE(templates, '{}'::jsonb), '{requirement_extraction}', CAST(:payload AS jsonb), true)
             WHERE active = true AND code = :code AND tenant_id IS NULL
        """).bindparams(payload=payload, code=code))


def downgrade() -> None:
    conn = op.get_bind()
    for code in PROFILES:
        conn.execute(sa.text("""
            UPDATE jurisdiction_profiles
               SET templates = templates - 'requirement_extraction'
             WHERE tenant_id IS NULL AND code=:code
        """), {"code": code})
