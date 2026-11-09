# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Motor jurídico — determinación de procedimientos y validaciones normativas.

Los umbrales y el marco legal aplicable viven en base de datos
(procedure_thresholds + jurisdiction_profiles + legal_rules). Este motor
solo contiene lógica de evaluación: nunca inventa montos ni artículos.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode, MegalodonException
from app.engines.procurement.threshold_resolver import ThresholdDecision, ThresholdResolver


class TipoProcedimiento(str, Enum):
    ADJUDICACION_DIRECTA = "ADJUDICACION_DIRECTA"
    INVITACION_TRES = "INVITACION_TRES"
    LICITACION_PUBLICA = "LICITACION_PUBLICA"
    SIN_DETERMINAR = "SIN_DETERMINAR"


class TipoContratacion(str, Enum):
    OBRA_PUBLICA = "OBRA_PUBLICA"
    ADQUISICION = "ADQUISICION"
    SERVICIO_RELACIONADO = "SERVICIO_RELACIONADO"
    ARRENDAMIENTO = "ARRENDAMIENTO"

    def a_tipo_umbral(self) -> str:
        if self == TipoContratacion.OBRA_PUBLICA:
            return "OBRA_PUBLICA"
        return "ADQUISICIONES_SERVICIOS"


@dataclass
class Requisito:
    codigo: str
    descripcion: str
    obligatorio: bool
    documento_soporte: str
    articulo: str
    ley: str


@dataclass
class MarcoLegal:
    ley: str
    articulos: list[str]
    reglamento: Optional[str] = None


@dataclass
class ResultadoJuridico:
    procedimiento: TipoProcedimiento
    tipo_contratacion: TipoContratacion
    jurisdiction_code: str
    marcos_legales: list[MarcoLegal]
    requisitos: list[Requisito]
    umbrales: dict[str, Optional[float]]
    observaciones: list[str]
    valido: bool
    datos_verificados: bool
    es_candidato: bool = False
    fuente_umbral: Optional[str] = None
    ejercicio_fiscal: int = 2026
    threshold_meta: Optional[dict[str, Any]] = None


class MotorJuridico:
    """Evalúa procedimiento a partir de umbrales persistidos en DB."""

    def __init__(self) -> None:
        self._thresholds = ThresholdResolver()

    async def jurisdicciones_disponibles(
        self,
        db: AsyncSession,
        tenant_id: UUID | str,
        ejercicio_fiscal: int | None = None,
    ) -> list[dict[str, object]]:
        return await self._thresholds.list_available(
            db, tenant_id=tenant_id, ejercicio_fiscal=ejercicio_fiscal
        )

    async def determinar_procedimiento(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID | str,
        monto: float,
        tipo_contratacion: TipoContratacion,
        jurisdiction_code: str,
        ejercicio_fiscal: int = 2026,
        presupuesto_dependencia_miles: float | None = None,
        es_servicio_relacionado: bool = False,
    ) -> ResultadoJuridico:
        if monto <= 0:
            raise MegalodonException(ErrorCode.JURIDICO_GENERICO, "El monto debe ser mayor a cero")

        tipo_umbral = (
            "OBRA_PUBLICA"
            if tipo_contratacion == TipoContratacion.OBRA_PUBLICA
            else tipo_contratacion.a_tipo_umbral()
        )
        decision = await self._thresholds.resolve(
            db,
            tenant_id=tenant_id,
            jurisdiction_code=jurisdiction_code,
            tipo_contratacion=tipo_umbral,
            ejercicio_fiscal=ejercicio_fiscal,
            presupuesto_dependencia_miles=presupuesto_dependencia_miles,
            es_servicio_relacionado=es_servicio_relacionado
            or tipo_contratacion == TipoContratacion.SERVICIO_RELACIONADO,
        )

        if not decision.found or decision.band is None:
            return self._sin_determinar(
                tipo_contratacion=tipo_contratacion,
                jurisdiction_code=jurisdiction_code,
                ejercicio_fiscal=ejercicio_fiscal,
                decision=decision,
                motivo=decision.notes or "Sin umbral aplicable en DB.",
            )
        if not decision.datos_verificados:
            return self._sin_determinar(
                tipo_contratacion=tipo_contratacion,
                jurisdiction_code=jurisdiction_code,
                ejercicio_fiscal=ejercicio_fiscal,
                decision=decision,
                motivo=(
                    "El umbral existe pero no está VERIFICADO contra una fuente primaria; "
                    "la determinación automática queda bloqueada."
                ),
            )

        umbral_ad = decision.adjudicacion_directa_pesos
        umbral_inv = decision.invitacion_restringida_pesos
        observaciones: list[str] = []
        if decision.notes:
            observaciones.append(decision.notes)
        if decision.es_candidato:
            observaciones.append(
                "Umbral en estado CANDIDATO: no fundamentar cumplimiento real sin confirmar fuente primaria."
            )

        if umbral_ad is not None and monto <= umbral_ad:
            procedimiento = TipoProcedimiento.ADJUDICACION_DIRECTA
            observaciones.append(
                f"Monto ${monto:,.2f} dentro del umbral de adjudicación directa (${umbral_ad:,.2f})."
            )
        elif umbral_inv is not None and monto <= umbral_inv:
            procedimiento = TipoProcedimiento.INVITACION_TRES
            observaciones.append(
                f"Monto ${monto:,.2f} dentro del umbral de invitación a cuando menos tres personas (${umbral_inv:,.2f})."
            )
        else:
            procedimiento = TipoProcedimiento.LICITACION_PUBLICA
            techo = umbral_inv if umbral_inv is not None else umbral_ad
            if techo is not None:
                observaciones.append(
                    f"Monto ${monto:,.2f} supera ${techo:,.2f}; corresponde licitación pública."
                )
            else:
                observaciones.append("Sin techo de invitación; corresponde licitación pública por regla general.")

        marcos = self._marcos(procedimiento, decision)
        requisitos = self._requisitos_base(procedimiento, tipo_contratacion, decision)

        return ResultadoJuridico(
            procedimiento=procedimiento,
            tipo_contratacion=tipo_contratacion,
            jurisdiction_code=decision.jurisdiction_code,
            marcos_legales=marcos,
            requisitos=requisitos,
            umbrales={"adjudicacion_directa": umbral_ad, "invitacion_tres": umbral_inv},
            observaciones=observaciones,
            valido=True,
            datos_verificados=decision.datos_verificados,
            es_candidato=decision.es_candidato,
            fuente_umbral=decision.fuente,
            ejercicio_fiscal=ejercicio_fiscal,
            threshold_meta={
                "estado_dato": decision.estado_dato,
                "ley": decision.ley,
                "articulo_referencia": decision.articulo_referencia,
                "fuente_uri": decision.fuente_uri,
                "inherited_from": list(decision.inherited_from),
                "band": {
                    "presupuesto_min_miles": decision.band.presupuesto_min_miles,
                    "presupuesto_max_miles": decision.band.presupuesto_max_miles,
                    "adjudicacion_directa_miles": decision.band.adjudicacion_directa_miles,
                    "invitacion_restringida_miles": decision.band.invitacion_restringida_miles,
                },
            },
        )

    async def validar_monto(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID | str,
        monto: float,
        tipo_contratacion: TipoContratacion,
        jurisdiction_code: str,
        ejercicio_fiscal: int = 2026,
        presupuesto_dependencia_miles: float | None = None,
        margen_riesgo_fraccionamiento: float = 0.05,
    ) -> dict[str, Any]:
        resultado = await self.determinar_procedimiento(
            db,
            tenant_id=tenant_id,
            monto=monto,
            tipo_contratacion=tipo_contratacion,
            jurisdiction_code=jurisdiction_code,
            ejercicio_fiscal=ejercicio_fiscal,
            presupuesto_dependencia_miles=presupuesto_dependencia_miles,
        )
        if not resultado.valido:
            return {
                "valido": False,
                "procedimiento": resultado.procedimiento.value,
                "umbrales": resultado.umbrales,
                "margen_al_siguiente_umbral": None,
                "cerca_de_umbral": False,
                "observaciones": resultado.observaciones,
                "datos_verificados": False,
                "es_candidato": resultado.es_candidato,
                "fuente_umbral": resultado.fuente_umbral,
            }

        umbral_ad = resultado.umbrales.get("adjudicacion_directa")
        umbral_inv = resultado.umbrales.get("invitacion_tres")
        if resultado.procedimiento == TipoProcedimiento.ADJUDICACION_DIRECTA:
            umbral_aplicable = umbral_ad
        elif resultado.procedimiento == TipoProcedimiento.INVITACION_TRES:
            umbral_aplicable = umbral_inv
        else:
            umbral_aplicable = None

        cerca = False
        margen = None
        observaciones = list(resultado.observaciones)
        if umbral_aplicable is not None:
            margen = umbral_aplicable - monto
            if 0 <= margen <= umbral_aplicable * margen_riesgo_fraccionamiento:
                cerca = True
                observaciones.append(
                    f"El monto está a ${margen:,.2f} del umbral ${umbral_aplicable:,.2f} "
                    "(posible señal de fraccionamiento)."
                )

        return {
            "valido": True,
            "procedimiento": resultado.procedimiento.value,
            "umbrales": resultado.umbrales,
            "margen_al_siguiente_umbral": margen,
            "cerca_de_umbral": cerca,
            "observaciones": observaciones,
            "datos_verificados": resultado.datos_verificados,
            "es_candidato": resultado.es_candidato,
            "fuente_umbral": resultado.fuente_umbral,
            "threshold_meta": resultado.threshold_meta,
        }

    def obtener_requisitos(
        self,
        procedimiento: TipoProcedimiento,
        tipo_contratacion: TipoContratacion,
    ) -> dict[str, Any]:
        """Checklist estructural mínimo. Los requisitos jurídicos vinculantes
        se derivan desde LegalRule en el motor de procurement; este método
        solo expone la lista operativa de presentación cuando aún no hay
        tender materializado.
        """
        decision = ThresholdDecision(
            found=False,
            jurisdiction_code="",
            tipo_contratacion=tipo_contratacion.a_tipo_umbral(),
            ejercicio_fiscal=0,
            band=None,
            ley=None,
            articulo_referencia=None,
            fuente=None,
            fuente_uri=None,
            estado_dato="PENDIENTE",
            datos_verificados=False,
            es_candidato=False,
            notes=None,
            inherited_from=(),
        )
        return {
            "procedimiento": procedimiento.value,
            "requisitos": self._requisitos_base(procedimiento, tipo_contratacion, decision),
        }

    def _sin_determinar(
        self,
        *,
        tipo_contratacion: TipoContratacion,
        jurisdiction_code: str,
        ejercicio_fiscal: int,
        decision: ThresholdDecision,
        motivo: str,
    ) -> ResultadoJuridico:
        return ResultadoJuridico(
            procedimiento=TipoProcedimiento.SIN_DETERMINAR,
            tipo_contratacion=tipo_contratacion,
            jurisdiction_code=jurisdiction_code,
            marcos_legales=[],
            requisitos=[],
            umbrales={"adjudicacion_directa": None, "invitacion_tres": None},
            observaciones=[motivo],
            valido=False,
            datos_verificados=False,
            es_candidato=decision.es_candidato,
            fuente_umbral=decision.fuente,
            ejercicio_fiscal=ejercicio_fiscal,
            threshold_meta={
                "estado_dato": decision.estado_dato,
                "inherited_from": list(decision.inherited_from),
            },
        )

    @staticmethod
    def _marcos(procedimiento: TipoProcedimiento, decision: ThresholdDecision) -> list[MarcoLegal]:
        ley = decision.ley or "Régimen aplicable según JurisdictionProfile"
        articulos = [decision.articulo_referencia] if decision.articulo_referencia else []
        if procedimiento == TipoProcedimiento.LICITACION_PUBLICA and not articulos:
            articulos = ["Regla general de licitación pública"]
        return [MarcoLegal(ley=ley, articulos=articulos)]

    @staticmethod
    def _requisitos_base(
        procedimiento: TipoProcedimiento,
        tipo: TipoContratacion,
        decision: ThresholdDecision,
    ) -> list[Requisito]:
        ley = decision.ley or ("LOPSRM" if tipo == TipoContratacion.OBRA_PUBLICA else "LAASSP")
        base = [
            Requisito(
                codigo="CONSTANCIA_SITUACION_FISCAL",
                descripcion="Constancia de situación fiscal vigente",
                obligatorio=True,
                documento_soporte="CSF SAT",
                articulo="Requisito administrativo general",
                ley=ley,
            ),
            Requisito(
                codigo="OPINION_CUMPLIMIENTO_IMSS",
                descripcion="Opinión de cumplimiento de obligaciones en materia de seguridad social",
                obligatorio=True,
                documento_soporte="Opinión IMSS",
                articulo="Requisito administrativo general",
                ley=ley,
            ),
            Requisito(
                codigo="OPINION_CUMPLIMIENTO_INFONAVIT",
                descripcion="Constancia de situación fiscal de créditos INFONAVIT",
                obligatorio=True,
                documento_soporte="Opinión INFONAVIT",
                articulo="Requisito administrativo general",
                ley=ley,
            ),
        ]
        if procedimiento == TipoProcedimiento.LICITACION_PUBLICA:
            base.append(
                Requisito(
                    codigo="GARANTIA_SERIEDAD",
                    descripcion="Garantía de seriedad de la proposición cuando las bases la exijan",
                    obligatorio=False,
                    documento_soporte="Fianza / cheque certificado",
                    articulo=decision.articulo_referencia or "Bases de la convocatoria",
                    ley=ley,
                )
            )
        if tipo == TipoContratacion.OBRA_PUBLICA:
            base.append(
                Requisito(
                    codigo="CAPACIDAD_TECNICA",
                    descripcion="Acreditación de capacidad técnica y experiencia en obras similares",
                    obligatorio=True,
                    documento_soporte="Currículum / contratos previos",
                    articulo=decision.articulo_referencia or "Bases técnicas",
                    ley=ley,
                )
            )
        return base
