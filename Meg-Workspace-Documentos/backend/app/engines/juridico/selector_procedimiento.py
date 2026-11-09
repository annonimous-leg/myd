# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Selector de procedimiento — decide LP / invitación / adjudicación directa.

La lógica de monto usa umbrales de DB vía MotorJuridico. Las excepciones
legales (proveedor único, emergencia, etc.) se evalúan solo cuando el
caller aporta el código de excepción y una justificación suficiente;
los fundamentos textuales de cada excepción también pueden venir de
LegalRule (domain=PROCEDURE_EXCEPTION) cuando existan en DB.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.juridico.motor_juridico import MotorJuridico, TipoContratacion, TipoProcedimiento
from app.models.procurement import LegalRule


class ResultadoSeleccion(str, Enum):
    LICITACION_PUBLICA = "LICITACION_PUBLICA"
    INVITACION_TRES = "INVITACION_TRES"
    ADJUDICACION_DIRECTA = "ADJUDICACION_DIRECTA"
    REQUIERE_JUSTIFICACION = "REQUIERE_JUSTIFICACION"


@dataclass
class JustificacionLegal:
    fundamento: str
    articulo: str
    ley: str
    requisitos: list[str]
    riesgo_compliance: str


@dataclass
class ResultadoSelector:
    procedimiento: ResultadoSeleccion
    justificacion: JustificacionLegal
    monto: float
    umbral_adjudicacion_directa: Optional[float]
    umbral_invitacion: Optional[float]
    requiere_investigacion_mercado: bool
    observaciones: list[str]
    datos_verificados: bool = False
    es_candidato: bool = False
    fuente_umbral: Optional[str] = None
    threshold_meta: Optional[dict[str, Any]] = None


class SelectorProcedimiento:
    """Máquina de reglas auditable. No inventa umbrales ni excepciones."""

    MIN_JUSTIFICACION_CHARS = 50

    def __init__(self) -> None:
        self.motor = MotorJuridico()

    async def seleccionar(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID | str,
        monto: float,
        es_obra_publica: bool,
        jurisdiction_code: str,
        presupuesto_dependencia_miles: float | None = None,
        excepcion_legal: str | None = None,
        justificacion_excepcion: str | None = None,
        investigacion_mercado_realizada: bool = False,
        ejercicio_fiscal: int = 2026,
    ) -> ResultadoSelector:
        tipo = TipoContratacion.OBRA_PUBLICA if es_obra_publica else TipoContratacion.ADQUISICION
        resultado = await self.motor.determinar_procedimiento(
            db,
            tenant_id=tenant_id,
            monto=monto,
            tipo_contratacion=tipo,
            jurisdiction_code=jurisdiction_code,
            ejercicio_fiscal=ejercicio_fiscal,
            presupuesto_dependencia_miles=presupuesto_dependencia_miles,
        )

        umbral_directa = resultado.umbrales.get("adjudicacion_directa")
        umbral_invitacion = resultado.umbrales.get("invitacion_tres")
        observaciones = list(resultado.observaciones)

        if excepcion_legal:
            return await self._por_excepcion(
                db,
                tenant_id=tenant_id,
                jurisdiction_code=jurisdiction_code,
                excepcion_legal=excepcion_legal,
                justificacion_excepcion=justificacion_excepcion,
                investigacion_mercado_realizada=investigacion_mercado_realizada,
                monto=monto,
                umbral_directa=umbral_directa,
                umbral_invitacion=umbral_invitacion,
                observaciones=observaciones,
                resultado_base=resultado,
            )

        if not resultado.valido or resultado.procedimiento == TipoProcedimiento.SIN_DETERMINAR:
            return ResultadoSelector(
                procedimiento=ResultadoSeleccion.REQUIERE_JUSTIFICACION,
                justificacion=JustificacionLegal(
                    fundamento="No hay umbrales activos en DB para decidir el procedimiento automáticamente.",
                    articulo=str((resultado.threshold_meta or {}).get("articulo_referencia") or "N/D"),
                    ley=str((resultado.threshold_meta or {}).get("ley") or "N/D"),
                    requisitos=[
                        "Registrar procedure_thresholds para la jurisdicción/ejercicio",
                        "Confirmar presupuesto autorizado de la dependencia cuando el Anexo sea escalonado",
                    ],
                    riesgo_compliance="ALTO",
                ),
                monto=monto,
                umbral_adjudicacion_directa=umbral_directa,
                umbral_invitacion=umbral_invitacion,
                requiere_investigacion_mercado=True,
                observaciones=observaciones,
                datos_verificados=False,
                es_candidato=resultado.es_candidato,
                fuente_umbral=resultado.fuente_umbral,
                threshold_meta=resultado.threshold_meta,
            )

        mapping = {
            TipoProcedimiento.ADJUDICACION_DIRECTA: ResultadoSeleccion.ADJUDICACION_DIRECTA,
            TipoProcedimiento.INVITACION_TRES: ResultadoSeleccion.INVITACION_TRES,
            TipoProcedimiento.LICITACION_PUBLICA: ResultadoSeleccion.LICITACION_PUBLICA,
        }
        procedimiento = mapping[resultado.procedimiento]
        ley = str((resultado.threshold_meta or {}).get("ley") or "Régimen aplicable")
        articulo = str((resultado.threshold_meta or {}).get("articulo_referencia") or "Regla de umbral")

        if procedimiento == ResultadoSeleccion.LICITACION_PUBLICA:
            just = JustificacionLegal(
                fundamento="La licitación pública es la regla general cuando el monto supera los umbrales de excepción.",
                articulo=articulo,
                ley=ley,
                requisitos=["Publicación de convocatoria", "Bases completas", "Junta de aclaraciones cuando proceda"],
                riesgo_compliance="BAJO" if resultado.datos_verificados else "MEDIO",
            )
            requiere_im = True
        elif procedimiento == ResultadoSeleccion.INVITACION_TRES:
            just = JustificacionLegal(
                fundamento="El monto se ubica en el tramo de invitación a cuando menos tres personas según umbral registrado.",
                articulo=articulo,
                ley=ley,
                requisitos=["Invitar al menos a tres proveedores", "Documentar criterios de selección"],
                riesgo_compliance="MEDIO" if resultado.datos_verificados else "ALTO",
            )
            requiere_im = True
        else:
            just = JustificacionLegal(
                fundamento="El monto se ubica en el tramo de adjudicación directa según umbral registrado.",
                articulo=articulo,
                ley=ley,
                requisitos=["Dictamen de procedencia", "Investigación de mercado documentada"],
                riesgo_compliance="MEDIO" if resultado.datos_verificados else "ALTO",
            )
            requiere_im = True

        if requiere_im and not investigacion_mercado_realizada:
            observaciones.append(
                "No se documentó investigación de mercado; el expediente queda expuesto a observación de auditoría."
            )

        return ResultadoSelector(
            procedimiento=procedimiento,
            justificacion=just,
            monto=monto,
            umbral_adjudicacion_directa=umbral_directa,
            umbral_invitacion=umbral_invitacion,
            requiere_investigacion_mercado=requiere_im,
            observaciones=observaciones,
            datos_verificados=resultado.datos_verificados,
            es_candidato=resultado.es_candidato,
            fuente_umbral=resultado.fuente_umbral,
            threshold_meta=resultado.threshold_meta,
        )

    async def _por_excepcion(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID | str,
        jurisdiction_code: str,
        excepcion_legal: str,
        justificacion_excepcion: str | None,
        investigacion_mercado_realizada: bool,
        monto: float,
        umbral_directa: float | None,
        umbral_invitacion: float | None,
        observaciones: list[str],
        resultado_base: Any,
    ) -> ResultadoSelector:
        codigo = str(excepcion_legal).strip().upper()
        justificacion = (justificacion_excepcion or "").strip()
        if len(justificacion) < self.MIN_JUSTIFICACION_CHARS:
            return ResultadoSelector(
                procedimiento=ResultadoSeleccion.REQUIERE_JUSTIFICACION,
                justificacion=JustificacionLegal(
                    fundamento="La excepción legal exige justificación motivada y suficiente.",
                    articulo="Excepción legal invocada",
                    ley="Régimen aplicable",
                    requisitos=[
                        f"Justificación de al menos {self.MIN_JUSTIFICACION_CHARS} caracteres",
                        "Fundamento normativo de la excepción",
                    ],
                    riesgo_compliance="ALTO",
                ),
                monto=monto,
                umbral_adjudicacion_directa=umbral_directa,
                umbral_invitacion=umbral_invitacion,
                requiere_investigacion_mercado=True,
                observaciones=observaciones + ["Justificación de excepción insuficiente."],
                datos_verificados=False,
                es_candidato=resultado_base.es_candidato,
                fuente_umbral=resultado_base.fuente_umbral,
                threshold_meta=resultado_base.threshold_meta,
            )

        rule = await self._cargar_excepcion(db, tenant_id, jurisdiction_code, codigo)
        if rule is None:
            return ResultadoSelector(
                procedimiento=ResultadoSeleccion.REQUIERE_JUSTIFICACION,
                justificacion=JustificacionLegal(
                    fundamento=(
                        f"La excepción '{codigo}' no está registrada como LegalRule activa "
                        f"(domain=PROCEDURE_EXCEPTION) para la jurisdicción."
                    ),
                    articulo="N/D",
                    ley="N/D",
                    requisitos=["Registrar la excepción en legal_rules antes de invocarla"],
                    riesgo_compliance="ALTO",
                ),
                monto=monto,
                umbral_adjudicacion_directa=umbral_directa,
                umbral_invitacion=umbral_invitacion,
                requiere_investigacion_mercado=True,
                observaciones=observaciones + [f"Excepción {codigo} no encontrada en DB."],
                datos_verificados=False,
                es_candidato=resultado_base.es_candidato,
                fuente_umbral=resultado_base.fuente_umbral,
                threshold_meta=resultado_base.threshold_meta,
            )

        req = rule.requirement or {}
        fund = str(req.get("fundamento") or req.get("description") or f"Excepción {codigo}")
        articulo = str(req.get("citation") or req.get("articulo") or rule.rule_id)
        ley = str(req.get("ley") or rule.domain)
        requisitos = [str(x) for x in (req.get("requisitos") or req.get("evidence_required") or [])]
        if not investigacion_mercado_realizada and bool(req.get("requiere_investigacion_mercado", True)):
            observaciones.append("La excepción exige investigación de mercado documentada.")

        # Procedimiento desde la regla si declara allowed_procedure / procedimiento;
        # default AD solo si la regla no especifica (corpus LOPSRM 42 / LAASSP 54).
        proc_raw = str(
            req.get("procedimiento")
            or req.get("allowed_procedure")
            or (req.get("params") or {}).get("procedimiento")
            or "ADJUDICACION_DIRECTA"
        ).upper().strip()
        proc_map = {
            "ADJUDICACION_DIRECTA": ResultadoSeleccion.ADJUDICACION_DIRECTA,
            "ADJUDICACION": ResultadoSeleccion.ADJUDICACION_DIRECTA,
            "INVITACION_TRES": ResultadoSeleccion.INVITACION_TRES,
            "INVITACION": ResultadoSeleccion.INVITACION_TRES,
            "LICITACION_PUBLICA": ResultadoSeleccion.LICITACION_PUBLICA,
        }
        procedimiento_ex = proc_map.get(proc_raw, ResultadoSeleccion.ADJUDICACION_DIRECTA)

        return ResultadoSelector(
            procedimiento=procedimiento_ex,
            justificacion=JustificacionLegal(
                fundamento=fund,
                articulo=articulo,
                ley=ley,
                requisitos=requisitos or ["Dictamen de procedencia", "Expediente de justificación"],
                riesgo_compliance=str(req.get("riesgo_compliance") or "ALTO"),
            ),
            monto=monto,
            umbral_adjudicacion_directa=umbral_directa,
            umbral_invitacion=umbral_invitacion,
            requiere_investigacion_mercado=bool(req.get("requiere_investigacion_mercado", True)),
            observaciones=observaciones + [f"Excepción aplicada: {codigo}", f"Justificación: {justificacion[:200]}"],
            datos_verificados=bool(rule.article_id),
            es_candidato=False,
            fuente_umbral=resultado_base.fuente_umbral,
            threshold_meta={
                **(resultado_base.threshold_meta or {}),
                "exception_rule_id": rule.rule_id,
                "exception_rule_version": rule.rule_version,
            },
        )

    async def _cargar_excepcion(
        self,
        db: AsyncSession,
        tenant_id: UUID | str,
        jurisdiction_code: str,
        codigo: str,
    ) -> LegalRule | None:
        from app.engines.procurement.jurisdiction import JurisdictionResolver

        chain = await JurisdictionResolver().inheritance_codes(db, tenant_id, jurisdiction_code)
        row = await db.scalar(
            select(LegalRule)
            .where(
                LegalRule.active.is_(True),
                LegalRule.domain == "PROCEDURE_EXCEPTION",
                LegalRule.rule_id == codigo,
                or_(LegalRule.jurisdiction_code.in_(list(chain)), LegalRule.jurisdiction_code.is_(None)),
                or_(LegalRule.tenant_id == tenant_id, LegalRule.tenant_id.is_(None)),
            )
            .order_by(LegalRule.rule_version.desc(), LegalRule.tenant_id.desc().nullslast())
        )
        return row

    def validar_transicion_estado(
        self,
        estado_actual: str,
        nuevo_estado: str,
        datos: Optional[dict] = None,
    ) -> tuple[bool, list[str]]:
        transiciones_validas = {
            "PLANEACION": ["INVESTIGACION_MERCADO", "CANCELADA"],
            "INVESTIGACION_MERCADO": ["SELECCION_PROCEDIMIENTO", "CANCELADA"],
            "SELECCION_PROCEDIMIENTO": ["CONVOCATORIA", "ADJUDICACION_DIRECTA", "CANCELADA"],
            "CONVOCATORIA": ["JUNTA_ACLARACIONES", "RECEPCION_PROPUESTAS", "CANCELADA"],
            "JUNTA_ACLARACIONES": ["RECEPCION_PROPUESTAS", "CANCELADA"],
            "RECEPCION_PROPUESTAS": ["APERTURA", "DESIERTA", "CANCELADA"],
            "APERTURA": ["EVALUACION", "DESIERTA", "CANCELADA"],
            "EVALUACION": ["FALLO", "DESIERTA", "CANCELADA"],
            "FALLO": ["ADJUDICACION", "DESIERTA", "CANCELADA"],
            "ADJUDICACION": ["CONTRATO", "CANCELADA"],
            "CONTRATO": ["CERRADA", "CANCELADA"],
            "DESIERTA": ["CERRADA", "PLANEACION"],
            "CANCELADA": ["CERRADA"],
            "CERRADA": [],
        }
        permitidos = transiciones_validas.get(estado_actual, [])
        if nuevo_estado in permitidos:
            return True, []
        return False, [
            f"Transición ilegal: {estado_actual} → {nuevo_estado}. Permitidos: {permitidos}"
        ]
