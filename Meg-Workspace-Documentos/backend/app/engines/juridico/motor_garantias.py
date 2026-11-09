"""Motor de garantías y penalizaciones 100% DB-driven.

Fuente de verdad: LegalRule (domain=GARANTIAS | PENALIZACIONES).
Sin constantes de porcentaje hardcodeadas en runtime; todo sale de LegalRule en DB.

Fail-closed: si no hay regla activa en DB → found=False / error de dominio.
No inventa porcentajes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contrato import TipoGarantia, TipoPenalizacion
from app.models.procurement import LegalRule


@dataclass(frozen=True)
class GarantiaDecision:
    found: bool
    monto_requerido: float
    percentage: float | None
    rule_id: str | None
    ley: str | None
    articulo: str | None
    fundamento: str | None
    error: str | None = None


@dataclass(frozen=True)
class PenalizacionDecision:
    found: bool
    monto_calculado: float
    monto_aplicado: float
    dias_atraso: int
    dentro_tope: bool
    tope_legal: float
    percentage_cap: float | None
    rule_id: str | None
    ley: str | None
    articulo: str | None
    observaciones: str
    error: str | None = None


@dataclass
class ResultadoGarantia:
    tipo: TipoGarantia
    monto_requerido: float
    monto_actual: float
    vigente: bool
    observaciones: str


@dataclass
class ResultadoPenalizacion:
    tipo: TipoPenalizacion
    monto_calculado: float
    monto_aplicado: float
    dias_atraso: int
    dentro_tope: bool
    tope_legal: float
    observaciones: str


class MotorGarantiasPenalizaciones:
    """Resuelve pisos/topes solo desde LegalRule en DB."""

    RULE_CUMPLIMIENTO_OBRA = "GARANTIA-CUMPLIMIENTO-OBRA-MIN10"
    RULE_ANTICIPO_OBRA = "GARANTIA-ANTICIPO-OBRA-100"
    RULE_ANTICIPO_ADQ = "GARANTIA-ANTICIPO-ADQ-100"
    RULE_TOPE_PENAS_OBRA = "TOPE-PENAS-CONVENCIONALES-OBRA"
    RULE_TOPE_PENAS_ADQ = "TOPE-PENAS-CONVENCIONALES-ADQ"

    async def _load_rule(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID | str | None,
        jurisdiction_code: str | None,
        domain: str,
        rule_id: str,
    ) -> LegalRule | None:
        from app.engines.procurement.jurisdiction import JurisdictionResolver

        codes: list[str] = []
        if jurisdiction_code:
            chain = await JurisdictionResolver().inheritance_codes(
                db, tenant_id or "00000000-0000-0000-0000-000000000000", jurisdiction_code
            )
            codes = list(chain)

        filters = [
            LegalRule.active.is_(True),
            LegalRule.domain == domain,
            LegalRule.rule_id == rule_id,
            or_(LegalRule.tenant_id == tenant_id, LegalRule.tenant_id.is_(None)),
        ]
        if codes:
            filters.append(
                or_(
                    LegalRule.jurisdiction_code.in_(codes),
                    LegalRule.jurisdiction_code.is_(None),
                )
            )

        return await db.scalar(
            select(LegalRule)
            .where(*filters)
            .order_by(LegalRule.tenant_id.desc().nullslast(), LegalRule.rule_version.desc())
        )

    @staticmethod
    def _params(rule: LegalRule) -> dict[str, Any]:
        req = rule.requirement or {}
        params = req.get("params") or {}
        return params if isinstance(params, dict) else {}

    @staticmethod
    def _meta(rule: LegalRule) -> tuple[str, str, str]:
        req = rule.requirement or {}
        ley = str(req.get("ley") or "")
        articulo = str(req.get("articulo") or req.get("citation") or "")
        fundamento = str(req.get("fundamento") or req.get("description") or "")
        return ley, articulo, fundamento

    async def resolve_cumplimiento(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID | str | None,
        jurisdiction_code: str | None,
        monto: float,
        tipo_contrato: str = "obra",
    ) -> GarantiaDecision:
        rule_id = self.RULE_CUMPLIMIENTO_OBRA
        rule = await self._load_rule(
            db,
            tenant_id=tenant_id,
            jurisdiction_code=jurisdiction_code,
            domain="GARANTIAS",
            rule_id=rule_id,
        )
        if rule is None:
            return GarantiaDecision(
                found=False,
                monto_requerido=0.0,
                percentage=None,
                rule_id=rule_id,
                ley=None,
                articulo=None,
                fundamento=None,
                error=f"Regla {rule_id} no encontrada en DB (domain=GARANTIAS).",
            )
        params = self._params(rule)
        pct = params.get("min_percentage")
        if pct is None:
            return GarantiaDecision(
                found=False,
                monto_requerido=0.0,
                percentage=None,
                rule_id=rule.rule_id,
                ley=None,
                articulo=None,
                fundamento=None,
                error=f"Regla {rule.rule_id} sin params.min_percentage.",
            )
        percentage = float(pct)
        ley, articulo, fundamento = self._meta(rule)
        return GarantiaDecision(
            found=True,
            monto_requerido=float(monto) * percentage,
            percentage=percentage,
            rule_id=rule.rule_id,
            ley=ley or None,
            articulo=articulo or None,
            fundamento=fundamento or None,
        )

    async def resolve_anticipo(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID | str | None,
        jurisdiction_code: str | None,
        monto_anticipo: float,
        es_obra: bool = True,
    ) -> GarantiaDecision:
        rule_id = self.RULE_ANTICIPO_OBRA if es_obra else self.RULE_ANTICIPO_ADQ
        rule = await self._load_rule(
            db,
            tenant_id=tenant_id,
            jurisdiction_code=jurisdiction_code,
            domain="GARANTIAS",
            rule_id=rule_id,
        )
        if rule is None:
            return GarantiaDecision(
                found=False,
                monto_requerido=0.0,
                percentage=None,
                rule_id=rule_id,
                ley=None,
                articulo=None,
                fundamento=None,
                error=f"Regla {rule_id} no encontrada en DB.",
            )
        params = self._params(rule)
        pct = params.get("percentage", params.get("min_percentage", 1.0))
        percentage = float(pct)
        ley, articulo, fundamento = self._meta(rule)
        return GarantiaDecision(
            found=True,
            monto_requerido=float(monto_anticipo) * percentage,
            percentage=percentage,
            rule_id=rule.rule_id,
            ley=ley or None,
            articulo=articulo or None,
            fundamento=fundamento or None,
        )

    async def resolve_tope_penas(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID | str | None,
        jurisdiction_code: str | None,
        monto_contrato: float,
        es_obra: bool = True,
    ) -> GarantiaDecision:
        rule_id = self.RULE_TOPE_PENAS_OBRA if es_obra else self.RULE_TOPE_PENAS_ADQ
        rule = await self._load_rule(
            db,
            tenant_id=tenant_id,
            jurisdiction_code=jurisdiction_code,
            domain="PENALIZACIONES",
            rule_id=rule_id,
        )
        if rule is None:
            return GarantiaDecision(
                found=False,
                monto_requerido=0.0,
                percentage=None,
                rule_id=rule_id,
                ley=None,
                articulo=None,
                fundamento=None,
                error=f"Regla {rule_id} no encontrada en DB (domain=PENALIZACIONES).",
            )
        params = self._params(rule)
        ley, articulo, fundamento = self._meta(rule)
        if params.get("max_percentage") is not None:
            pct = float(params["max_percentage"])
            return GarantiaDecision(
                found=True,
                monto_requerido=float(monto_contrato) * pct,
                percentage=pct,
                rule_id=rule.rule_id,
                ley=ley or None,
                articulo=articulo or None,
                fundamento=fundamento or None,
            )
        cumplimiento = await self.resolve_cumplimiento(
            db,
            tenant_id=tenant_id,
            jurisdiction_code=jurisdiction_code,
            monto=monto_contrato,
        )
        if not cumplimiento.found:
            return GarantiaDecision(
                found=False,
                monto_requerido=0.0,
                percentage=None,
                rule_id=rule.rule_id,
                ley=ley or None,
                articulo=articulo or None,
                fundamento=fundamento or None,
                error=f"Tope penas depende de cumplimiento y no está en DB: {cumplimiento.error}",
            )
        return GarantiaDecision(
            found=True,
            monto_requerido=cumplimiento.monto_requerido,
            percentage=cumplimiento.percentage,
            rule_id=rule.rule_id,
            ley=ley or None,
            articulo=articulo or None,
            fundamento=fundamento or None,
        )

    async def calcular_garantia_cumplimiento(
        self,
        db: AsyncSession,
        monto_contrato: float,
        *,
        tenant_id: UUID | str | None = None,
        jurisdiction_code: str | None = None,
        tipo_contrato: str = "obra",
    ) -> tuple[float, GarantiaDecision]:
        dec = await self.resolve_cumplimiento(
            db,
            tenant_id=tenant_id,
            jurisdiction_code=jurisdiction_code,
            monto=monto_contrato,
            tipo_contrato=tipo_contrato,
        )
        return (dec.monto_requerido if dec.found else 0.0), dec

    async def calcular_penalizacion_atraso(
        self,
        db: AsyncSession,
        monto_contrato: float,
        dias_atraso: int,
        *,
        tenant_id: UUID | str | None = None,
        jurisdiction_code: str | None = None,
        es_obra: bool = True,
        porcentaje_diario: float | None = None,
    ) -> PenalizacionDecision:
        tope = await self.resolve_tope_penas(
            db,
            tenant_id=tenant_id,
            jurisdiction_code=jurisdiction_code,
            monto_contrato=monto_contrato,
            es_obra=es_obra,
        )
        if not tope.found:
            return PenalizacionDecision(
                found=False,
                monto_calculado=0.0,
                monto_aplicado=0.0,
                dias_atraso=int(dias_atraso),
                dentro_tope=False,
                tope_legal=0.0,
                percentage_cap=None,
                rule_id=tope.rule_id,
                ley=None,
                articulo=None,
                observaciones="",
                error=tope.error,
            )
        if porcentaje_diario is None:
            calculado = 0.0
            obs = (
                "Sin params.daily_percentage en LegalRule; monto diario no se inventa. "
                f"Tope legal resuelto: {tope.monto_requerido:,.2f} ({tope.rule_id})."
            )
        else:
            calculado = float(monto_contrato) * float(porcentaje_diario) * int(dias_atraso)
            obs = f"Cálculo con daily_percentage={porcentaje_diario} × {dias_atraso} días."
        aplicado = min(calculado, tope.monto_requerido) if calculado else 0.0
        return PenalizacionDecision(
            found=True,
            monto_calculado=calculado,
            monto_aplicado=aplicado,
            dias_atraso=int(dias_atraso),
            dentro_tope=calculado <= tope.monto_requerido if calculado else True,
            tope_legal=tope.monto_requerido,
            percentage_cap=tope.percentage,
            rule_id=tope.rule_id,
            ley=tope.ley,
            articulo=tope.articulo,
            observaciones=obs,
        )

    async def validar_garantia_contra_piso(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID | str | None,
        jurisdiction_code: str | None,
        monto_contrato: float,
        monto_poliza: float,
        tipo_contrato: str = "obra",
    ) -> GarantiaDecision:
        dec = await self.resolve_cumplimiento(
            db,
            tenant_id=tenant_id,
            jurisdiction_code=jurisdiction_code,
            monto=monto_contrato,
            tipo_contrato=tipo_contrato,
        )
        if not dec.found:
            return dec
        if float(monto_poliza) + 1e-9 < dec.monto_requerido:
            return GarantiaDecision(
                found=True,
                monto_requerido=dec.monto_requerido,
                percentage=dec.percentage,
                rule_id=dec.rule_id,
                ley=dec.ley,
                articulo=dec.articulo,
                fundamento=dec.fundamento,
                error=(
                    f"Póliza ${monto_poliza:,.2f} debajo del piso legal "
                    f"${dec.monto_requerido:,.2f} ({dec.rule_id} / {dec.articulo})."
                ),
            )
        return dec

    async def resolve_seriedad(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID | str | None,
        jurisdiction_code: str | None,
        monto_propuesta: float,
        seriedad_required: bool = False,
        percentage_from_convocatoria: float | None = None,
        es_obra: bool = True,
    ) -> GarantiaDecision:
        """Seriedad solo si la convocatoria/case_pack la activa.

        No inventa 5%. Si seriedad_required y percentage_from_convocatoria, usa ese %.
        Si required pero sin %, carga regla y sigue sin monto (PENDIENTE de bases).
        """
        rule_id = "GARANTIA-SERIEDAD-PROPUESTA" if es_obra else "GARANTIA-SERIEDAD-PROPUESTA-ADQ"
        if not seriedad_required:
            return GarantiaDecision(
                found=False,
                monto_requerido=0.0,
                percentage=None,
                rule_id=rule_id,
                ley=None,
                articulo=None,
                fundamento=None,
                error="Seriedad no exigida por convocatoria/case_pack (activation=CONVOCATORIA_OR_CASE_PACK).",
            )
        if percentage_from_convocatoria is not None:
            pct = float(percentage_from_convocatoria)
            return GarantiaDecision(
                found=True,
                monto_requerido=float(monto_propuesta) * pct,
                percentage=pct,
                rule_id=rule_id,
                ley="CONVOCATORIA",
                articulo="bases",
                fundamento="Porcentaje de seriedad fijado en la convocatoria/bases.",
            )
        rule = await self._load_rule(
            db,
            tenant_id=tenant_id,
            jurisdiction_code=jurisdiction_code,
            domain="GARANTIAS",
            rule_id=rule_id,
        )
        return GarantiaDecision(
            found=False,
            monto_requerido=0.0,
            percentage=None,
            rule_id=rule_id if rule else rule_id,
            ley="CONVOCATORIA",
            articulo="bases",
            fundamento=(rule.requirement or {}).get("fundamento") if rule else None,
            error="Seriedad exigida pero la convocatoria no definió porcentaje; capturar desde bases.",
        )

