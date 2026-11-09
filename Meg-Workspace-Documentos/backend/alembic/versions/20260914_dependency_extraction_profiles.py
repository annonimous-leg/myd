"""Refine source extraction by dependency, official format and engineering flow.

This migration only changes deterministic extraction maps. It does not encode legal
requirements and cannot create TenderRequirement rows by itself.
"""
from alembic import op
import json
import sqlalchemy as sa

revision = "20260914_dependency_extraction_profiles"
down_revision = "20260914_dependency_specific_source_extraction"
branch_labels = None
depends_on = None

COMMON_STOP = ["ANEXOS", "TRANSITORIOS", "FIRMAS", "NOTAS", "FIN DE LA SECCIÓN", "FIN DE LA SECCION"]
BASE = {
    "CONVOCATORIA": {
        "pdf": ["REQUISITOS", "REQUISITOS DE PARTICIPACIÓN", "DOCUMENTACIÓN QUE DEBERÁ PRESENTAR EL LICITANTE", "DOCUMENTACIÓN DE LA PROPOSICIÓN"],
        "docx": ["REQUISITOS", "DOCUMENTACIÓN QUE DEBERÁ PRESENTAR EL LICITANTE"],
        "xlsx": ["REQUISITOS", "DOCUMENTACIÓN", "FORMATO", "DATOS A PROPORCIONAR"],
    },
    "ANEXO": {
        "pdf": ["REQUISITOS", "DOCUMENTACIÓN", "INSTRUCCIONES AL LICITANTE", "DATOS A PROPORCIONAR"],
        "docx": ["REQUISITOS", "DOCUMENTACIÓN", "INSTRUCCIONES AL LICITANTE"],
        "xlsx": ["REQUISITOS", "FORMATO", "DATOS A PROPORCIONAR", "CAMPOS"],
    },
    "MODIFICACION": {
        "pdf": ["MODIFICACIONES", "CAMBIOS", "ANEXOS MODIFICADOS", "MODIFICACIONES A LA CONVOCATORIA"],
        "docx": ["MODIFICACIONES", "CAMBIOS", "ANEXOS MODIFICADOS"],
        "xlsx": ["MODIFICACIONES", "CAMBIOS", "CAMPOS MODIFICADOS"],
    },
    "JUNTA_ACLARACIONES": {
        "pdf": ["RESPUESTAS", "ACUERDOS", "ACLARACIONES", "MODIFICACIONES A LAS BASES", "PREGUNTAS Y RESPUESTAS"],
        "docx": ["RESPUESTAS", "ACUERDOS", "ACLARACIONES", "PREGUNTAS Y RESPUESTAS"],
        "xlsx": ["RESPUESTAS", "ACUERDOS", "PREGUNTAS", "RESPUESTA DE LA CONVOCANTE"],
    },
}

DEPENDENCY = {
    "MX-FED-CONAGUA-OBRA": {
        "dependency_code": "CONAGUA",
        "flow_codes": ["OBRA_HIDRAULICA", "PTAR"],
        "format_codes": ["AE-01", "AE-02", "AE-03", "AE-05", "AE-06", "AE-07", "AT-02"],
        "extra": ["DOCUMENTACIÓN DE LA PROPOSICIÓN TÉCNICA", "DOCUMENTACIÓN DE LA PROPOSICIÓN ECONÓMICA", "ANEXOS AT", "ANEXOS AE"],
    },
    "MX-FED-SICT-OBRA": {
        "dependency_code": "SICT",
        "flow_codes": ["CARRETERAS", "COMUNICACIONES"],
        "format_codes": ["FORMATO_12", "FORMA_E-7", "FORMATO_13", "FORMATO_14", "FORMATO_15", "FORMATO_17", "FORMATO_07"],
        "extra": ["DOCUMENTACIÓN DE LA PROPOSICIÓN", "FORMATOS DE LA PROPOSICIÓN", "CATÁLOGO DE CONCEPTOS", "PROGRAMA DE EJECUCIÓN"],
    },
    "MX-FED-CFE-OBRA": {
        "dependency_code": "CFE",
        "flow_codes": ["OBRA_ELECTRICA"],
        "format_codes": ["CFE_DCPROTER", "OFERTA_TECNICA", "OFERTA_ECONOMICA"],
        "extra": ["DOCUMENTACIÓN DE LA OFERTA", "REQUISITOS TÉCNICOS CFE", "FORMATOS CFE", "ANEXOS CFE"],
    },
    "MX-FED-OBRA": {
        "dependency_code": "FEDERAL",
        "flow_codes": ["OBRA_PUBLICA", "INFRAESTRUCTURA_ESCOLAR", "CARRETERAS"],
        "format_codes": ["ECO.1", "ECO.2", "ECO.3"],
        "extra": ["DOCUMENTACIÓN DE LA PROPOSICIÓN", "DOCUMENTACIÓN LEGAL", "DOCUMENTACIÓN TÉCNICA", "DOCUMENTACIÓN ECONÓMICA"],
    },
    "MX-LOCAL-STATE-OBRA": {
        "dependency_code": "ESTATAL",
        "flow_codes": ["OBRA_PUBLICA", "INFRAESTRUCTURA_ESCOLAR"],
        "format_codes": ["PE_09", "PE_13"],
        "extra": ["DOCUMENTACIÓN DE LA PROPUESTA", "FORMATOS ESTATALES"],
    },
    "MX-LOCAL-MUNICIPAL-OBRA": {
        "dependency_code": "MUNICIPAL",
        "flow_codes": ["OBRA_PUBLICA", "INFRAESTRUCTURA_ESCOLAR"],
        "format_codes": [],
        "extra": ["DOCUMENTACIÓN DE LA PROPUESTA", "FORMATOS MUNICIPALES"],
    },
    "MX-FED-ADQ": {
        "dependency_code": "FEDERAL_ADQUISICIONES",
        "flow_codes": ["ADQUISICIONES", "SERVICIOS"],
        "format_codes": ["FORMATO_8", "FORMATO_9"],
        "extra": ["PROPUESTA TÉCNICA", "PROPUESTA ECONÓMICA", "DOCUMENTACIÓN DEL PROVEEDOR"],
    },
    "MX-PRIVATE-OBRA": {
        "dependency_code": "PRIVADA",
        "flow_codes": ["OBRA_PRIVADA", "REMODELACION", "CONSTRUCCION"],
        "format_codes": [],
        "extra": ["ALCANCE DE LOS TRABAJOS", "ESPECIFICACIONES", "ENTREGABLES", "CRITERIOS DE ACEPTACIÓN"],
    },
}

ITEM = {
    "pdf": r"^\s*(?:[-•*]|\d+[.)]|[A-Za-z][.)])\s+(.+?)\s*$",
    "docx": r"^\s*(?:[-•*]|\d+[.)]|[A-Za-z][.)])\s+(.+?)\s*$",
    "xlsx": r"^\s*(?:[-•*]|\d+[.)]|[A-Za-z][.)])\s+(.+?)\s*$",
}


def build(dep):
    roles = {}
    for role, formats in BASE.items():
        role_cfg = {"formats": {}}
        for physical, headings in formats.items():
            role_cfg["formats"][physical] = {
                "headings": headings + dep["extra"],
                "stop_headings": COMMON_STOP,
                "item_pattern": ITEM[physical],
                "category": "PRESENTACION" if physical == "xlsx" else "ADMINISTRATIVO",
                "mandatory_default": None,
            }
        roles[role] = role_cfg
    return {
        "engine": "MECHANICAL_DETERMINISTIC",
        "ai": False,
        "dependency_code": dep["dependency_code"],
        "flow_codes": dep["flow_codes"],
        "format_codes": dep["format_codes"],
        "required_source_roles": ["CONVOCATORIA"],
        "optional_source_roles": ["ANEXO", "JUNTA_ACLARACIONES", "MODIFICACION"],
        "source_roles": roles,
        "document_version_pattern": r"(?:versi[oó]n|version|rev(?:isi[oó]n)?|revision)\s*[:#-]?\s*([A-Za-z0-9._-]+)",
        "mapping_policy": "SOURCE_TEXT_ONLY",
        "normative_engine_allowed": False,
        "notes": "Los perfiles y formatos determinan cómo localizar texto del documento suministrado; no determinan obligaciones.",
    }


def upgrade():
    conn = op.get_bind()
    for code, dep in DEPENDENCY.items():
        payload = json.dumps(build(dep), ensure_ascii=False)
        conn.execute(sa.text("""
            UPDATE jurisdiction_profiles
               SET templates = jsonb_set(COALESCE(templates, '{}'::jsonb), '{requirement_extraction}', CAST(:payload AS jsonb), true)
             WHERE tenant_id IS NULL AND active = true AND code = :code
        """).bindparams(payload=payload, code=code))


def downgrade():
    # Revert to the previous dependency-agnostic source extraction map.
    conn = op.get_bind()
    for code in DEPENDENCY:
        conn.execute(sa.text("""
            UPDATE jurisdiction_profiles
               SET templates = templates - 'requirement_extraction'
             WHERE tenant_id IS NULL AND code=:code
        """), {"code": code})
