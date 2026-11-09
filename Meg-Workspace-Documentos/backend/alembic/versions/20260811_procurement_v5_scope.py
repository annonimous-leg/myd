"""Procurement domain scope, contract variants and entity/case packs."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import text
from uuid import uuid4
import json

revision = "20260811_procurement_v5_scope"
down_revision = "20260811_procurement_catalog"
branch_labels = None
depends_on = None
UUID = postgresql.UUID(as_uuid=True)


def _get_source(conn, citation: str):
    return conn.execute(text("SELECT id FROM legal_sources WHERE citation=:c AND tenant_id IS NULL LIMIT 1"), {"c": citation}).scalar()


def _get_article(conn, source_id, code: str):
    return conn.execute(text("SELECT id FROM legal_articles WHERE source_id=:s AND article_code=:c LIMIT 1"), {"s": source_id, "c": code}).scalar()


def _insert_profile(conn, code, authority, level, matter, ruleset):
    conn.execute(text("""
        INSERT INTO jurisdiction_profiles
        (id, created_at, updated_at, tenant_id, code, authority, government_level, matter,
         portal_code, profile_version, ruleset, templates, active)
        VALUES (:id, now(), now(), NULL, :code, :authority, :level, :matter, :portal, 1,
                CAST(:rules AS jsonb), '{}'::jsonb, true)
        ON CONFLICT DO NOTHING
    """), {
        "id": str(uuid4()), "code": code, "authority": authority, "level": level,
        "matter": matter, "portal": "COMPRAS_MX", "rules": json.dumps(ruleset),
    })


def _insert_case_rule(conn, rule_id, jurisdiction, article_source, article_code, condition, requirement, validation, domain="PUBLIC_WORKS"):
    sid = _get_source(conn, article_source)
    if sid is None:
        raise RuntimeError(f"No existe fuente jurídica global: {article_source}")
    aid = _get_article(conn, sid, article_code)
    if aid is None:
        raise RuntimeError(f"No existe artículo {article_source} {article_code}")
    conn.execute(text("""
        INSERT INTO legal_rules
        (id, created_at, updated_at, tenant_id, rule_id, jurisdiction_code, domain,
         procedure_type, source_id, article_id, source_version, condition, requirement,
         validation, severity, rule_version, active)
        VALUES (:id, now(), now(), NULL, :rule_id, :jurisdiction, :domain, NULL, :sid, :aid,
                'guide-2026-08-11', CAST(:condition AS jsonb), CAST(:requirement AS jsonb),
                CAST(:validation AS jsonb), 'BLOCKER', 1, true)
        ON CONFLICT DO NOTHING
    """), {
        "id": str(uuid4()), "rule_id": rule_id, "jurisdiction": jurisdiction, "domain": domain,
        "sid": sid, "aid": aid, "condition": json.dumps(condition),
        "requirement": json.dumps(requirement), "validation": json.dumps(validation),
    })


def upgrade():
    op.add_column("tender_packages", sa.Column("evaluation_criterion", sa.String(80), nullable=True))
    op.add_column("tender_packages", sa.Column("project_type", sa.String(80), nullable=True))
    op.add_column("tender_packages", sa.Column("scope_scale", sa.String(40), nullable=True))
    op.add_column("tender_packages", sa.Column("case_pack_code", sa.String(120), nullable=True))
    op.create_index("idx_tender_packages_project_type", "tender_packages", ["tenant_id", "project_type"])
    op.create_index("idx_tender_packages_case_pack", "tender_packages", ["tenant_id", "case_pack_code"])

    conn = op.get_bind()
    _insert_profile(conn, "MX-FED-CFE-OBRA", "CFE", "FEDERAL", "PUBLIC_WORKS", {
        "regime_family": "LOPSRM+ENTITY_RULES",
        "selection_label": "CFE — Obra eléctrica",
        "allowed_procedures": ["LICITACION_PUBLICA", "INVITACION", "ADJUDICACION"],
        "allowed_contract_types": ["UNIT_PRICES", "LUMP_SUM", "MIXED"],
        "allowed_evaluation_criteria": ["BINARY", "POINTS_PERCENTAGES"],
        "legal_sources": ["LOPSRM", "RLOPSRM"], "portal_code": "COMPRAS_MX",
        "inherits_from": ["MX-FED-OBRA"], "requires_official_entity_pack": True,
        "case_packs": ["CFE_DCPROTER"],
    })
    _insert_profile(conn, "MX-FED-PEMEX-OBRA", "PEMEX", "FEDERAL", "PUBLIC_WORKS", {
        "regime_family": "ENTITY_SPECIFIC", "selection_label": "PEMEX — Obra / régimen especial",
        "allowed_procedures": [], "allowed_contract_types": ["UNIT_PRICES", "LUMP_SUM", "MIXED"],
        "allowed_evaluation_criteria": ["BINARY", "POINTS_PERCENTAGES"], "legal_sources": [],
        "requires_official_entity_pack": True,
    })
    _insert_profile(conn, "MX-FED-SECRETARIAS-OBRA", "Secretaría / dependencia federal — obra", "FEDERAL", "PUBLIC_WORKS", {
        "regime_family": "LOPSRM", "selection_label": "Dependencia federal — obra pública",
        "allowed_procedures": ["LICITACION_PUBLICA", "INVITACION", "ADJUDICACION"],
        "allowed_contract_types": ["UNIT_PRICES", "LUMP_SUM", "MIXED"],
        "allowed_evaluation_criteria": ["BINARY", "POINTS_PERCENTAGES"],
        "legal_sources": ["LOPSRM", "RLOPSRM"], "portal_code": "COMPRAS_MX",
        "inherits_from": ["MX-FED-OBRA"],
    })

    for code, name, level in [
        ("MX-LOCAL-STATE-OBRA", "Entidad federativa — perfil a configurar", "ESTATAL"),
        ("MX-LOCAL-MUNICIPAL-OBRA", "Municipio/alcaldía — perfil a configurar", "MUNICIPAL"),
    ]:
        _insert_profile(conn, code, name, level, "PUBLIC_WORKS", {
            "regime_family": f"{level}_SPECIFIC",
            "selection_label": f"{name} — cargar ley, reglamento, lineamientos y fuentes oficiales",
            "allowed_procedures": [], "allowed_contract_types": ["UNIT_PRICES", "LUMP_SUM", "MIXED"],
            "allowed_evaluation_criteria": ["BINARY", "POINTS_PERCENTAGES"], "legal_sources": [],
            "requires_official_entity_pack": True,
        })

    # The guide's case structures are requirements activated only by an explicit case pack.
    for i in range(1, 14):
        _insert_case_rule(
            conn, f"CONAGUA-PTAR-AT-{i:02d}", "MX-FED-CONAGUA-OBRA", "LOPSRM", "31-35",
            {"conditions": [{"field": "case_pack_code", "op": "eq", "val": "REFERENCE_CONAGUA_PTAR_2026"}]},
            {"code": f"AT-{i:02d}", "category": "TECNICO", "description": f"Anexo técnico AT-{i:02d} del caso CONAGUA/PTAR de aceptación.",
             "mandatory": True, "artifact_required": [f"AT-{i:02d}"], "source_marker": f"AT-{i}"},
            {"type": "required_artifact", "artifact": f"AT-{i:02d}"},
        )
    for i in range(1, 13):
        _insert_case_rule(
            conn, f"CONAGUA-PTAR-AE-{i:02d}", "MX-FED-CONAGUA-OBRA", "RLOPSRM", "58-68",
            {"conditions": [{"field": "case_pack_code", "op": "eq", "val": "REFERENCE_CONAGUA_PTAR_2026"}]},
            {"code": f"AE-{i:02d}", "category": "ECONOMICO", "description": f"Anexo económico AE-{i:02d} del caso CONAGUA/PTAR de aceptación.",
             "mandatory": True, "artifact_required": [f"AE-{i:02d}"], "source_marker": f"AE-{i}"},
            {"type": "required_artifact", "artifact": f"AE-{i:02d}"},
        )

    # Apply case-pack metadata to global entity profiles without overwriting tenant-owned profiles.
    conn.execute(text("""
        UPDATE jurisdiction_profiles
        SET ruleset = jsonb_set(ruleset, '{case_packs}',
            CASE code
                WHEN 'MX-FED-CONAGUA-OBRA' THEN '["REFERENCE_CONAGUA_PTAR_2026"]'::jsonb
                WHEN 'MX-FED-SICT-OBRA' THEN '["SICT_DT_2026"]'::jsonb
                WHEN 'MX-FED-CFE-OBRA' THEN '["CFE_DCPROTER"]'::jsonb
                ELSE COALESCE(ruleset->'case_packs', '[]'::jsonb)
            END,
            true)
        WHERE tenant_id IS NULL
    """))


def downgrade():
    for idx in ("idx_tender_packages_case_pack", "idx_tender_packages_project_type"):
        op.drop_index(idx, table_name="tender_packages")
    for col in ("case_pack_code", "scope_scale", "project_type", "evaluation_criterion"):
        op.drop_column("tender_packages", col)
