"""Global jurisdiction/legal catalog and article binding for procurement."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from uuid import uuid4

revision = "20260811_procurement_catalog"
down_revision = "20260811_procurement"
branch_labels = None
depends_on = None
UUID = postgresql.UUID(as_uuid=True)

FED_LAW_URL = "https://www.diputados.gob.mx/LeyesBiblio/pdf/LOPSRM.pdf"
RLOPSRM_URL = "https://www.diputados.gob.mx/LeyesBiblio/regley/Reg_LOPSRM.pdf"
LAASSP_URL = "https://www.diputados.gob.mx/LeyesBiblio/ref/laassp.htm"
RLAASSP_URL = "https://www.diputados.gob.mx/LeyesBiblio/regley/Reg_LAASSP.pdf"
COMPRAS_MX_URL = "https://comprasmx.buengobierno.gob.mx/compras-mx"


def upgrade():
    op.alter_column("jurisdiction_profiles", "tenant_id", existing_type=UUID, nullable=True)
    op.drop_constraint("uq_jurisdiction_profile_tenant_code", "jurisdiction_profiles", type_="unique")
    op.create_index("uq_jurisdiction_profile_tenant_code", "jurisdiction_profiles", ["tenant_id", "code"], unique=True)
    op.create_table("legal_articles",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("source_id", UUID, sa.ForeignKey("legal_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("article_code", sa.String(80), nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("effective_from", sa.String(20)),
        sa.Column("effective_to", sa.String(20)),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("status", sa.String(30), nullable=False, server_default="ACTIVE"),
        sa.UniqueConstraint("source_id", "article_code", name="uq_legal_article_source_code"),
    )
    op.create_index("idx_legal_articles_source", "legal_articles", ["source_id"])
    op.add_column("legal_sources", sa.Column("status", sa.String(30), nullable=False, server_default="ACTIVE"))
    op.alter_column("legal_sources", "tenant_id", existing_type=UUID, nullable=True)
    op.alter_column("legal_rules", "tenant_id", existing_type=UUID, nullable=True)
    op.add_column("legal_rules", sa.Column("article_id", UUID, sa.ForeignKey("legal_articles.id", ondelete="SET NULL"), nullable=True))
    op.create_index("idx_legal_rules_article", "legal_rules", ["article_id"])
    # Replace tenant uniqueness with a tenant-aware composite; global rows are unique by code/version via the same index semantics.
    op.drop_constraint("uq_legal_rule_version", "legal_rules", type_="unique")
    op.create_index("uq_legal_rule_version", "legal_rules", ["tenant_id", "rule_id", "rule_version"], unique=True)

    # Global legal sources. The source text is anchored to official URLs from the project guide; exact current validity is a data-governance responsibility.
    sources = {}
    for title, uri, citation, version, jurisdiction in [
        ("LOPSRM", FED_LAW_URL, "LOPSRM", "2025-11-14", "MX-FED-OBRA"),
        ("RLOPSRM", RLOPSRM_URL, "RLOPSRM", "2023", "MX-FED-OBRA"),
        ("LAASSP", LAASSP_URL, "LAASSP", "2025-04-16", "MX-FED-ADQ"),
        ("RLAASSP", RLAASSP_URL, "RLAASSP", "2026-03-27", "MX-FED-ADQ"),
    ]:
        sid = str(uuid4()); sources[citation] = sid
        op.get_bind().execute(sa.text("INSERT INTO legal_sources (id, created_at, updated_at, tenant_id, authority, title, citation, source_uri, version, jurisdiction_code, status) VALUES (:id, now(), now(), NULL, :authority, :title, :citation, :uri, :version, :jurisdiction, 'ACTIVE') ON CONFLICT DO NOTHING"), dict(id=sid, authority="Cámara de Diputados / DOF", title=title, citation=citation, uri=uri, version=version, jurisdiction=jurisdiction))

    articles = [
        ("LOPSRM", "1-4", "Ámbito y definiciones", "Clasificación inicial del objeto: obra pública, servicios relacionados y ámbito de aplicación."),
        ("LOPSRM", "15-24", "Planeación y procedimientos previos", "Planeación, programación, presupuestación y programas anuales; verificar objeto y contexto del procedimiento."),
        ("LOPSRM", "27-30", "Procedimientos de contratación", "Procedimientos de contratación, licitación y reglas generales; confirmar modalidad, carácter y condiciones."),
        ("LOPSRM", "31-35", "Convocatoria, bases y juntas", "Contenido de convocatoria/bases, juntas y modificaciones; extraer requisitos y fechas."),
        ("LOPSRM", "36-40", "Presentación, evaluación y fallo", "Presentación/apertura, evaluación, fallo y supuestos de licitación desierta/cancelación."),
        ("LOPSRM", "41-44", "Excepciones", "Excepciones a licitación, invitación y contratación directa dentro de los supuestos legales."),
        ("LOPSRM", "45-47", "Contratación y formalización", "Tipos de contratación, contrato y obligaciones de formalización."),
        ("LOPSRM", "48-51", "Garantías y anticipo", "Garantías, anticipo y reglas asociadas al procedimiento."),
        ("LOPSRM", "52-58", "Ejecución y pagos", "Ejecución, pago, ajustes y aspectos contractuales que condicionan la coherencia de la propuesta."),
        ("LOPSRM", "59-63", "Modificaciones y terminación", "Modificaciones, rescisión/terminación y riesgos posteriores al fallo."),
        ("LOPSRM", "64-69", "Recepción y finiquito", "Recepción, finiquito y terminación; conservar trazabilidad para cierre."),
        ("LOPSRM", "74-80", "Control y responsabilidades", "Información, control, responsabilidades y sanciones conforme al texto vigente."),
        ("LOPSRM", "83+", "Defensa e inconformidades", "Medios de defensa e inconformidades conforme al texto vigente."),
        ("LOPSRM", "24", "Modalidades de contratación", "La guía identifica licitación pública, invitación a tres y adjudicación directa como modalidades que determinan el procedimiento aplicable."),
        ("LOPSRM", "36", "Evaluación", "La guía identifica la secuencia de evaluación de solvencia técnica y económica y exige seleccionar el criterio aplicable al procedimiento."),
        ("LOPSRM", "46", "Tipos de contrato", "La guía vincula el artículo con precios unitarios, precio alzado y contratos mixtos."),
        ("RLOPSRM", "58-68", "Análisis y cálculo de precios unitarios", "La guía identifica este bloque como la base reglamentaria para APU, costos directos, indirectos, financiamiento, utilidad y cargos aplicables."),
        ("RLOPSRM", "191", "Factor de salario real", "La guía exige conservar los componentes, periodo, días pagados y laborados y obligaciones patronales del FSR/FASAR."),
        ("RLOPSRM", "213", "Seguros y fianzas", "La guía vincula seguros y fianzas con el tratamiento de costos indirectos para la propuesta."),
    ]
    article_ids={}
    for src, code, title, summary in articles:
        aid=str(uuid4()); article_ids[(src,code)] = aid
        op.get_bind().execute(sa.text("INSERT INTO legal_articles (id, created_at, updated_at, source_id, article_code, title, summary, status) VALUES (:id, now(), now(), :sid, :code, :title, :summary, 'ACTIVE')"), dict(id=aid, sid=sources[src], code=code, title=title, summary=summary))

    profiles = [
        ("MX-FED-OBRA", "Gobierno Federal — Obra Pública", "FEDERAL", "PUBLIC_WORKS", {
            "regime_family":"LOPSRM", "selection_label":"Obra pública federal",
            "allowed_procedures":["LICITACION_PUBLICA","INVITACION","ADJUDICACION"],
            "allowed_contract_types":["UNIT_PRICES","LUMP_SUM","MIXED"],
            "allowed_evaluation_criteria":["BINARY","POINTS_PERCENTAGES"],
            "legal_sources":["LOPSRM","RLOPSRM"], "portal_code":"COMPRAS_MX"
        }),
        ("MX-FED-ADQ", "Gobierno Federal — Adquisiciones", "FEDERAL", "ACQUISITIONS", {
            "regime_family":"LAASSP", "selection_label":"Adquisiciones federales",
            "allowed_procedures":["LICITACION_PUBLICA","INVITACION","ADJUDICACION"],
            "allowed_contract_types":["MIXED"],
            "allowed_evaluation_criteria":["BINARY","POINTS_PERCENTAGES","COST_BENEFIT"],
            "legal_sources":["LAASSP","RLAASSP"], "portal_code":"COMPRAS_MX"
        }),
        ("MX-FED-SERV", "Gobierno Federal — Servicios", "FEDERAL", "SERVICES", {
            "regime_family":"LAASSP", "selection_label":"Servicios federales",
            "allowed_procedures":["LICITACION_PUBLICA","INVITACION","ADJUDICACION"],
            "allowed_contract_types":["MIXED"],
            "allowed_evaluation_criteria":["BINARY","POINTS_PERCENTAGES","COST_BENEFIT"],
            "legal_sources":["LAASSP","RLAASSP"], "portal_code":"COMPRAS_MX"
        }),
        ("MX-FED-CONAGUA-OBRA", "CONAGUA", "FEDERAL", "PUBLIC_WORKS", {
            "regime_family":"LOPSRM+ENTITY_RULES", "selection_label":"CONAGUA — Obra pública",
            "allowed_procedures":["LICITACION_PUBLICA","INVITACION","ADJUDICACION"],
            "allowed_contract_types":["UNIT_PRICES","LUMP_SUM","MIXED"],
            "allowed_evaluation_criteria":["BINARY","POINTS_PERCENTAGES"],
            "legal_sources":["LOPSRM","RLOPSRM"], "portal_code":"COMPRAS_MX", "inherits_from":["MX-FED-OBRA"], "requires_tender_specific_annexes":True, "case_packs":["REFERENCE_CONAGUA_PTAR_2026"]
        }),
        ("MX-FED-SICT-OBRA", "SICT", "FEDERAL", "PUBLIC_WORKS", {
            "regime_family":"LOPSRM+ENTITY_RULES", "selection_label":"SICT — Obra pública",
            "allowed_procedures":["LICITACION_PUBLICA","INVITACION","ADJUDICACION"],
            "allowed_contract_types":["UNIT_PRICES","LUMP_SUM","MIXED"],
            "allowed_evaluation_criteria":["BINARY","POINTS_PERCENTAGES"],
            "legal_sources":["LOPSRM","RLOPSRM"], "portal_code":"COMPRAS_MX", "inherits_from":["MX-FED-OBRA"], "requires_tender_specific_annexes":True, "case_packs":["SICT_DT_2026"]
        }),
        ("MX-FED-CFE-OBRA", "CFE", "FEDERAL", "PUBLIC_WORKS", {
            "regime_family":"LOPSRM+ENTITY_RULES", "selection_label":"CFE — Obra eléctrica",
            "allowed_procedures":["LICITACION_PUBLICA","INVITACION","ADJUDICACION"],
            "allowed_contract_types":["UNIT_PRICES","LUMP_SUM","MIXED"],
            "allowed_evaluation_criteria":["BINARY","POINTS_PERCENTAGES"],
            "legal_sources":["LOPSRM","RLOPSRM"], "portal_code":"COMPRAS_MX",
            "inherits_from":["MX-FED-OBRA"], "requires_official_entity_pack":True,
            "case_packs":["CFE_DCPROTER"]
        }),
        ("MX-FED-PEMEX-OBRA", "PEMEX", "FEDERAL", "PUBLIC_WORKS", {
            "regime_family":"ENTITY_SPECIFIC", "selection_label":"PEMEX — Obra / régimen especial",
            "allowed_procedures":[], "allowed_contract_types":["UNIT_PRICES","LUMP_SUM","MIXED"],
            "allowed_evaluation_criteria":["BINARY","POINTS_PERCENTAGES"], "legal_sources":[],
            "requires_official_entity_pack":True
        }),
        ("MX-FED-SECRETARIAS-OBRA", "Secretaría / dependencia federal — obra", "FEDERAL", "PUBLIC_WORKS", {
            "regime_family":"LOPSRM", "selection_label":"Dependencia federal — obra pública",
            "allowed_procedures":["LICITACION_PUBLICA","INVITACION","ADJUDICACION"],
            "allowed_contract_types":["UNIT_PRICES","LUMP_SUM","MIXED"],
            "allowed_evaluation_criteria":["BINARY","POINTS_PERCENTAGES"],
            "legal_sources":["LOPSRM","RLOPSRM"], "portal_code":"COMPRAS_MX",
            "inherits_from":["MX-FED-OBRA"]
        }),
        ("MX-LOCAL-STATE-OBRA", "Entidad federativa — perfil a configurar", "ESTATAL", "PUBLIC_WORKS", {
            "regime_family":"STATE_SPECIFIC", "selection_label":"Estado — cargar ley, reglamento y lineamientos oficiales",
            "allowed_procedures":[], "allowed_contract_types":["UNIT_PRICES","LUMP_SUM","MIXED"],
            "allowed_evaluation_criteria":["BINARY","POINTS_PERCENTAGES"], "legal_sources":[],
            "requires_official_entity_pack":True
        }),
        ("MX-LOCAL-MUNICIPAL-OBRA", "Municipio/alcaldía — perfil a configurar", "MUNICIPAL", "PUBLIC_WORKS", {
            "regime_family":"MUNICIPAL_SPECIFIC", "selection_label":"Municipio/alcaldía — cargar ley, reglamento y lineamientos oficiales",
            "allowed_procedures":[], "allowed_contract_types":["UNIT_PRICES","LUMP_SUM","MIXED"],
            "allowed_evaluation_criteria":["BINARY","POINTS_PERCENTAGES"], "legal_sources":[],
            "requires_official_entity_pack":True
        }),
        ("MX-ENTITY-SPECIAL", "Entidad/Dependencia con régimen especial", "FEDERAL", "PUBLIC_WORKS", {
            "regime_family":"ENTITY_SPECIFIC", "selection_label":"Régimen especial — requiere RuleSet oficial",
            "allowed_procedures":["LICITACION_PUBLICA","INVITACION","ADJUDICACION"],
            "allowed_contract_types":["UNIT_PRICES","LUMP_SUM","MIXED"],
            "allowed_evaluation_criteria":["BINARY","POINTS_PERCENTAGES"],
            "legal_sources":[]
        }),
    ]
    for code, authority, level, matter, ruleset in profiles:
        pid=str(uuid4())
        op.get_bind().execute(sa.text("INSERT INTO jurisdiction_profiles (id, created_at, updated_at, tenant_id, code, authority, government_level, matter, portal_code, profile_version, ruleset, templates, active) VALUES (:id, now(), now(), NULL, :code, :authority, :level, :matter, :portal, 1, CAST(:ruleset AS jsonb), '{}'::jsonb, true) ON CONFLICT DO NOTHING"), dict(id=pid, code=code, authority=authority, level=level, matter=matter, portal="COMPRAS_MX", ruleset=__import__('json').dumps(ruleset)))

    rules=[
        ("LOPSRM-PROC-24", "MX-FED-OBRA", None, "PUBLIC_WORKS", {"conditions":[{"field":"procedure_type","op":"in","val":["LICITACION_PUBLICA","INVITACION","ADJUDICACION"]}]}, {"code":"PROC_MODALITY","category":"LEGAL","description":"El procedimiento debe corresponder a una modalidad reconocida por el régimen aplicable.","mandatory":True,"evidence_required":[{"kind":"SOURCE_DOCUMENT","subject":"convocatoria"}],"artifact_required":[],"citation":"LOPSRM Art. 24"}, {"type":"enum","field":"procedure_type","values":["LICITACION_PUBLICA","INVITACION","ADJUDICACION"]}, "24"),
        ("LOPSRM-TYPE-46", "MX-FED-OBRA", None, "PUBLIC_WORKS", {"conditions":[{"field":"contract_type","op":"in","val":["UNIT_PRICES","LUMP_SUM","MIXED"]}]}, {"code":"CONTRACT_TYPE","category":"LEGAL","description":"El tipo de contrato debe quedar definido y sustentado por las bases del procedimiento.","mandatory":True,"citation":"LOPSRM Art. 46"}, {"type":"enum","field":"contract_type","values":["UNIT_PRICES","LUMP_SUM","MIXED"]}, "46"),
        ("RLOPSRM-FSR-191", "MX-FED-OBRA", "UNIT_PRICES", "PUBLIC_WORKS", {"conditions":[{"field":"contract_type","op":"eq","val":"UNIT_PRICES"}]}, {"code":"FSR_APU","category":"ECONOMICO","description":"Los APU con mano de obra deben conservar el cálculo del factor de salario real y su evidencia de insumos y periodo.","mandatory":True,"evidence_required":[{"kind":"CALCULATION","subject":"FSR"}],"artifact_required":["AE-03","FASAR"],"citation":"RLOPSRM Art. 191"}, {"type":"required_artifact","artifact":"FASAR"}, "191"),
        ("RLOPSRM-IND-213", "MX-FED-OBRA", None, "PUBLIC_WORKS", {"conditions":[]}, {"code":"INSURANCE_BONDS","category":"ECONOMICO","description":"La estructura económica debe contemplar seguros y fianzas conforme a las bases y reglas aplicables.","mandatory":True,"citation":"RLOPSRM Art. 213"}, {"type":"required_component","component":"insurance_bonds"}, "213"),
        ("LOPSRM-EVAL-36", "MX-FED-OBRA", None, "PUBLIC_WORKS", {"conditions":[{"field":"evaluation_criterion","op":"in","val":["BINARY","POINTS_PERCENTAGES"]}]}, {"code":"EVALUATION_CRITERION","category":"LEGAL","description":"El criterio de evaluación debe quedar seleccionado y respaldado por la convocatoria/bases.","mandatory":True,"evidence_required":[{"kind":"SOURCE_DOCUMENT","subject":"bases"}],"citation":"LOPSRM Art. 36"}, {"type":"enum","field":"evaluation_criterion","values":["BINARY","POINTS_PERCENTAGES"]}, "36"),
    ]
    # Seed the federal rules under the canonical profiles and specialized federal entity profiles as inheritance by the engine.
    for rid, juris, proc, domain, condition, req, validation, article_code in rules:
        rid_uuid=str(uuid4())
        sid=sources["LOPSRM" if rid.startswith("LOPSRM") else "RLOPSRM"]
        aid=article_ids[("LOPSRM" if rid.startswith("LOPSRM") else "RLOPSRM", article_code)]
        op.get_bind().execute(sa.text("INSERT INTO legal_rules (id, created_at, updated_at, tenant_id, rule_id, jurisdiction_code, domain, procedure_type, source_id, article_id, source_version, condition, requirement, validation, severity, rule_version, active) VALUES (:id, now(), now(), NULL, :rid, :juris, :domain, :proc, :sid, :aid, 'guide-2026-08-11', CAST(:cond AS jsonb), CAST(:req AS jsonb), CAST(:val AS jsonb), 'BLOCKER', 1, true) ON CONFLICT DO NOTHING"), dict(id=rid_uuid, rid=rid, juris=juris, domain=domain, proc=proc, sid=sid, aid=aid, cond=__import__('json').dumps(condition), req=__import__('json').dumps(req), val=__import__('json').dumps(validation)))

    # Reference case requirements from the project guide. They are activated only when the explicit case pack is selected.
    case_rules = []
    for i in range(1, 14):
        case_rules.append((
            f"CONAGUA-AT-{i:02d}", "MX-FED-CONAGUA-OBRA", None, "PUBLIC_WORKS",
            {"conditions":[{"field":"case_pack_code","op":"eq","val":"REFERENCE_CONAGUA_PTAR_2026"}]},
            {"code":f"AT-{i:02d}", "category":"TECNICO", "description":f"Anexo técnico AT-{i:02d} requerido por el caso de aceptación CONAGUA/PTAR de la guía.", "mandatory":True, "artifact_required":[f"AT-{i:02d}"], "source_marker":f"AT-{i}"},
            {"type":"required_artifact","artifact":f"AT-{i:02d}"}, "31-35"
        ))
    for i in range(1, 13):
        case_rules.append((
            f"CONAGUA-AE-{i:02d}", "MX-FED-CONAGUA-OBRA", None, "PUBLIC_WORKS",
            {"conditions":[{"field":"case_pack_code","op":"eq","val":"REFERENCE_CONAGUA_PTAR_2026"}]},
            {"code":f"AE-{i:02d}", "category":"ECONOMICO", "description":f"Anexo económico AE-{i:02d} requerido por el caso de aceptación CONAGUA/PTAR de la guía.", "mandatory":True, "artifact_required":[f"AE-{i:02d}"], "source_marker":f"AE-{i}"},
            {"type":"required_artifact","artifact":f"AE-{i:02d}"}, "58-68"
        ))
    for rid, juris, proc, domain, condition, req, validation, article_code in case_rules:
        rid_uuid=str(uuid4())
        source_key = "LOPSRM" if article_code in {"31-35"} else "RLOPSRM"
        sid = sources[source_key]
        aid = article_ids[(source_key, article_code)]
        op.get_bind().execute(sa.text("INSERT INTO legal_rules (id, created_at, updated_at, tenant_id, rule_id, jurisdiction_code, domain, procedure_type, source_id, article_id, source_version, condition, requirement, validation, severity, rule_version, active) VALUES (:id, now(), now(), NULL, :rid, :juris, :domain, :proc, :sid, :aid, 'guide-2026-08-11', CAST(:cond AS jsonb), CAST(:req AS jsonb), CAST(:val AS jsonb), 'BLOCKER', 1, true) ON CONFLICT DO NOTHING"), dict(id=rid_uuid, rid=rid, juris=juris, domain=domain, proc=proc, sid=sid, aid=aid, cond=__import__('json').dumps(condition), req=__import__('json').dumps(req), val=__import__('json').dumps(validation)))

    # Entity profiles inherit the federal source/rules at runtime; entity-specific overrides must be loaded from the tender's own bases.


def downgrade():
    op.drop_index("uq_legal_rule_version", table_name="legal_rules")
    op.create_unique_constraint("uq_legal_rule_version", "legal_rules", ["tenant_id", "rule_id", "rule_version"])
    op.drop_index("idx_legal_rules_article", table_name="legal_rules")
    op.drop_column("legal_rules", "article_id")
    op.alter_column("legal_rules", "tenant_id", existing_type=UUID, nullable=False)
    op.drop_column("legal_sources", "status")
    op.alter_column("legal_sources", "tenant_id", existing_type=UUID, nullable=False)
    op.drop_index("idx_legal_articles_source", table_name="legal_articles")
    op.drop_table("legal_articles")
    op.drop_index("uq_jurisdiction_profile_tenant_code", table_name="jurisdiction_profiles")
    op.create_unique_constraint("uq_jurisdiction_profile_tenant_code", "jurisdiction_profiles", ["tenant_id", "code"])
    op.alter_column("jurisdiction_profiles", "tenant_id", existing_type=UUID, nullable=False)
