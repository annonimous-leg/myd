from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.procurement.jurisdiction import JurisdictionResolver
from app.models.procurement import ProcedureThreshold


@dataclass(frozen=True)
class ThresholdBand:
    presupuesto_min_miles: float
    presupuesto_max_miles: float | None
    adjudicacion_directa_miles: float
    invitacion_restringida_miles: float
    adjudicacion_directa_servicio_miles: float | None
    invitacion_restringida_servicio_miles: float | None


@dataclass(frozen=True)
class ThresholdDecision:
    found: bool
    jurisdiction_code: str
    tipo_contratacion: str
    ejercicio_fiscal: int
    band: ThresholdBand | None
    ley: str | None
    articulo_referencia: str | None
    fuente: str | None
    fuente_uri: str | None
    estado_dato: str
    datos_verificados: bool
    es_candidato: bool
    notes: str | None
    inherited_from: tuple[str, ...]

    @property
    def adjudicacion_directa_pesos(self) -> float | None:
        if self.band is None:
            return None
        return float(self.band.adjudicacion_directa_miles) * 1000.0

    @property
    def invitacion_restringida_pesos(self) -> float | None:
        if self.band is None:
            return None
        return float(self.band.invitacion_restringida_miles) * 1000.0


class ThresholdResolver:
    """Resuelve umbrales únicamente desde procedure_thresholds + herencia de jurisdicción.

    Fail-closed: si no hay tramo activo para el contexto, found=False y el
    caller debe negar la determinación automática del procedimiento.
    """

    def __init__(self) -> None:
        self._jurisdiction = JurisdictionResolver()

    async def resolve(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID | str,
        jurisdiction_code: str,
        tipo_contratacion: str,
        ejercicio_fiscal: int,
        presupuesto_dependencia_miles: float | None = None,
        es_servicio_relacionado: bool = False,
    ) -> ThresholdDecision:
        code = str(jurisdiction_code).upper().strip()
        tipo = str(tipo_contratacion).upper().strip()
        chain = await self._jurisdiction.inheritance_codes(db, tenant_id, code)

        rows = (
            await db.execute(
                select(ProcedureThreshold)
                .where(
                    ProcedureThreshold.active.is_(True),
                    ProcedureThreshold.jurisdiction_code.in_(list(chain)),
                    ProcedureThreshold.tipo_contratacion == tipo,
                    ProcedureThreshold.ejercicio_fiscal == int(ejercicio_fiscal),
                    or_(
                        ProcedureThreshold.tenant_id == tenant_id,
                        ProcedureThreshold.tenant_id.is_(None),
                    ),
                )
                .order_by(
                    ProcedureThreshold.tenant_id.desc().nullslast(),
                    ProcedureThreshold.presupuesto_min_miles.asc(),
                )
            )
        ).scalars().all()

        if not rows:
            return ThresholdDecision(
                found=False,
                jurisdiction_code=code,
                tipo_contratacion=tipo,
                ejercicio_fiscal=int(ejercicio_fiscal),
                band=None,
                ley=None,
                articulo_referencia=None,
                fuente=None,
                fuente_uri=None,
                estado_dato="PENDIENTE",
                datos_verificados=False,
                es_candidato=False,
                notes="No existen umbrales activos en DB para la jurisdicción/ejercicio/tipo solicitados.",
                inherited_from=chain,
            )

        # Prefer exact jurisdiction match before inherited parents.
        by_code: dict[str, list[ProcedureThreshold]] = {}
        for row in rows:
            by_code.setdefault(row.jurisdiction_code.upper(), []).append(row)

        selected_rows: list[ProcedureThreshold] | None = None
        selected_code = code
        for candidate in chain:
            if candidate in by_code:
                selected_rows = by_code[candidate]
                selected_code = candidate
                break
        if selected_rows is None:
            selected_rows = rows
            selected_code = rows[0].jurisdiction_code.upper()

        band_row = self._pick_tramo(selected_rows, presupuesto_dependencia_miles)
        if band_row is None:
            return ThresholdDecision(
                found=False,
                jurisdiction_code=selected_code,
                tipo_contratacion=tipo,
                ejercicio_fiscal=int(ejercicio_fiscal),
                band=None,
                ley=selected_rows[0].ley,
                articulo_referencia=selected_rows[0].articulo_referencia,
                fuente=selected_rows[0].fuente,
                fuente_uri=selected_rows[0].fuente_uri,
                estado_dato=str(selected_rows[0].estado_dato).upper(),
                datos_verificados=False,
                es_candidato=False,
                notes=(
                    "Existen umbrales en DB pero falta presupuesto_dependencia_miles "
                    "para seleccionar el tramo escalonado, o el monto no cae en ningún tramo."
                ),
                inherited_from=chain,
            )

        ad_miles = float(band_row.adjudicacion_directa_miles)
        inv_miles = float(band_row.invitacion_restringida_miles)
        if es_servicio_relacionado:
            if band_row.adjudicacion_directa_servicio_miles is not None:
                ad_miles = float(band_row.adjudicacion_directa_servicio_miles)
            if band_row.invitacion_restringida_servicio_miles is not None:
                inv_miles = float(band_row.invitacion_restringida_servicio_miles)

        estado = str(band_row.estado_dato or "PENDIENTE").upper()
        return ThresholdDecision(
            found=True,
            jurisdiction_code=selected_code,
            tipo_contratacion=tipo,
            ejercicio_fiscal=int(ejercicio_fiscal),
            band=ThresholdBand(
                presupuesto_min_miles=float(band_row.presupuesto_min_miles),
                presupuesto_max_miles=(
                    float(band_row.presupuesto_max_miles)
                    if band_row.presupuesto_max_miles is not None
                    else None
                ),
                adjudicacion_directa_miles=ad_miles,
                invitacion_restringida_miles=inv_miles,
                adjudicacion_directa_servicio_miles=(
                    float(band_row.adjudicacion_directa_servicio_miles)
                    if band_row.adjudicacion_directa_servicio_miles is not None
                    else None
                ),
                invitacion_restringida_servicio_miles=(
                    float(band_row.invitacion_restringida_servicio_miles)
                    if band_row.invitacion_restringida_servicio_miles is not None
                    else None
                ),
            ),
            ley=band_row.ley,
            articulo_referencia=band_row.articulo_referencia,
            fuente=band_row.fuente,
            fuente_uri=band_row.fuente_uri,
            estado_dato=estado,
            datos_verificados=(estado == "VERIFICADO"),
            es_candidato=(estado == "CANDIDATO"),
            notes=band_row.notas,
            inherited_from=chain,
        )

    @staticmethod
    def _pick_tramo(
        rows: list[ProcedureThreshold],
        presupuesto_dependencia_miles: float | None,
    ) -> ProcedureThreshold | None:
        if not rows:
            return None
        # Single-band jurisdictions (no escalonado): apply directly.
        if len(rows) == 1 and rows[0].presupuesto_max_miles is None and float(rows[0].presupuesto_min_miles or 0) == 0:
            return rows[0]
        if presupuesto_dependencia_miles is None:
            # Escalated table requires the dependencia budget. Fail closed.
            if any(r.presupuesto_max_miles is not None or float(r.presupuesto_min_miles or 0) > 0 for r in rows):
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
        # Above last ceiling → last open-ended band if present.
        for row in reversed(ordered):
            if row.presupuesto_max_miles is None:
                return row
        return None

    async def list_available(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID | str,
        ejercicio_fiscal: int | None = None,
    ) -> list[dict[str, Any]]:
        query = select(ProcedureThreshold).where(
            ProcedureThreshold.active.is_(True),
            or_(ProcedureThreshold.tenant_id == tenant_id, ProcedureThreshold.tenant_id.is_(None)),
        )
        if ejercicio_fiscal is not None:
            query = query.where(ProcedureThreshold.ejercicio_fiscal == int(ejercicio_fiscal))
        rows = (await db.execute(query.order_by(
            ProcedureThreshold.jurisdiction_code,
            ProcedureThreshold.tipo_contratacion,
            ProcedureThreshold.ejercicio_fiscal,
            ProcedureThreshold.presupuesto_min_miles,
        ))).scalars().all()

        summary: dict[tuple[str, int], str] = {}
        rank = {"PENDIENTE": 0, "CANDIDATO": 1, "VERIFICADO": 2}
        for row in rows:
            key = (row.jurisdiction_code.upper(), int(row.ejercicio_fiscal))
            current = summary.get(key, "PENDIENTE")
            estado = str(row.estado_dato or "PENDIENTE").upper()
            if rank.get(estado, 0) >= rank.get(current, 0):
                summary[key] = estado
        return [
            {"jurisdiction_code": code, "ejercicio_fiscal": year, "estado_dato": estado}
            for (code, year), estado in sorted(summary.items())
        ]
