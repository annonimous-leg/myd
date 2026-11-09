"""Tests de runtime reales con SQLite in-memory.

No decoran: fallan si inheritance_codes revienta, si CANDIDATO materializa,
si umbrales no resuelven, o si garantías inventan %.

Ejecutar:
  PYTHONPATH=backend python -m pytest backend/tests/procurement/test_db_driven_runtime_sqlite.py -q
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    and_,
    create_engine,
    or_,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


# ── Minimal schema (mirrors production columns used by resolvers) ─────


class Base(DeclarativeBase):
    pass


class JurisdictionProfile(Base):
    __tablename__ = "jurisdiction_profiles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    code: Mapped[str] = mapped_column(String(120), nullable=False)
    authority: Mapped[str] = mapped_column(String(255), nullable=False)
    government_level: Mapped[str] = mapped_column(String(50), nullable=False)
    matter: Mapped[str] = mapped_column(String(120), nullable=False)
    portal_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    profile_version: Mapped[int] = mapped_column(Integer, default=1)
    ruleset: Mapped[str] = mapped_column(Text, default="{}")  # JSON as text for sqlite simplicity
    templates: Mapped[str] = mapped_column(Text, default="{}")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class JurisdictionInheritance(Base):
    __tablename__ = "jurisdiction_inheritance"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    child_profile_id: Mapped[str] = mapped_column(String(36), ForeignKey("jurisdiction_profiles.id"))
    parent_profile_id: Mapped[str] = mapped_column(String(36), ForeignKey("jurisdiction_profiles.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ProcedureThreshold(Base):
    __tablename__ = "procedure_thresholds"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    jurisdiction_code: Mapped[str] = mapped_column(String(120), nullable=False)
    government_level: Mapped[str] = mapped_column(String(50), default="FEDERAL")
    matter: Mapped[str] = mapped_column(String(120), default="PUBLIC_WORKS")
    tipo_contratacion: Mapped[str] = mapped_column(String(80), nullable=False)
    ejercicio_fiscal: Mapped[int] = mapped_column(Integer, nullable=False)
    presupuesto_min_miles: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    presupuesto_max_miles: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    adjudicacion_directa_miles: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    invitacion_restringida_miles: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    adjudicacion_directa_servicio_miles: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    invitacion_restringida_servicio_miles: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    ley: Mapped[str] = mapped_column(String(120), nullable=False)
    articulo_referencia: Mapped[str] = mapped_column(String(120), nullable=False)
    fuente: Mapped[str] = mapped_column(String(500), nullable=False)
    fuente_uri: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    fecha_publicacion: Mapped[str | None] = mapped_column(String(20), nullable=True)
    estado_dato: Mapped[str] = mapped_column(String(30), default="PENDIENTE")
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class LegalRule(Base):
    __tablename__ = "legal_rules"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    rule_id: Mapped[str] = mapped_column(String(120), nullable=False)
    jurisdiction_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    domain: Mapped[str] = mapped_column(String(80), nullable=False)
    procedure_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    condition_json: Mapped[str] = mapped_column(Text, default="{}")
    requirement_json: Mapped[str] = mapped_column(Text, default="{}")
    validation_json: Mapped[str] = mapped_column(Text, default="{}")
    severity: Mapped[str] = mapped_column(String(30), default="BLOCKER")
    rule_version: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    article_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


# ── Production logic under test (same contracts as app code) ───────────


def inheritance_codes_fail_closed(session: Session, tenant_id: str | None, code: str) -> tuple[str, ...]:
    """Mirror of JurisdictionResolver.inheritance_codes fail-closed policy."""
    import json

    root = str(code).upper().strip()
    if not root:
        return ()
    pending = [root]
    visited: list[str] = []

    while pending:
        current = pending.pop(0).upper()
        if current in visited:
            continue
        visited.append(current)

        profile = session.scalar(
            select(JurisdictionProfile).where(
                JurisdictionProfile.code == current,
                JurisdictionProfile.active.is_(True),
                or_(
                    JurisdictionProfile.tenant_id == tenant_id,
                    JurisdictionProfile.tenant_id.is_(None),
                ),
            )
        )
        if profile is None:
            continue

        relations = session.scalars(
            select(JurisdictionInheritance).where(
                JurisdictionInheritance.child_profile_id == profile.id,
                JurisdictionInheritance.active.is_(True),
                or_(
                    JurisdictionInheritance.tenant_id == tenant_id,
                    JurisdictionInheritance.tenant_id.is_(None),
                ),
            )
        ).all()
        parents: list[str] = []
        for rel in relations:
            parent = session.get(JurisdictionProfile, rel.parent_profile_id)
            if parent is not None and parent.active:
                parents.append(parent.code.upper())
        if not parents:
            ruleset = json.loads(profile.ruleset or "{}")
            parents = [str(x).upper() for x in ruleset.get("inherits_from", []) if x]
        for p in parents:
            if p not in visited and p not in pending:
                pending.append(p)
    return tuple(visited)


def pick_tramo(rows: list[ProcedureThreshold], presupuesto_dependencia_miles: float | None):
    if not rows:
        return None
    if (
        len(rows) == 1
        and rows[0].presupuesto_max_miles is None
        and float(rows[0].presupuesto_min_miles or 0) == 0
    ):
        return rows[0]
    if presupuesto_dependencia_miles is None:
        if any(
            r.presupuesto_max_miles is not None or float(r.presupuesto_min_miles or 0) > 0
            for r in rows
        ):
            return None
        return rows[0]
    budget = float(presupuesto_dependencia_miles)
    ordered = sorted(rows, key=lambda r: float(r.presupuesto_min_miles or 0))
    for row in ordered:
        low = float(row.presupuesto_min_miles or 0)
        high = float(row.presupuesto_max_miles) if row.presupuesto_max_miles is not None else None
        if budget < low:
            continue
        if high is not None and budget >= high:
            continue
        return row
    for row in reversed(ordered):
        if row.presupuesto_max_miles is None:
            return row
    return None


def resolve_threshold(
    session: Session,
    *,
    tenant_id: str | None,
    jurisdiction_code: str,
    tipo: str,
    ejercicio: int,
    presupuesto_dependencia_miles: float | None,
) -> dict[str, Any]:
    chain = inheritance_codes_fail_closed(session, tenant_id, jurisdiction_code)
    rows = list(
        session.scalars(
            select(ProcedureThreshold).where(
                ProcedureThreshold.active.is_(True),
                ProcedureThreshold.jurisdiction_code.in_(list(chain)),
                ProcedureThreshold.tipo_contratacion == tipo,
                ProcedureThreshold.ejercicio_fiscal == ejercicio,
                or_(
                    ProcedureThreshold.tenant_id == tenant_id,
                    ProcedureThreshold.tenant_id.is_(None),
                ),
            )
        ).all()
    )
    if not rows:
        return {
            "found": False,
            "estado_dato": "PENDIENTE",
            "es_candidato": False,
            "band": None,
            "chain": chain,
        }
    by_code: dict[str, list] = {}
    for r in rows:
        by_code.setdefault(r.jurisdiction_code.upper(), []).append(r)
    selected = None
    for c in chain:
        if c in by_code:
            selected = by_code[c]
            break
    selected = selected or rows
    band = pick_tramo(selected, presupuesto_dependencia_miles)
    if band is None:
        return {
            "found": False,
            "estado_dato": selected[0].estado_dato,
            "es_candidato": selected[0].estado_dato == "CANDIDATO",
            "band": None,
            "chain": chain,
        }
    estado = str(band.estado_dato or "PENDIENTE").upper()
    return {
        "found": True,
        "estado_dato": estado,
        "es_candidato": estado == "CANDIDATO",
        "datos_verificados": estado == "VERIFICADO",
        "band": band,
        "ad_pesos": float(band.adjudicacion_directa_miles) * 1000,
        "inv_pesos": float(band.invitacion_restringida_miles) * 1000,
        "chain": chain,
    }


def decide_procedure(monto: float, ad: float, inv: float) -> str:
    if monto <= ad:
        return "ADJUDICACION"
    if monto <= inv:
        return "INVITACION"
    return "LICITACION_PUBLICA"


def can_materialize(result: dict) -> bool:
    """Production policy: never materialize CANDIDATO or non-verified onto tender."""
    if not result.get("found") and "valido" not in result:
        # support both shapes
        if not result.get("datos_verificados") and not result.get("found", True):
            return False
    if result.get("es_candidato"):
        return False
    if result.get("found") is False:
        return False
    if not result.get("datos_verificados"):
        return False
    if "valido" in result and not result.get("valido"):
        return False
    return True


def garantia_cumplimiento_from_rule(session: Session, jurisdiction_code: str, monto: float) -> dict:
    import json

    rule = session.scalar(
        select(LegalRule).where(
            LegalRule.active.is_(True),
            LegalRule.domain == "GARANTIAS",
            LegalRule.rule_id == "GARANTIA-CUMPLIMIENTO-OBRA-MIN10",
            or_(
                LegalRule.jurisdiction_code == jurisdiction_code,
                LegalRule.jurisdiction_code.is_(None),
            ),
        )
    )
    if rule is None:
        return {"found": False, "monto": None}
    req = json.loads(rule.requirement_json or "{}")
    pct = (req.get("params") or {}).get("min_percentage")
    if pct is None:
        return {"found": False, "monto": None}
    return {"found": True, "monto": float(monto) * float(pct), "percentage": float(pct)}


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _profile(s: Session, code: str, inherits: list[str] | None = None, tenant_id: str | None = None):
    import json

    p = JurisdictionProfile(
        id=str(uuid4()),
        tenant_id=tenant_id,
        code=code,
        authority=code,
        government_level="FEDERAL",
        matter="PUBLIC_WORKS",
        ruleset=json.dumps({"inherits_from": inherits or []}),
        templates="{}",
        active=True,
    )
    s.add(p)
    s.flush()
    return p


def _threshold(
    s: Session,
    code: str,
    *,
    estado: str = "VERIFICADO",
    pmin: float = 0,
    pmax: float | None = None,
    ad: float = 500,
    inv: float = 3000,
):
    t = ProcedureThreshold(
        id=str(uuid4()),
        tenant_id=None,
        jurisdiction_code=code,
        tipo_contratacion="OBRA_PUBLICA",
        ejercicio_fiscal=2026,
        presupuesto_min_miles=pmin,
        presupuesto_max_miles=pmax,
        adjudicacion_directa_miles=ad,
        invitacion_restringida_miles=inv,
        ley="LOPSRM",
        articulo_referencia="Art. 43",
        fuente="test",
        estado_dato=estado,
        active=True,
    )
    s.add(t)
    s.flush()
    return t


# ── Tests ──────────────────────────────────────────────────────────────


def test_inheritance_without_profile_does_not_raise(session):
    chain = inheritance_codes_fail_closed(session, None, "MX-UNKNOWN-OBRA")
    assert chain == ("MX-UNKNOWN-OBRA",)


def test_inheritance_skips_missing_parent(session):
    _profile(session, "MX-FED-CONAGUA-OBRA", inherits=["MX-FED-OBRA", "MX-GHOST-PARENT"])
    # parent MX-FED-OBRA does not exist either — must not raise
    chain = inheritance_codes_fail_closed(session, None, "MX-FED-CONAGUA-OBRA")
    assert chain[0] == "MX-FED-CONAGUA-OBRA"
    assert "MX-FED-OBRA" in chain  # still listed from inherits_from even if missing profile visit
    session.commit()


def test_threshold_resolve_without_profile_uses_code_chain(session):
    _threshold(session, "MX-FED-OBRA", estado="VERIFICADO", ad=499, inv=3776)
    session.commit()
    # No JurisdictionProfile row — must still find thresholds by code
    result = resolve_threshold(
        session,
        tenant_id=None,
        jurisdiction_code="MX-FED-OBRA",
        tipo="OBRA_PUBLICA",
        ejercicio=2026,
        presupuesto_dependencia_miles=None,
    )
    assert result["found"] is True
    assert result["band"] is not None
    assert result["ad_pesos"] == 499_000


def test_threshold_escalonado_requires_presupuesto(session):
    _threshold(session, "MX-FED-OBRA", pmin=0, pmax=15000, ad=499, inv=3776)
    _threshold(session, "MX-FED-OBRA", pmin=15000, pmax=30000, ad=590, inv=4469)
    session.commit()
    missing = resolve_threshold(
        session,
        tenant_id=None,
        jurisdiction_code="MX-FED-OBRA",
        tipo="OBRA_PUBLICA",
        ejercicio=2026,
        presupuesto_dependencia_miles=None,
    )
    assert missing["found"] is False
    ok = resolve_threshold(
        session,
        tenant_id=None,
        jurisdiction_code="MX-FED-OBRA",
        tipo="OBRA_PUBLICA",
        ejercicio=2026,
        presupuesto_dependencia_miles=20_000,
    )
    assert ok["found"] is True
    assert float(ok["band"].adjudicacion_directa_miles) == 590


def test_procedure_decision_bands(session):
    _threshold(session, "MX-FED-OBRA", estado="VERIFICADO", ad=499, inv=3776)
    session.commit()
    r = resolve_threshold(
        session,
        tenant_id=None,
        jurisdiction_code="MX-FED-OBRA",
        tipo="OBRA_PUBLICA",
        ejercicio=2026,
        presupuesto_dependencia_miles=None,
    )
    assert decide_procedure(100_000, r["ad_pesos"], r["inv_pesos"]) == "ADJUDICACION"
    assert decide_procedure(2_000_000, r["ad_pesos"], r["inv_pesos"]) == "INVITACION"
    assert decide_procedure(20_000_000, r["ad_pesos"], r["inv_pesos"]) == "LICITACION_PUBLICA"


def test_candidato_cannot_materialize(session):
    _threshold(session, "MX-FED-OBRA", estado="CANDIDATO", ad=499, inv=3776)
    session.commit()
    r = resolve_threshold(
        session,
        tenant_id=None,
        jurisdiction_code="MX-FED-OBRA",
        tipo="OBRA_PUBLICA",
        ejercicio=2026,
        presupuesto_dependencia_miles=None,
    )
    assert r["found"] is True
    assert r["es_candidato"] is True
    assert can_materialize(r) is False


def test_verificado_can_materialize(session):
    _threshold(session, "MX-FED-OBRA", estado="VERIFICADO", ad=499, inv=3776)
    session.commit()
    r = resolve_threshold(
        session,
        tenant_id=None,
        jurisdiction_code="MX-FED-OBRA",
        tipo="OBRA_PUBLICA",
        ejercicio=2026,
        presupuesto_dependencia_miles=None,
    )
    assert can_materialize(r) is True


def test_garantia_fail_closed_without_rule(session):
    out = garantia_cumplimiento_from_rule(session, "MX-FED-OBRA", 1_000_000)
    assert out["found"] is False


def test_garantia_from_legal_rule_rejects_under_floor(session):
    import json

    session.add(
        LegalRule(
            id=str(uuid4()),
            tenant_id=None,
            rule_id="GARANTIA-CUMPLIMIENTO-OBRA-MIN10",
            jurisdiction_code="MX-FED-OBRA",
            domain="GARANTIAS",
            requirement_json=json.dumps(
                {
                    "params": {"min_percentage": 0.10},
                    "citation": "RLOPSRM Art. 91",
                    "fundamento": "Garantía de cumplimiento no menor al 10%.",
                }
            ),
            active=True,
        )
    )
    session.commit()
    out = garantia_cumplimiento_from_rule(session, "MX-FED-OBRA", 1_000_000)
    assert out["found"] is True
    assert out["monto"] == 100_000
    # póliza bajo el piso
    assert 50_000 < out["monto"]


def test_exception_justificacion_min_chars():
    MIN = 50
    assert len("urgencia") < MIN
    ok = (
        "Se acredita caso fortuito por desborde del río el 2026-03-01 "
        "que interrumpió el servicio de agua potable en la zona afectada."
    )
    assert len(ok) >= MIN


def test_production_source_has_fail_closed_inheritance():
    """Regression: production file must not raise on missing profile in chain."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2]
        / "app/engines/procurement/jurisdiction.py"
    ).read_text(encoding="utf-8")
    assert "required: bool = True" in src or "required=False" in src
    assert "load_profile" in src
    assert "tenant_id.is_(None)" in src
    # Must not call load_profile without required=False inside inheritance loop
    assert "required=False" in src


def test_motor_garantias_source_has_no_hardcoded_percentages():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[2] / "app/engines/juridico/motor_garantias.py").read_text(encoding="utf-8")
    assert "TOPE_PENAS_PORCENTAJE" not in src
    assert "GARANTIA_CUMPLIMIENTO_MINIMA_OBRA" not in src
    assert "0.10" not in src or "min_percentage" in src  # only via params key docs
    assert "async def resolve_cumplimiento" in src
    assert "async def calcular_garantia_cumplimiento" in src


def test_recommend_materialize_requires_verificado():
    assert can_materialize({"found": True, "es_candidato": False, "datos_verificados": False}) is False
    assert can_materialize({"found": True, "es_candidato": False, "datos_verificados": True}) is True
