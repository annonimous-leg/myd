"""Catálogo de procurement — labels y case packs desde DB.

Los dicts PROCEDURES / CONTRACT_TYPES / etc. ya NO son autoridad de runtime.
Se cargan de catalog_terms. Si el dominio está vacío → dict vacío (fail-closed
de vocabulario; el API puede reportarlo).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procurement import CatalogTerm, JurisdictionProfile, LegalRule

# Dominios canónicos (códigos de dominio, no labels)
CATALOG_DOMAINS = (
    "PROCEDURES",
    "CONTRACT_TYPES",
    "EVALUATION_CRITERIA",
    "PROJECT_TYPES",
    "FUNDING_SOURCES",
    "OBJECT_CLASSES",
    "LEGAL_REGIMES",
    "SCOPE_SCALES",
)


async def load_catalog_terms(
    db: AsyncSession,
    *,
    tenant_id,
    domain: str | None = None,
) -> dict[str, dict[str, str]]:
    """Return { domain: { code: label } } from catalog_terms.

    Tenant override wins over global (tenant_id NULL).
    """
    q = select(CatalogTerm).where(
        CatalogTerm.active.is_(True),
        or_(CatalogTerm.tenant_id == tenant_id, CatalogTerm.tenant_id.is_(None)),
    )
    if domain:
        q = q.where(CatalogTerm.domain == domain.upper())
    rows = (
        await db.execute(
            q.order_by(
                CatalogTerm.domain.asc(),
                CatalogTerm.sort_order.asc(),
                CatalogTerm.code.asc(),
                CatalogTerm.tenant_id.desc().nullslast(),
            )
        )
    ).scalars().all()

    out: dict[str, dict[str, str]] = {}
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row.domain.upper(), row.code.upper())
        if key in seen:
            continue  # tenant row already preferred by order
        seen.add(key)
        out.setdefault(row.domain.upper(), {})[row.code.upper()] = row.label
    return out


async def load_domain_map(
    db: AsyncSession,
    *,
    tenant_id,
    domain: str,
) -> dict[str, str]:
    all_maps = await load_catalog_terms(db, tenant_id=tenant_id, domain=domain)
    return all_maps.get(domain.upper(), {})


def _normalize_pack(raw: dict[str, Any], *, jurisdiction_code: str) -> dict[str, Any] | None:
    code = str(raw.get("code") or "").strip().upper()
    if not code:
        return None
    artifacts = []
    for item in raw.get("artifacts") or []:
        if not isinstance(item, dict):
            continue
        acode = str(item.get("code") or "").strip()
        if not acode:
            continue
        artifacts.append(
            {
                "code": acode,
                "title": str(item.get("title") or acode),
                "category": str(item.get("category") or "TECNICO").upper(),
                "source_marker": str(item.get("source_marker") or acode),
                "required": bool(item.get("required", True)),
                "requires_uploaded_template": bool(item.get("requires_uploaded_template", False)),
                "description": str(item.get("description") or ""),
            }
        )
    return {
        "code": code,
        "name": str(raw.get("name") or code),
        "jurisdiction_code": str(raw.get("jurisdiction_code") or jurisdiction_code).upper(),
        "project_type": str(raw.get("project_type") or "").upper() or None,
        "description": str(raw.get("description") or ""),
        "artifacts": artifacts,
    }


def _case_pack_codes_from_condition(condition: dict[str, Any]) -> set[str]:
    """Return the explicit case-pack codes that activate a legal rule.

    Case-pack requirements are stored as versioned ``LegalRule`` rows.  A
    rule only belongs to a pack when its condition explicitly binds
    ``case_pack_code``; unscoped rules must not leak into a named pack.
    """
    clauses = condition.get("conditions") or []
    if isinstance(clauses, dict):
        clauses = [clauses]
    codes: set[str] = set()
    for clause in clauses:
        if not isinstance(clause, dict):
            continue
        if str(clause.get("field") or "").lower() != "case_pack_code":
            continue
        if str(clause.get("op") or "eq").lower() not in {"eq", "in"}:
            continue
        value = clause.get("val", clause.get("value"))
        values = value if isinstance(value, list) else [value]
        codes.update(str(item).strip().upper() for item in values if str(item or "").strip())
    return codes


def _artifact_specs_from_rule(rule: LegalRule) -> list[dict[str, Any]]:
    requirement = rule.requirement or {}
    artifacts: list[dict[str, Any]] = []
    for raw_code in requirement.get("artifact_required") or []:
        code = str(raw_code or "").strip()
        if not code:
            continue
        artifacts.append(
            {
                "code": code,
                "title": str(requirement.get("description") or code),
                "category": str(requirement.get("category") or rule.domain or "TECNICO").upper(),
                "source_marker": str(requirement.get("source_marker") or code),
                "required": bool(requirement.get("mandatory", True)),
                "requires_uploaded_template": bool(
                    requirement.get("requires_uploaded_template", False)
                ),
                "description": str(requirement.get("description") or ""),
            }
        )
    return artifacts


def _derive_case_packs_from_rules(
    profile: JurisdictionProfile, rules: list[LegalRule]
) -> list[dict[str, Any]]:
    """Materialize named packs declared by the profile from scoped rules.

    ``ruleset.case_packs`` is the allow-list while each rule condition is the
    membership proof.  This keeps the runtime DB-driven without reviving the
    removed Python ``CASE_PACKS`` constant.
    """
    declared = {
        str(code).strip().upper()
        for code in (profile.ruleset or {}).get("case_packs") or []
        if str(code or "").strip()
    }
    artifacts_by_pack: dict[str, dict[str, dict[str, Any]]] = {
        code: {} for code in declared
    }
    unscoped: dict[str, dict[str, Any]] = {}

    for rule in rules:
        artifacts = _artifact_specs_from_rule(rule)
        if not artifacts:
            continue
        scoped_codes = _case_pack_codes_from_condition(rule.condition or {}) & declared
        targets = scoped_codes or ({f"GENERIC_{profile.code}"} if not declared else set())
        for code in targets:
            bucket = artifacts_by_pack.setdefault(code, {})
            for artifact in artifacts:
                bucket.setdefault(artifact["code"], artifact)
        if not scoped_codes and declared:
            for artifact in artifacts:
                unscoped.setdefault(artifact["code"], artifact)

    packs: list[dict[str, Any]] = []
    for code, artifacts in artifacts_by_pack.items():
        if not artifacts:
            continue
        packs.append(
            {
                "code": code,
                "name": f"Paquete de requisitos — {profile.authority}",
                "jurisdiction_code": profile.code,
                "project_type": None,
                "description": "Artefactos derivados de reglas jurídicas condicionadas al paquete.",
                "artifacts": list(artifacts.values()),
            }
        )

    if unscoped:
        packs.append(
            {
                "code": f"GENERIC_{profile.code}",
                "name": f"Paquete derivado — {profile.authority}",
                "jurisdiction_code": profile.code,
                "project_type": None,
                "description": "Artefactos no condicionados a un paquete específico.",
                "artifacts": list(unscoped.values()),
            }
        )
    return packs


async def load_case_packs(
    db: AsyncSession,
    *,
    tenant_id,
    jurisdiction_code: str | None = None,
) -> list[dict[str, Any]]:
    """Case packs desde JurisdictionProfile.templates['case_packs'] + LegalRule."""
    query = select(JurisdictionProfile).where(
        JurisdictionProfile.active.is_(True),
        or_(JurisdictionProfile.tenant_id == tenant_id, JurisdictionProfile.tenant_id.is_(None)),
    )
    if jurisdiction_code:
        query = query.where(JurisdictionProfile.code == str(jurisdiction_code).upper())
    profiles = (
        await db.execute(query.order_by(JurisdictionProfile.tenant_id.desc().nullslast()))
    ).scalars().all()

    packs: dict[str, dict[str, Any]] = {}
    for profile in profiles:
        templates = profile.templates or {}
        raw_packs = templates.get("case_packs") or []
        if isinstance(raw_packs, dict):
            raw_packs = list(raw_packs.values())
        for raw in raw_packs:
            if not isinstance(raw, dict):
                continue
            normalized = _normalize_pack(raw, jurisdiction_code=profile.code)
            if normalized is None:
                continue
            packs.setdefault(normalized["code"], normalized)

        rules = (
            await db.execute(
                select(LegalRule).where(
                    LegalRule.active.is_(True),
                    LegalRule.jurisdiction_code == profile.code,
                    or_(LegalRule.tenant_id == tenant_id, LegalRule.tenant_id.is_(None)),
                ).order_by(
                    LegalRule.tenant_id.desc().nullslast(),
                    LegalRule.rule_version.desc(),
                )
            )
        ).scalars().all()
        for derived in _derive_case_packs_from_rules(profile, list(rules)):
            packs.setdefault(derived["code"], derived)

    return list(packs.values())


async def get_case_pack(
    db: AsyncSession,
    *,
    tenant_id,
    code: str | None,
) -> dict[str, Any] | None:
    if not code:
        return None
    packs = await load_case_packs(db, tenant_id=tenant_id)
    needle = str(code).upper()
    for pack in packs:
        if pack["code"] == needle:
            return pack
    return None


async def get_configured_case_pack(
    db: AsyncSession, *, tenant_id, jurisdiction_code: str, code: str | None
) -> dict[str, Any] | None:
    """Return only a case pack explicitly configured in the selected profile.

    This is the safe path for proposal compilation: LegalRule/corpus-derived
    artifacts are deliberately excluded from the primary elaboration flow.
    """
    if not code:
        return None
    query = select(JurisdictionProfile).where(
        JurisdictionProfile.active.is_(True),
        JurisdictionProfile.code == str(jurisdiction_code).upper(),
        or_(JurisdictionProfile.tenant_id == tenant_id, JurisdictionProfile.tenant_id.is_(None)),
    ).order_by(JurisdictionProfile.tenant_id.desc().nullslast())
    profile = await db.scalar(query)
    if profile is None:
        return None
    for raw in (profile.templates or {}).get("case_packs") or []:
        if isinstance(raw, dict) and str(raw.get("code") or "").upper() == str(code).upper():
            return _normalize_pack(raw, jurisdiction_code=profile.code)
    return None


async def case_packs_for_jurisdiction(
    db: AsyncSession,
    *,
    tenant_id,
    jurisdiction_code: str,
) -> list[dict[str, Any]]:
    return await load_case_packs(db, tenant_id=tenant_id, jurisdiction_code=jurisdiction_code)


async def build_catalog_payload(
    db: AsyncSession,
    *,
    tenant_id,
) -> dict[str, Any]:
    """Vocabularios listos para /procurement/catalog (sin perfiles)."""
    maps = await load_catalog_terms(db, tenant_id=tenant_id)
    missing = [d for d in CATALOG_DOMAINS if not maps.get(d)]
    return {
        "procedures": maps.get("PROCEDURES", {}),
        "contract_types": maps.get("CONTRACT_TYPES", {}),
        "evaluation_criteria": maps.get("EVALUATION_CRITERIA", {}),
        "project_types": maps.get("PROJECT_TYPES", {}),
        "scope_scales": maps.get("SCOPE_SCALES", {}),
        "funding_sources": maps.get("FUNDING_SOURCES", {}),
        "object_classes": maps.get("OBJECT_CLASSES", {}),
        "legal_regimes": maps.get("LEGAL_REGIMES", {}),
        "vocabulary_complete": len(missing) == 0,
        "vocabulary_missing_domains": missing,
    }
