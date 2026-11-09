"""DB-driven procurement format catalog.

The database owns the external format -> canonical field mapping.  Python owns
only the executable compiler algorithms; it must never own tender-specific
format names, titles, paths or dependency assignments.
"""
from __future__ import annotations

from typing import Any
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procurement import JurisdictionProfile, JurisdictionInheritance

_ALIASES = {
    "FORMATO 12": "FORMATO_12", "FORMATO12": "FORMATO_12",
    "FORMA E-7": "FORMA_E-7", "FORMA E7": "FORMA_E-7", "E-7": "FORMA_E-7",
    "PE 09": "PE_09", "PE09": "PE_09", "PE 13": "PE_13", "PE13": "PE_13",
    "FORMATO 8": "FORMATO_8", "FORMATO 9": "FORMATO_9",
    "ECO 1": "ECO.1", "ECO 2": "ECO.2", "ECO 3": "ECO.3",
    "ECO.01": "ECO.1", "ECO.02": "ECO.2", "ECO.03": "ECO.3",
}


def normalize_format_code(code: str) -> str:
    raw = (code or "").strip().upper().replace("  ", " ")
    return _ALIASES.get(raw, raw.replace(" ", "_") if raw.replace(" ", "_") else raw)


async def _profile_chain(db: AsyncSession, tenant_id: Any, code: str) -> list[JurisdictionProfile]:
    """Return most-specific profile first, then active inherited profiles."""
    seen: set[str] = set()
    result: list[JurisdictionProfile] = []
    queue = [code.upper()]
    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        profile = await db.scalar(select(JurisdictionProfile).where(
            JurisdictionProfile.code == current,
            JurisdictionProfile.active.is_(True),
            or_(JurisdictionProfile.tenant_id == tenant_id, JurisdictionProfile.tenant_id.is_(None)),
        ).order_by(JurisdictionProfile.tenant_id.desc().nullslast()))
        if profile is None:
            continue
        result.append(profile)
        parents = (profile.ruleset or {}).get("inherits_from") or []
        profile_id = getattr(profile, "id", None)
        links = (await db.execute(select(JurisdictionInheritance.parent_profile_id).where(
            JurisdictionInheritance.child_profile_id == profile_id,
            JurisdictionInheritance.active.is_(True),
            or_(JurisdictionInheritance.tenant_id == tenant_id, JurisdictionInheritance.tenant_id.is_(None)),
        ))).scalars().all()
        parent_ids = {str(x) for x in links}
        if parent_ids:
            parent_rows = (await db.execute(select(JurisdictionProfile).where(
                JurisdictionProfile.id.in_(links),
                JurisdictionProfile.active.is_(True),
                or_(JurisdictionProfile.tenant_id == tenant_id, JurisdictionProfile.tenant_id.is_(None)),
            ))).scalars().all()
            queue.extend([p.code for p in parent_rows])
        queue.extend([str(x).upper() for x in parents])
    return result


async def load_format_catalog(db: AsyncSession, *, tenant_id: Any, jurisdiction_code: str) -> dict[str, dict[str, Any]]:
    """Load effective format definitions; child entries override inherited entries."""
    profiles = await _profile_chain(db, tenant_id, jurisdiction_code)
    if not profiles:
        raise ValueError(f"No existe un perfil activo para la dependencia {jurisdiction_code}.")
    merged: dict[str, dict[str, Any]] = {}
    for profile in reversed(profiles):
        for row in (profile.templates or {}).get("format_definitions") or []:
            if not isinstance(row, dict) or not row.get("format_code"):
                raise ValueError(f"Catálogo de formatos inválido en {profile.code}.")
            code = normalize_format_code(str(row["format_code"]))
            merged[code] = {**row, "format_code": code}
    return merged


async def resolve_format(db: AsyncSession, *, tenant_id: Any, jurisdiction_code: str, code: str) -> dict[str, Any] | None:
    return (await load_format_catalog(db, tenant_id=tenant_id, jurisdiction_code=jurisdiction_code)).get(normalize_format_code(code))


async def required_paths_for_codes(db: AsyncSession, *, tenant_id: Any, jurisdiction_code: str, codes: list[str]) -> list[str]:
    catalog = await load_format_catalog(db, tenant_id=tenant_id, jurisdiction_code=jurisdiction_code)
    paths: list[str] = []
    seen: set[str] = set()
    for code in codes:
        meta = catalog.get(normalize_format_code(code))
        if meta is None:
            continue
        for path in meta.get("canonical_paths") or []:
            if path not in seen:
                seen.add(path); paths.append(path)
    return paths


async def megalodon_codes_for_external(db: AsyncSession, *, tenant_id: Any, jurisdiction_code: str, codes: list[str]) -> list[str]:
    catalog = await load_format_catalog(db, tenant_id=tenant_id, jurisdiction_code=jurisdiction_code)
    out: list[str] = []; seen: set[str] = set()
    for code in codes:
        meta = catalog.get(normalize_format_code(code))
        if meta is None:
            continue
        value = meta.get("megalodon_code")
        if value and value not in seen:
            seen.add(value); out.append(value)
    return out
