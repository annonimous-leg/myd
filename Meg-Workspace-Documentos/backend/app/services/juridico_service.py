# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
JuridicoService — orquestación del motor jurídico contra datos de DB.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.juridico.motor_juridico import MotorJuridico, TipoContratacion, TipoProcedimiento
from app.engines.juridico.selector_procedimiento import ResultadoSeleccion, SelectorProcedimiento


class JuridicoService:
    """Consultas y validaciones jurídicas 100% respaldadas por DB."""

    def __init__(self, db: AsyncSession, tenant_id: UUID | str | None = None):
        self.db = db
        self.tenant_id = tenant_id
        self.motor = MotorJuridico()
        self.selector = SelectorProcedimiento()

    def _require_tenant(self, tenant_id: UUID | str | None = None) -> UUID | str:
        tid = tenant_id if tenant_id is not None else self.tenant_id
        if tid is None:
            raise ValueError("tenant_id es obligatorio para resolver umbrales y excepciones desde DB.")
        return tid

    async def determinar_procedimiento(
        self,
        monto: float,
        tipo_contratacion: str,
        es_obra_publica: bool = True,
        jurisdiction_code: str = "MX-FED-OBRA",
        ejercicio_fiscal: int = 2026,
        presupuesto_dependencia_miles: float | None = None,
        excepcion_legal: Optional[str] = None,
        justificacion_excepcion: Optional[str] = None,
        investigacion_mercado_realizada: bool = False,
        tenant_id: UUID | str | None = None,
        # compat legacy param name
        jurisdiccion: str | None = None,
    ) -> dict[str, Any]:
        tid = self._require_tenant(tenant_id)
        code = (jurisdiction_code or jurisdiccion or "MX-FED-OBRA").upper()

        if excepcion_legal or True:
            # Unified path: selector always owns the decision surface.
            resultado = await self.selector.seleccionar(
                self.db,
                tenant_id=tid,
                monto=monto,
                es_obra_publica=es_obra_publica,
                jurisdiction_code=code,
                presupuesto_dependencia_miles=presupuesto_dependencia_miles,
                excepcion_legal=excepcion_legal,
                justificacion_excepcion=justificacion_excepcion,
                investigacion_mercado_realizada=investigacion_mercado_realizada,
                ejercicio_fiscal=ejercicio_fiscal,
            )
            return {
                "procedimiento": resultado.procedimiento.value,
                "justificacion": {
                    "fundamento": resultado.justificacion.fundamento,
                    "articulo": resultado.justificacion.articulo,
                    "ley": resultado.justificacion.ley,
                    "requisitos": resultado.justificacion.requisitos,
                    "riesgo_compliance": resultado.justificacion.riesgo_compliance,
                },
                "monto": resultado.monto,
                "umbrales": {
                    "adjudicacion_directa": resultado.umbral_adjudicacion_directa,
                    "invitacion_tres": resultado.umbral_invitacion,
                },
                "requiere_investigacion_mercado": resultado.requiere_investigacion_mercado,
                "observaciones": resultado.observaciones,
                "valido": resultado.procedimiento != ResultadoSeleccion.REQUIERE_JUSTIFICACION,
                "datos_verificados": resultado.datos_verificados,
                "es_candidato": resultado.es_candidato,
                "fuente_umbral": resultado.fuente_umbral,
                "threshold_meta": resultado.threshold_meta,
                "jurisdiction_code": code,
                "ejercicio_fiscal": ejercicio_fiscal,
            }

    async def validar_monto(
        self,
        monto: float,
        tipo_contratacion: str,
        jurisdiction_code: str = "MX-FED-OBRA",
        ejercicio_fiscal: int = 2026,
        presupuesto_dependencia_miles: float | None = None,
        tenant_id: UUID | str | None = None,
        jurisdiccion: str | None = None,
    ) -> dict[str, Any]:
        tid = self._require_tenant(tenant_id)
        code = (jurisdiction_code or jurisdiccion or "MX-FED-OBRA").upper()
        tipo = TipoContratacion(tipo_contratacion)
        return await self.motor.validar_monto(
            self.db,
            tenant_id=tid,
            monto=monto,
            tipo_contratacion=tipo,
            jurisdiction_code=code,
            ejercicio_fiscal=ejercicio_fiscal,
            presupuesto_dependencia_miles=presupuesto_dependencia_miles,
        )

    async def checklist_requisitos(
        self,
        procedimiento: str,
        tipo_contratacion: str,
    ) -> list[dict[str, Any]]:
        tipo = TipoContratacion(tipo_contratacion)
        proc = TipoProcedimiento(procedimiento)
        resultado = self.motor.obtener_requisitos(proc, tipo)
        return [
            {
                "codigo": r.codigo,
                "descripcion": r.descripcion,
                "obligatorio": r.obligatorio,
                "documento_soporte": r.documento_soporte,
                "articulo": r.articulo,
                "ley": r.ley,
                "cumplido": False,
                "evidencia": None,
            }
            for r in resultado["requisitos"]
        ]

    async def jurisdicciones_disponibles(
        self,
        tenant_id: UUID | str | None = None,
        ejercicio_fiscal: int | None = None,
    ) -> list[dict[str, Any]]:
        tid = self._require_tenant(tenant_id)
        return await self.motor.jurisdicciones_disponibles(
            self.db, tenant_id=tid, ejercicio_fiscal=ejercicio_fiscal
        )
