"""Strengthen procurement jurisdiction selection, funding and current legal article bindings."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import text

revision = "20260811_procurement_v6_jurisdiction_funding"
down_revision = "20260811_procurement_v5_scope"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tender_packages", sa.Column("funding_source", sa.String(40), nullable=True))
    op.add_column("tender_packages", sa.Column("object_class", sa.String(40), nullable=True))
    op.add_column("tender_packages", sa.Column("legal_regime", sa.String(80), nullable=True))
    op.create_index("idx_tender_packages_funding", "tender_packages", ["tenant_id", "funding_source"])
    op.create_index("idx_tender_packages_regime", "tender_packages", ["tenant_id", "legal_regime"])

    conn = op.get_bind()
    # Create an exact current-law article node for the 14-11-2025 LOPSRM text.
    conn.execute(text("""
        INSERT INTO legal_articles (id, created_at, updated_at, source_id, article_code, title, summary, status)
        SELECT gen_random_uuid(), now(), now(), s.id, '45', 'Condiciones de pago y tipos de contrato',
               'Precios unitarios, precio alzado y contratos mixtos conforme al texto vigente.', 'ACTIVE'
          FROM legal_sources s
         WHERE s.citation = 'LOPSRM' AND s.tenant_id IS NULL
           AND NOT EXISTS (SELECT 1 FROM legal_articles a WHERE a.source_id=s.id AND a.article_code='45')
    """))
    # Preserve the legacy rule as historical data; deactivate it so only the current rule is executable.
    conn.execute(text("""
        UPDATE legal_rules
           SET active = false
         WHERE rule_id = 'LOPSRM-TYPE-46'
           AND tenant_id IS NULL
    """))
    # Create a versioned replacement rule so historical versions remain immutable.
    conn.execute(text("""
        INSERT INTO legal_rules
        (id, created_at, updated_at, tenant_id, rule_id, jurisdiction_code, domain, procedure_type, source_id, article_id, source_version, condition, requirement, validation, severity, rule_version, active)
        SELECT gen_random_uuid(), now(), now(), NULL, 'LOPSRM-CONTRACT-TYPE-45-2025', 'MX-FED-OBRA', 'PUBLIC_WORKS', NULL, r.source_id, a45.id, 'LOPSRM-DOF-2025-11-14',
               '{"conditions":[{"field":"contract_type","op":"in","val":["UNIT_PRICES","LUMP_SUM","MIXED"]}]}'::jsonb,
               '{"code":"CONTRACT_TYPE","category":"LEGAL","description":"El tipo de contrato debe corresponder a una modalidad de pago permitida por el artículo 45 vigente y estar sustentado por las bases."}'::jsonb,
               '{"type":"enum","field":"contract_type","values":["UNIT_PRICES","LUMP_SUM","MIXED"]}'::jsonb,
               'BLOCKER', 1, true
          FROM legal_sources rsrc
          JOIN legal_articles a45 ON a45.source_id = rsrc.id AND a45.article_code = '45'
          JOIN legal_rules r ON r.source_id = rsrc.id AND r.rule_id = 'LOPSRM-TYPE-46' AND r.tenant_id IS NULL
         WHERE NOT EXISTS (SELECT 1 FROM legal_rules x WHERE x.rule_id='LOPSRM-CONTRACT-TYPE-45-2025' AND x.tenant_id IS NULL AND x.rule_version=1)
    """))

    # Case-pack artifacts are derived from the tender/case source, not falsely attributed
    # to an entire statutory article range. Their legal requirements remain separately
    # governed by the generic RuleSet and the particular tender bases.
    conn.execute(text("""
        UPDATE legal_rules
           SET article_id = NULL, source_id = NULL, source_version = 'GUIDE-CASE-2026-08-11'
         WHERE tenant_id IS NULL
           AND (rule_id LIKE 'CONAGUA-PTAR-AT-%' OR rule_id LIKE 'CONAGUA-PTAR-AE-%')
    """))

    # Explicitly classify the regime allowed by the jurisdiction profile.
    conn.execute(text("""
        UPDATE jurisdiction_profiles
           SET ruleset = ruleset || jsonb_build_object(
             'allowed_funding_sources', CASE
               WHEN code = 'MX-FED-OBRA' THEN jsonb_build_array('FEDERAL','CONVENIO','MIXED')
               WHEN code = 'MX-FED-CONAGUA-OBRA' THEN jsonb_build_array('FEDERAL','CONVENIO','MIXED')
               WHEN code = 'MX-FED-SICT-OBRA' THEN jsonb_build_array('FEDERAL','CONVENIO','MIXED')
               WHEN code = 'MX-FED-CFE-OBRA' THEN jsonb_build_array('FEDERAL','CONVENIO','MIXED')
               WHEN code LIKE 'MX-LOCAL-STATE%' THEN jsonb_build_array('STATE','FEDERAL','CONVENIO','MIXED')
               WHEN code LIKE 'MX-LOCAL-MUNICIPAL%' THEN jsonb_build_array('MUNICIPAL','STATE','FEDERAL','CONVENIO','MIXED')
               ELSE jsonb_build_array('FEDERAL','CONVENIO','MIXED') END,
             'allowed_legal_regimes', CASE
               WHEN code = 'MX-FED-OBRA' THEN jsonb_build_array('LOPSRM')
               WHEN code = 'MX-FED-CONAGUA-OBRA' THEN jsonb_build_array('LOPSRM')
               WHEN code = 'MX-FED-SICT-OBRA' THEN jsonb_build_array('LOPSRM')
               WHEN code = 'MX-FED-CFE-OBRA' THEN jsonb_build_array('LOPSRM','ENTITY_SPECIFIC')
               WHEN code = 'MX-FED-PEMEX-OBRA' THEN jsonb_build_array('ENTITY_SPECIFIC')
               WHEN code LIKE 'MX-LOCAL-STATE%' THEN jsonb_build_array('LOCAL_PUBLIC_WORKS','LOCAL_PROCUREMENT','LOPSRM')
               WHEN code LIKE 'MX-LOCAL-MUNICIPAL%' THEN jsonb_build_array('LOCAL_PUBLIC_WORKS','LOCAL_PROCUREMENT','LOPSRM')
               ELSE jsonb_build_array('LOPSRM') END
           )
         WHERE tenant_id IS NULL
    """))


def downgrade():
    for idx in ("idx_tender_packages_regime", "idx_tender_packages_funding"):
        op.drop_index(idx, table_name="tender_packages")
    for col in ("legal_regime", "object_class", "funding_source"):
        op.drop_column("tender_packages", col)
