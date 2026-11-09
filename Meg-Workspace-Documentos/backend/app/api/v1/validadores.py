# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
API de validación de propuestas de licitación.

BUG ORIGINAL: el único endpoint (`/completo`) validaba un RFC checando
solo su longitud -- no corría ninguna regla de negocio real (SAT, IMSS,
INFONAVIT, FSR, maquinaria, sobrecostos, congruencia temporal, garantías,
publicación, requisitos de participación), y no persistía nada.

Ahora existe `/evaluar-completo`, que corre los 10 validadores reales
(portados de megalodon_costos_v3_1.py) contra el payload completo de una
propuesta, y persiste la bitácora para auditoría. El endpoint viejo
`/completo` se conserva para no romper integraciones existentes, pero
ahora deja explícito en la respuesta que es solo una verificación de
FORMATO de RFC, no una consulta real.
"""
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.core.deps import get_current_user, get_db
from app.core.errors import handle_megalodon_errors
from app.services.validador_service import ValidadorService, ValidadorExpedienteService
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


# ─── Payload completo de una propuesta (los 10 validadores reales) ─────

class FiscalInput(BaseModel):
    opinion_sat_sentido: str = ""
    opinion_sat_fecha: str = ""  # YYYY-MM-DD
    opinion_imss_sentido: str = ""
    opinion_infonavit_sentido: str = ""


class AdministrativoInput(BaseModel):
    efirma_valida: bool = False


class AnalisisFSRInput(BaseModel):
    tp_dias_pagados: float = 0
    tl_dias_laborados: float = 0
    ps_fraccion_imss_infonavit: float = 0
    fsr_calculado_por_licitante: float = 0


class AnalisisMaquinariaInput(BaseModel):
    codigo_equipo: str = "N/A"
    cargo_combustible: float = 0
    precio_litro_combustible_declarado: float = 0
    cargo_operacion: float = 0
    costo_horario_total: float = 0
    total_cargos_fijos: float = 0
    cargo_lubricantes: float = 0
    horas_uso_anual: float = 0
    requiere_combustible: bool = True


class AnalisisSobrecostosInput(BaseModel):
    pct_indirecto_oficina: float = 0
    pct_indirecto_campo: float = 0
    pct_utilidad: float = 0
    pct_financiamiento: float = 0
    pct_cargos_adicionales: float = 0
    factor_sobrecosto_total_declarado: float = 1.0
    tasa_interes_utilizada: float = 0


class EconomicoInput(BaseModel):
    analisis_fsr: AnalisisFSRInput = Field(default_factory=AnalisisFSRInput)
    analisis_maquinaria: AnalisisMaquinariaInput = Field(default_factory=AnalisisMaquinariaInput)
    analisis_sobrecostos: AnalisisSobrecostosInput = Field(default_factory=AnalisisSobrecostosInput)


class TecnicoInput(BaseModel):
    incongruencias_detectadas: List[str] = Field(default_factory=list)


class GarantiaInput(BaseModel):
    tipo: str
    monto: Optional[float] = None


class PropuestaLicitacionInput(BaseModel):
    rfc_empresa: Optional[str] = None
    fiscal: FiscalInput = Field(default_factory=FiscalInput)
    administrativo: AdministrativoInput = Field(default_factory=AdministrativoInput)
    economico: EconomicoInput = Field(default_factory=EconomicoInput)
    tecnico: TecnicoInput = Field(default_factory=TecnicoInput)
    garantias: List[GarantiaInput] = Field(default_factory=list)
    fecha_fallo: Optional[str] = None
    requisitos_participacion: List[str] = Field(default_factory=list)


class ResultadoReglaOut(BaseModel):
    id_regla: str
    seccion: str
    estatus: str
    valor_detectado: str
    valor_esperado: str
    evidencia: str


class ValidacionOut(BaseModel):
    id: UUID
    expediente_id: UUID
    proposicion_id: Optional[UUID] = None
    rfc_empresa: Optional[str] = None
    estado: str
    bitacora_evaluacion: List[ResultadoReglaOut]
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


@router.post("/{expediente_id}/evaluar-completo", response_model=ValidacionOut)
@handle_megalodon_errors
async def evaluar_propuesta_completa(
    expediente_id: UUID,
    data: PropuestaLicitacionInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Diagnostica los datos declarados y persiste la bitácora.

    No consulta SAT/IMSS ni verifica criptográficamente la e.firma; no emite
    admisión, veto legal ni marcas de integridad de archivos.
    """
    service = ValidadorService(db)
    return await service.evaluar_propuesta_completa(
        tenant_id=current_user.tenant_id,
        expediente_id=expediente_id,
        datos_propuesta=data.model_dump(),
        creado_por_id=current_user.id,
    )


@router.get("/{expediente_id}/historial", response_model=List[ValidacionOut])
@handle_megalodon_errors
async def historial_validaciones(
    expediente_id: UUID,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    service = ValidadorService(db)
    return await service.historial(expediente_id, tenant_id=current_user.tenant_id, limit=limit)


@router.get("/{expediente_id}/validacion/{validacion_id}", response_model=ValidacionOut)
@handle_megalodon_errors
async def obtener_validacion(
    expediente_id: UUID,
    validacion_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Antes era GET /validacion/{id} sin expediente_id en el path -- la
    única ruta del sistema que no colgaba de /{expediente_id}/..., y sin
    validar pertenencia (cualquiera con el UUID podía leer la validación
    de otro expediente)."""
    service = ValidadorService(db)
    return await service.obtener(validacion_id, expediente_id=expediente_id, tenant_id=current_user.tenant_id)


# ─── Endpoint viejo: validación de FORMATO de RFC únicamente ───────────
# BUG ORIGINAL: esto se llamaba "/completo" y no dejaba claro que solo
# verificaba longitud de RFC, no una consulta real a SAT/IMSS/INFONAVIT.

class ValidarRFCRequest(BaseModel):
    rfc: str = Field(..., min_length=12, max_length=13)
    fsr: float = Field(default=1.0, gt=0)


@router.post("/completo")
@handle_megalodon_errors
async def validar_formato_rfc(
    data: ValidarRFCRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Verificación de FORMATO de RFC/FSR únicamente. Para la validación
    real y completa de una propuesta, usar /{expediente_id}/evaluar-completo."""
    service = ValidadorService(db)
    return await service.validar_completo_rfc(data.rfc, data.fsr)


# ─── Validación documental/normativa de expedientes ────────────────────
#
# ANTES: ValidacionExpediente y CheckValidacion (app/models/validador.py)
# existían como modelos, pero ningún servicio ni endpoint los usaba en
# ningún lugar del backend -- catálogo de datos sin motor que lo
# ejecutara. Ahora corren de verdad contra app.engines.validadores.
# motor_expediente.MotorValidacionExpediente (ver ValidadorExpedienteService).

class ResultadoCheckOut(BaseModel):
    check_id: UUID
    codigo: str
    nombre: str
    categoria: str
    severidad: str
    estado: str
    detalle: str


class ValidacionExpedienteOut(BaseModel):
    id: UUID
    expediente_id: UUID
    tipo: str
    nombre: str
    descripcion: Optional[str] = None
    estado: str
    resultados: List[ResultadoCheckOut]
    score: Optional[int] = None
    ejecutado_por_id: Optional[UUID] = None
    fecha_ejecucion: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class EjecutarValidacionExpedienteRequest(BaseModel):
    tipo: str = Field(..., description="Tipo de la corrida, p. ej. 'DOCUMENTAL', 'PRE_FIRMA', 'CIERRE'.")
    nombre: str = Field(..., description="Nombre descriptivo de esta corrida de validación.")
    descripcion: Optional[str] = None
    categoria: Optional[str] = Field(
        default=None, description="Si se da, solo se corren los checks de esta categoría."
    )
    check_codigos: Optional[List[str]] = Field(
        default=None, description="Si se da, solo se corren los checks con estos códigos exactos."
    )


class CheckValidacionOut(BaseModel):
    id: UUID
    codigo: str
    nombre: str
    descripcion: Optional[str] = None
    categoria: str
    logica: Dict[str, Any]
    mensaje_exito: Optional[str] = None
    mensaje_error: Optional[str] = None
    severidad: str
    activo: bool
    orden: int

    class Config:
        from_attributes = True


class CheckValidacionCreate(BaseModel):
    codigo: str = Field(..., min_length=1, max_length=50)
    nombre: str = Field(..., min_length=1, max_length=255)
    descripcion: Optional[str] = None
    categoria: str = Field(..., description="DOCUMENTAL, FINANCIERA, TECNICA, TEMPORAL, NORMATIVA, INTEGRIDAD")
    logica: Dict[str, Any] = Field(..., description="{'tipo': 'documento_existe'|'rango_numerico'|"
                                                      "'campo_no_vacio'|'valor_en_catalogo'|'regex_formato', "
                                                      "'parametros': {...}}")
    mensaje_exito: Optional[str] = None
    mensaje_error: Optional[str] = None
    severidad: str = Field(default="MEDIA", description="BLOQUEANTE, ALTA, MEDIA, BAJA, INFORMATIVA")
    activo: bool = True
    orden: int = 0


class CheckValidacionUpdate(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    categoria: Optional[str] = None
    logica: Optional[Dict[str, Any]] = None
    mensaje_exito: Optional[str] = None
    mensaje_error: Optional[str] = None
    severidad: Optional[str] = None
    activo: Optional[bool] = None
    orden: Optional[int] = None


@router.post("/expedientes/{expediente_id}/ejecutar", response_model=ValidacionExpedienteOut)
@handle_megalodon_errors
async def ejecutar_validacion_expediente(
    expediente_id: UUID,
    data: EjecutarValidacionExpedienteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Corre el catálogo de CheckValidacion (documentos requeridos, montos,
    plazos, campos obligatorios, catálogos permitidos) contra el
    expediente completo y persiste el resultado."""
    service = ValidadorExpedienteService(db)
    return await service.ejecutar(
        tenant_id=current_user.tenant_id,
        expediente_id=expediente_id,
        tipo=data.tipo,
        nombre=data.nombre,
        descripcion=data.descripcion,
        categoria=data.categoria,
        check_codigos=data.check_codigos,
        ejecutado_por_id=current_user.id,
    )


@router.get("/expedientes/{expediente_id}/historial", response_model=List[ValidacionExpedienteOut])
@handle_megalodon_errors
async def historial_validacion_expediente(
    expediente_id: UUID,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    service = ValidadorExpedienteService(db)
    return await service.historial(expediente_id, tenant_id=current_user.tenant_id, limit=limit)


@router.get("/expedientes/{expediente_id}/validacion/{validacion_id}", response_model=ValidacionExpedienteOut)
@handle_megalodon_errors
async def obtener_validacion_expediente(
    expediente_id: UUID,
    validacion_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    service = ValidadorExpedienteService(db)
    return await service.obtener(validacion_id, expediente_id=expediente_id, tenant_id=current_user.tenant_id)


@router.get("/checks", response_model=List[CheckValidacionOut])
@handle_megalodon_errors
async def listar_checks(
    categoria: Optional[str] = None,
    solo_activos: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Lista el catálogo de checks reutilizables del tenant."""
    service = ValidadorExpedienteService(db)
    return await service.listar_checks(current_user.tenant_id, categoria=categoria, solo_activos=solo_activos)


@router.post("/checks", response_model=CheckValidacionOut)
@handle_megalodon_errors
async def crear_check(
    data: CheckValidacionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    service = ValidadorExpedienteService(db)
    return await service.crear_check(current_user.tenant_id, data.model_dump())


@router.patch("/checks/{check_id}", response_model=CheckValidacionOut)
@handle_megalodon_errors
async def actualizar_check(
    check_id: UUID,
    data: CheckValidacionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    service = ValidadorExpedienteService(db)
    return await service.actualizar_check(check_id, current_user.tenant_id, data.model_dump(exclude_unset=True))


@router.patch("/checks/{check_id}/toggle", response_model=CheckValidacionOut)
@handle_megalodon_errors
async def alternar_check(
    check_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Activa/desactiva un check sin borrarlo (toggle de 'activo')."""
    service = ValidadorExpedienteService(db)
    return await service.alternar_check(check_id, current_user.tenant_id)


@router.post("/checks/sembrar-default", response_model=List[CheckValidacionOut])
@handle_megalodon_errors
async def sembrar_checks_default(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Crea el catálogo base de checks para el tenant si todavía no tiene
    ninguno propio (idempotente por código: no duplica los que ya existan)."""
    service = ValidadorExpedienteService(db)
    return await service.sembrar_checks_default(current_user.tenant_id)
