"""DB-driven proposition structure catalog.

The rows are configuration data attached to the selected dependency profile.
They are not a substitute for requirements extracted from the current tender.
"""
from __future__ import annotations

import json
from typing import Any
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.procurement import JurisdictionProfile, JurisdictionInheritance


def _parse_bool(v: Any) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "si", "sí"}


def _pipe_set(value: str | None) -> set[str]:
    if not value: return set()
    return {p.strip().upper() for p in str(value).split("|") if p.strip()}


def _condition_ok(condition_json: str | None, case_pack_code: str | None) -> bool:
    if not (condition_json or "").strip(): return True
    try: cond = json.loads(condition_json or "")
    except json.JSONDecodeError: return False
    needle = cond.get("case_pack_contains")
    if needle:
        pack = (case_pack_code or "").upper()
        return needle.upper() in pack or pack == needle.upper()
    return True


async def _profiles(db: AsyncSession, tenant_id: Any, code: str) -> list[JurisdictionProfile]:
    seen: set[str] = set(); queue=[code.upper()]; out=[]
    while queue:
        c=queue.pop(0)
        if c in seen: continue
        seen.add(c)
        p=await db.scalar(select(JurisdictionProfile).where(JurisdictionProfile.code==c, JurisdictionProfile.active.is_(True), or_(JurisdictionProfile.tenant_id==tenant_id, JurisdictionProfile.tenant_id.is_(None))).order_by(JurisdictionProfile.tenant_id.desc().nullslast()))
        if p is None: continue
        out.append(p)
        parents=(p.ruleset or {}).get("inherits_from") or []
        links=(await db.execute(select(JurisdictionInheritance.parent_profile_id).where(JurisdictionInheritance.child_profile_id==p.id, JurisdictionInheritance.active.is_(True)))).scalars().all()
        if links:
            ps=(await db.execute(select(JurisdictionProfile).where(
                JurisdictionProfile.id.in_(links),
                JurisdictionProfile.active.is_(True),
                or_(JurisdictionProfile.tenant_id == tenant_id, JurisdictionProfile.tenant_id.is_(None)),
            ))).scalars().all()
            queue.extend(x.code for x in ps)
        queue.extend(str(x).upper() for x in parents)
    return out


async def derive_proposition_structure(
    db: AsyncSession, *, tenant_id: Any, jurisdiction_code: str, procedure_type: str | None = None,
    evaluation_criterion: str | None = None, legal_regime: str | None = "LOPSRM",
    case_pack_code: str | None = None, include_optional: bool = True,
) -> dict[str, Any]:
    profiles=await _profiles(db, tenant_id, jurisdiction_code)
    if not profiles: raise ValueError(f"No existe perfil activo para {jurisdiction_code}.")
    rows_by_code={}
    # Inherited first; selected dependency overrides exact item definitions.
    for p in reversed(profiles):
        for row in (p.templates or {}).get("proposition_structure") or []:
            if isinstance(row, dict) and row.get("code"):
                rows_by_code[str(row["code"])] = row
    proc=(procedure_type or "").strip().upper(); evalc=(evaluation_criterion or "").strip().upper(); regime=(legal_regime or "LOPSRM").strip().upper()
    items=[]
    for row in rows_by_code.values():
        rj=str(row.get("jurisdiction_code") or "").strip().upper()
        if rj and rj != jurisdiction_code.upper(): continue
        rr=str(row.get("legal_regime") or "").strip().upper()
        if regime and rr and rr not in {regime,"ANY"}: continue
        allowed=_pipe_set(row.get("procedure_types"))
        if proc and allowed and proc not in allowed: continue
        allowed_e=_pipe_set(row.get("evaluation_criteria"))
        if evalc and allowed_e and evalc not in allowed_e: continue
        if not _condition_ok(row.get("condition_json"), case_pack_code): continue
        mandatory=_parse_bool(row.get("mandatory", True))
        if not include_optional and not mandatory: continue
        items.append({**row, "mandatory": mandatory, "evidence_types": [x for x in str(row.get("evidence_types") or "").split("|") if x], "artifact_code": row.get("artifact_code") or row["code"], "sort_order": int(row.get("sort_order") or 0), "status_hint": "OPTIONAL" if not mandatory else ("APU_DEFERRED" if "APU_DEFERRED" in str(row.get("notes") or "") else "PENDING")})
    items.sort(key=lambda x:(str(x.get("section") or "").upper(), int(x.get("sort_order") or 0), str(x.get("code"))))
    sections={"LEGAL":[],"TECNICA":[],"ECONOMICA":[]}
    for i in items: sections.setdefault(str(i.get("section") or "").upper(),[]).append(i)
    mandatory=sum(1 for x in items if x["mandatory"])
    deferred=[x["code"] for x in items if x["status_hint"]=="APU_DEFERRED"]
    return {"jurisdiction_code":jurisdiction_code.upper(),"procedure_type":proc or None,"evaluation_criterion":evalc or None,"legal_regime":regime,"case_pack_code":case_pack_code,"sections":sections,"totals":{"items":len(items),"mandatory":mandatory,"optional":len(items)-mandatory,"apu_deferred":len(deferred)},"apu_deferred_codes":deferred,"source":"jurisdiction_profiles.templates.proposition_structure","policy":{"authority":"Configuración DB del perfil seleccionado; no sustituye requisitos del expediente vigente.","apu":"El motor APU se ejecuta solo cuando existen catálogos y datos suficientes."}}


def congruence_check(*, carta_monto: float|None, catalogo_total: float|None, programa_montos_total: float|None, explosion_cd_total: float|None, tolerance: float=0.01)->dict[str,Any]:
    values={"carta_monto":carta_monto,"catalogo_total":catalogo_total,"programa_montos_total":programa_montos_total,"explosion_cd_total":explosion_cd_total}; present={k:float(v) for k,v in values.items() if v is not None}
    if len(present)<2:return {"ok":False,"reason":"Se requieren al menos dos montos para comparar.","values":values,"deltas":{}}
    base="catalogo_total" if "catalogo_total" in present else next(iter(present)); baseline=present[base]; deltas={k:abs(v-baseline) for k,v in present.items()}; ok=all(d<=tolerance for d in deltas.values())
    return {"ok":ok,"baseline":base,"baseline_value":baseline,"values":values,"deltas":deltas,"tolerance":tolerance,"reason":None if ok else "Montos fuera de tolerancia de congruencia."}
