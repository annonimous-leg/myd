# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
API del motor jurídico.

Todo el cálculo de umbrales y excepciones se resuelve desde DB
(procedure_thresholds + legal_rules). El router solo valida entrada y
delega en JuridicoService.
"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.deps import get_db
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from app.engines.juridico.motor_juridico import TipoContratacion, TipoProcedimiento
from app.services.juridico_service import JuridicoService

router = APIRouter()


class DeterminarProcedimientoRequest(BaseModel):
    monto: float = Field(..., gt=0)
    tipo_contratacion: TipoContratacion = TipoContratacion.OBRA_PUBLICA
    es_obra_publica: bool = True
    jurisdiction_code: str = Field(
        default="MX-FED-OBRA",
        description="Código de JurisdictionProfile (ej. MX-FED-OBRA, MX-FED-CONAGUA-OBRA).",
    )
    ejercicio_fiscal: int = 2026
    presupuesto_dependencia_miles: Optional[float] = Field(
        default=None,
        description="Presupuesto autorizado de la dependencia en miles de pesos (Anexo 9 escalonado).",
    )
    excepcion_legal: Optional[str] = Field(
        default=None,
        description="rule_id de LegalRule con domain=PROCEDURE_EXCEPTION.",
    )
    justificacion_excepcion: Optional[str] = None
    investigacion_mercado_realizada: bool = False


class ValidarMontoRequest(BaseModel):
    monto: float = Field(..., gt=0)
    tipo_contratacion: TipoContratacion = TipoContratacion.OBRA_PUBLICA
    jurisdiction_code: str = "MX-FED-OBRA"
    ejercicio_fiscal: int = 2026
    presupuesto_dependencia_miles: Optional[float] = None


class ChecklistRequest(BaseModel):
    procedimiento: TipoProcedimiento
    tipo_contratacion: TipoContratacion = TipoContratacion.OBRA_PUBLICA


@router.post("/determinar-procedimiento")
async def determinar_procedimiento(
    data: DeterminarProcedimientoRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_strict),
):
    service = JuridicoService(db, tenant_id=current_user.tenant_id)
    return await service.determinar_procedimiento(
        monto=data.monto,
        tipo_contratacion=data.tipo_contratacion.value,
        es_obra_publica=data.es_obra_publica,
        jurisdiction_code=data.jurisdiction_code,
        ejercicio_fiscal=data.ejercicio_fiscal,
        presupuesto_dependencia_miles=data.presupuesto_dependencia_miles,
        excepcion_legal=data.excepcion_legal,
        justificacion_excepcion=data.justificacion_excepcion,
        investigacion_mercado_realizada=data.investigacion_mercado_realizada,
        tenant_id=current_user.tenant_id,
    )


@router.post("/validar-monto")
async def validar_monto(
    data: ValidarMontoRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_strict),
):
    service = JuridicoService(db, tenant_id=current_user.tenant_id)
    return await service.validar_monto(
        monto=data.monto,
        tipo_contratacion=data.tipo_contratacion.value,
        jurisdiction_code=data.jurisdiction_code,
        ejercicio_fiscal=data.ejercicio_fiscal,
        presupuesto_dependencia_miles=data.presupuesto_dependencia_miles,
        tenant_id=current_user.tenant_id,
    )


@router.post("/checklist")
async def checklist(
    data: ChecklistRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_strict),
):
    service = JuridicoService(db, tenant_id=current_user.tenant_id)
    requisitos = await service.checklist_requisitos(
        procedimiento=data.procedimiento.value,
        tipo_contratacion=data.tipo_contratacion.value,
    )
    return {
        "procedimiento": data.procedimiento.value,
        "tipo_contratacion": data.tipo_contratacion.value,
        "requisitos": requisitos,
    }


@router.get("/jurisdicciones")
async def jurisdicciones_disponibles(
    ejercicio_fiscal: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_standard),
):
    service = JuridicoService(db, tenant_id=current_user.tenant_id)
    return await service.jurisdicciones_disponibles(
        tenant_id=current_user.tenant_id,
        ejercicio_fiscal=ejercicio_fiscal,
    )
