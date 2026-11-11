# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
API BIM/IFC — cuantificación real conectada a BIMService.

BUG ORIGINAL (histórico): subir_ifc() encolaba una tarea de Celery
pasando solo filename/content_type (nunca los bytes del archivo), y el
worker (bim_tasks.py) tenía un TODO sin implementar -- nada se procesaba
nunca, la tarea siempre regresaba elementos_count=0 hardcodeado. Se
resolvió haciendo el procesamiento SÍNCRONO mientras no hubiera storage
real de donde el worker pudiera leer el archivo de forma asíncrona.

Storage real (Supabase, ver STORAGE_SUPABASE.md) y el worker
(workers/bim_tasks.py:procesar_ifc) ya existen y están probados -- este
endpoint ahora sí encola en vez de procesar en el request. Un IFC grande
ya no bloquea el request completo; el frontend hace polling a
GET /modelos/{id} hasta que estado_procesamiento sea COMPLETADO o ERROR.
"""
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Dict, List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile, File, Form, Header, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, verificar_expediente_tenant, module_access, require_approval_role
from app.core.errors import MegalodonException, ErrorCode
from app.config import settings
from app.models.base import EstadoProceso
from app.services.bim_service import BIMService
from app.services.clash_service import ClashService
from app.models.user import User
from app.schemas.costos import ParametrosCosteoInput
from app.utils.upload_limits import validate_upload_with_limit

# BUG ORIGINAL: ningún endpoint de este router verificaba que
# expediente_id perteneciera al tenant del usuario autenticado -- ver
# nota completa en app.core.deps.verificar_expediente_tenant. Todas las
# rutas de este archivo cuelgan de /{expediente_id}/..., así que se
# aplica una sola vez a nivel router.
router = APIRouter(dependencies=[Depends(verificar_expediente_tenant), Depends(module_access("bim-calculator"))])


class ModeloBIMOut(BaseModel):
    id: UUID
    identificador: str
    nombre: str
    descripcion: Optional[str] = None
    expediente_id: UUID
    estado_procesamiento: str
    num_elementos: int
    niveles: Optional[List[str]] = None
    version_ifc: Optional[str] = None
    revision_actual_id: Optional[UUID] = None
    error_procesamiento: Optional[str] = None

    class Config:
        from_attributes = True


class ElementoBIMOut(BaseModel):
    id: UUID
    modelo_id: UUID
    global_id: str
    tipo: str
    nombre: Optional[str] = None
    volumen: Optional[float] = None
    area: Optional[float] = None
    longitud: Optional[float] = None
    fuente_volumen: str
    fuente_area: str
    nivel: Optional[str] = None
    bbox: Optional[List[float]] = None
    partida_id: Optional[UUID] = None
    malla_vertices: Optional[list] = None
    malla_caras: Optional[list] = None

    class Config:
        from_attributes = True


class MapeoPartida(BaseModel):
    elemento_id: UUID
    partida_id: UUID


class CantidadComplementaria(BaseModel):
    elemento_id: UUID
    unidad: str = Field(..., min_length=1, max_length=20)
    cantidad: float = Field(..., gt=0, lt=1e14, allow_inf_nan=False)
    referencia: str = Field(..., min_length=5, max_length=1000)


class GenerarPresupuestoRequest(BaseModel):
    nombre: str = "Presupuesto desde BIM"
    parametros_costeo: ParametrosCosteoInput
    # Atajo por IfcType y overrides por elemento. El override puntual
    # evita asumir que dos elementos del mismo tipo tienen la misma
    # especificación/material/APU.
    mapeo_catalogo: Optional[Dict[str, UUID]] = None
    mapeo_elementos: Dict[UUID, UUID] = Field(default_factory=dict, max_length=20_000)
    cantidades_complementarias: List[CantidadComplementaria] = Field(default_factory=list)


class AsignarZona4D(BaseModel):
    elemento_id: UUID
    zona_4d: str


class AsignarZonaPorNivel4D(BaseModel):
    zona_4d: str = Field(min_length=1, max_length=255, pattern=r"\S")
    nivel: Optional[str] = None


class GenerarActividades4DRequest(BaseModel):
    fecha_inicio: datetime
    # Duración base configurable; la estimación final la ajusta el
    # servicio BIM con el tamaño y la complejidad geométrica del grupo.
    dias_por_defecto: float = 5.0
    nombre_programa: Optional[str] = None


class GeneracionBIM4D5DOut(BaseModel):
    id: UUID
    modelo_id: UUID
    expediente_id: UUID
    programa_id: Optional[UUID] = None
    estado: str
    error: Optional[str] = None
    agrupar_por: str
    dias_por_defecto: float
    num_actividades_generadas: Optional[int] = None

    class Config:
        from_attributes = True


class CrearDibujoRequest(BaseModel):
    tipo: Literal["PLAN", "SECTION", "ELEVATION"]
    titulo: str = Field(..., min_length=1, max_length=300)
    parametros: Dict[str, object]
    formatos: List[Literal["SVG", "DXF", "PDF"]] = Field(default_factory=lambda: ["SVG", "DXF"], min_length=1)
    permitir_geometria_parcial: bool = False

    class Config:
        extra = "forbid"


class DibujoBIMOut(BaseModel):
    id: UUID
    modelo_id: UUID
    expediente_id: UUID
    tipo: str
    titulo: str
    formatos: List[str]
    estado: str
    error: Optional[str] = None
    elementos_fuente: int
    elementos_con_malla: Optional[int] = None
    elementos_sin_malla: Optional[int] = None
    sha256_svg: Optional[str] = None
    sha256_dxf: Optional[str] = None
    sha256_pdf: Optional[str] = None
    source_model_updated_at: datetime
    metadatos: Optional[dict] = None
    obsoleto: bool = False

    class Config:
        from_attributes = True


class EjecutarClashRequest(BaseModel):
    # 0 = solo traslape real ("clash duro"). >0 = también marca pares que
    # están más cerca que esta distancia sin llegar a tocarse ("clash
    # blando" -- típico para reglas de clearance MEP vs estructura).
    tolerancia_m: float = 0.0
    tipos_incluidos: Optional[List[str]] = None
    tipos_excluidos: Optional[List[str]] = None


class AnalisisClashOut(BaseModel):
    id: UUID
    modelo_id: UUID
    tolerancia_m: float
    estado: str
    num_pares_evaluados: int
    num_clashes_duros: int
    num_clashes_blandos: int
    tiempo_calculo_ms: Optional[int] = None
    error: Optional[str] = None

    class Config:
        from_attributes = True


class ClashResultOut(BaseModel):
    id: UUID
    analisis_id: UUID
    elemento_a_id: UUID
    elemento_b_id: UUID
    tipo_a: str
    tipo_b: str
    severidad: str
    distancia_m: float
    volumen_aproximado_m3: Optional[float] = None
    punto_cercano_a: List[float]
    punto_cercano_b: List[float]
    triangulos_a: Optional[list] = None
    triangulos_b: Optional[list] = None
    estado: str

    class Config:
        from_attributes = True


class ActualizarEstadoClashRequest(BaseModel):
    estado: str  # NUEVO | REVISADO | RESUELTO | IGNORADO


@router.get("/{expediente_id}/modelos", response_model=List[ModeloBIMOut])
async def listar_modelos_bim(
    expediente_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Lista los modelos BIM de un expediente (más reciente primero)."""
    service = BIMService(db, tenant_id=current_user.tenant_id)
    return await service.listar_modelos(expediente_id)


@router.post("/{expediente_id}/modelos", response_model=ModeloBIMOut)
async def subir_modelo_bim(
    expediente_id: UUID,
    file: UploadFile = File(...),
    nombre: str = Form(...),
    descripcion: Optional[str] = Form(None),
    tipos_elementos: Optional[str] = Form(None),  # coma-separado, ej "IfcWall,IfcSlab"
    extraer_malla: bool = Form(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Registra el modelo (sube el IFC a Supabase Storage de una vez) y
    encola la extracción de cantidades (Qto del IFC, con respaldo
    geométrico) y la malla para renderizar en el frontend.

    Devuelve con estado_procesamiento=EN_PROCESO; el frontend hace
    polling a GET /modelos/{id} hasta COMPLETADO o ERROR."""
    service = BIMService(db, tenant_id=current_user.tenant_id)
    file_size = await validate_upload_with_limit(file, settings.IFC_MAX_FILE_SIZE_MB)

    tipos = [t.strip() for t in tipos_elementos.split(",")] if tipos_elementos else None
    modelo = await service.crear_modelo(
        expediente_id=expediente_id,
        nombre=nombre,
        descripcion=descripcion,
        file_content=file.file,
        file_size=file_size,
        filename=file.filename or "modelo.ifc",
        opciones_procesamiento={"tipos_elementos":tipos, "extraer_malla":extraer_malla},
        creado_por_id=current_user.id,
    )

    return modelo


@router.get("/{expediente_id}/modelos/{modelo_id}/descarga")
async def descargar_modelo_bim(
    expediente_id: UUID,
    modelo_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """URL firmada temporal para descargar el IFC original desde
    Supabase Storage directamente (no pasa por el backend)."""
    service = BIMService(db, tenant_id=current_user.tenant_id)
    if settings.BIM_STORAGE_PROVIDER == 'filesystem':
        await service._validar_modelo_en_expediente(modelo_id, expediente_id)
        return {'url': str(request.url_for('descargar_ifc_local', expediente_id=str(expediente_id),
            modelo_id=str(modelo_id))), 'expira_en_segundos': 0}
    url = await service.url_descarga_modelo(modelo_id, expediente_id=expediente_id)
    return {"url": url, "expira_en_segundos": 3600}


@router.get("/{expediente_id}/modelos/{modelo_id}", response_model=ModeloBIMOut)
async def obtener_modelo_bim(
    expediente_id: UUID,
    modelo_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    service = BIMService(db, tenant_id=current_user.tenant_id)
    modelo = await service._validar_modelo_en_expediente(modelo_id, expediente_id)
    return modelo


@router.get("/{expediente_id}/modelos/{modelo_id}/elementos", response_model=List[ElementoBIMOut])
async def listar_elementos_bim(
    expediente_id: UUID,
    modelo_id: UUID,
    tipo: Optional[str] = None,
    nivel: Optional[str] = None,
    incluir_malla: bool = False,
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Lista elementos cuantificados. `incluir_malla=true` para pedir la
    geometría (más pesado) cuando el frontend va a renderizar en 3D.
    `nivel` filtra por piso/planta (ver ModeloBIM.niveles)."""
    service = BIMService(db, tenant_id=current_user.tenant_id)
    return await service.listar_elementos(
        modelo_id, expediente_id=expediente_id, tipo=tipo, nivel=nivel, incluir_malla=incluir_malla, limit=limit, offset=offset
    )


@router.post("/{expediente_id}/modelos/{modelo_id}/mapear-partidas")
async def mapear_elementos_a_partidas(
    expediente_id: UUID,
    modelo_id: UUID,
    mapeos: List[MapeoPartida],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    service = BIMService(db, tenant_id=current_user.tenant_id)
    count = await service.mapear_a_partidas(modelo_id, expediente_id=expediente_id, mapeos=[m.model_dump() for m in mapeos])
    return {"elementos_actualizados": count}


@router.post("/{expediente_id}/modelos/{modelo_id}/generar-presupuesto")
async def generar_presupuesto_desde_bim(
    expediente_id: UUID,
    modelo_id: UUID,
    data: GenerarPresupuestoRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Crea un presupuesto desde cantidades BIM y los APU seleccionados."""
    from app.api.v1.presupuestos import PresupuestoOut

    solicitud = None
    if idempotency_key is not None:
        canonical = json.dumps(data.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        solicitud = {
            "clave": sha256(f"{current_user.id}:{idempotency_key}".encode()).hexdigest(),
            "huella": sha256(canonical.encode()).hexdigest(),
        }
    service = BIMService(db, tenant_id=current_user.tenant_id)
    presupuesto = await service.crear_presupuesto_desde_bim(
        modelo_id=modelo_id,
        expediente_id=expediente_id,
        nombre=data.nombre,
        parametros_costeo=data.parametros_costeo.to_domain(),
        mapeo_catalogo=data.mapeo_catalogo,
        mapeo_elementos=data.mapeo_elementos,
        cantidades_complementarias=[item.model_dump() for item in data.cantidades_complementarias],
        creado_por_id=current_user.id,
        solicitud=solicitud,
    )
    return PresupuestoOut.model_validate(presupuesto)


@router.post("/{expediente_id}/modelos/{modelo_id}/zonas-4d")
async def asignar_zonas_4d(
    expediente_id: UUID,
    modelo_id: UUID,
    asignaciones: List[AsignarZona4D] | AsignarZonaPorNivel4D,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Asigna zona_4d a elementos en lote -- agrupación de trabajo
    editable para el cronograma 4D, independiente de `nivel` (ver
    ElementoBIM.zona_4d). Sin esto, generar-4d5d agrupa por `nivel`."""
    service = BIMService(db, tenant_id=current_user.tenant_id)
    if isinstance(asignaciones, AsignarZonaPorNivel4D):
        count = await service.asignar_zona_por_nivel(
            modelo_id, expediente_id, asignaciones.zona_4d.strip(), asignaciones.nivel,
        )
    else:
        count = await service.asignar_zonas_4d(
            modelo_id, expediente_id=expediente_id,
            asignaciones=[a.model_dump() for a in asignaciones],
        )
    return {"elementos_actualizados": count}


@router.post("/{expediente_id}/modelos/{modelo_id}/generar-4d5d", response_model=GeneracionBIM4D5DOut)
async def generar_4d5d(
    expediente_id: UUID,
    modelo_id: UUID,
    data: GenerarActividades4DRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Encola la generación de un ProgramaObra 4D desde el modelo BIM
    (una actividad por zona×tipo, sin predecesoras -- ver nota en
    BIMService.generar_actividades_4d). Devuelve de inmediato el
    registro de seguimiento; el frontend hace polling a
    GET .../generaciones-4d5d/{id} hasta COMPLETADO o ERROR."""
    service = BIMService(db, tenant_id=current_user.tenant_id)
    generacion = await service.crear_generacion_4d5d(
        modelo_id=modelo_id,
        expediente_id=expediente_id,
        dias_por_defecto=data.dias_por_defecto,
        fecha_inicio=data.fecha_inicio,
        creado_por_id=current_user.id,
    )

    return generacion


@router.get("/{expediente_id}/generaciones-4d5d/{generacion_id}", response_model=GeneracionBIM4D5DOut)
async def obtener_generacion_4d5d(
    expediente_id: UUID,
    generacion_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Poll de estado de una generación 4D en curso."""
    from app.models.bim import GeneracionBIM4D5D

    result = await db.execute(
        select(GeneracionBIM4D5D).where(
            GeneracionBIM4D5D.id == generacion_id,
            GeneracionBIM4D5D.tenant_id == current_user.tenant_id,
            GeneracionBIM4D5D.expediente_id == expediente_id,
        )
    )
    generacion = result.scalar_one_or_none()
    if not generacion:
        raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, f"Generación {generacion_id} no encontrada")
    return generacion


@router.post("/{expediente_id}/modelos/{modelo_id}/clash-detection", response_model=AnalisisClashOut)
async def ejecutar_clash_detection(
    expediente_id: UUID,
    modelo_id: UUID,
    data: EjecutarClashRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Registra el análisis (rápido, PENDIENTE) y encola el cómputo real
    (broad phase AABB + narrow phase Möller-Trumbore triángulo-triángulo)
    en un worker Celery -- ver ClashService/bim_tasks.analizar_clash sobre
    por qué esto ya no corre síncrono dentro del request. El frontend hace
    polling a GET /clash-detection/{analisis_id} hasta COMPLETADO/ERROR,
    igual que con la carga del modelo."""
    service = ClashService(db, current_user.tenant_id)
    analisis = await service.crear_analisis_pendiente(
        modelo_id=modelo_id,
        expediente_id=expediente_id,
        tolerancia_m=data.tolerancia_m,
        tipos_incluidos=data.tipos_incluidos,
        tipos_excluidos=data.tipos_excluidos,
        creado_por_id=current_user.id,
    )

    return analisis


@router.get("/{expediente_id}/modelos/{modelo_id}/clash-detection/{analisis_id}", response_model=AnalisisClashOut)
async def obtener_analisis_clash(
    expediente_id: UUID,
    modelo_id: UUID,
    analisis_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    service = ClashService(db, current_user.tenant_id)
    return await service.obtener_analisis(analisis_id, modelo_id=modelo_id)


@router.get(
    "/{expediente_id}/modelos/{modelo_id}/clash-detection/{analisis_id}/resultados",
    response_model=List[ClashResultOut],
)
async def listar_resultados_clash(
    expediente_id: UUID,
    modelo_id: UUID,
    analisis_id: UUID,
    severidad: Optional[str] = None,
    estado: Optional[str] = None,
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """`severidad`: DURO | BLANDO. `estado`: NUEVO | REVISADO | RESUELTO
    | IGNORADO. Ordenado DURO primero, luego por fecha."""
    service = ClashService(db, current_user.tenant_id)
    return await service.listar_resultados(
        analisis_id, modelo_id=modelo_id, severidad=severidad, estado=estado, limit=limit, offset=offset
    )


@router.patch("/{expediente_id}/clash-resultados/{resultado_id}/estado", response_model=ClashResultOut)
async def actualizar_estado_clash(
    expediente_id: UUID,
    resultado_id: UUID,
    data: ActualizarEstadoClashRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Marca un clash como revisado/resuelto/ignorado -- seguimiento de
    equipo, no vuelve a correr el análisis geométrico."""
    service = ClashService(db, current_user.tenant_id)
    return await service.actualizar_estado_resultado(resultado_id, data.estado, expediente_id=expediente_id)



def _dibujo_bim_out(drawing, model) -> DibujoBIMOut:
    source_time = drawing.source_model_updated_at
    model_time = model.updated_at
    if source_time.tzinfo is None:
        source_time = source_time.replace(tzinfo=timezone.utc)
    if model_time.tzinfo is None:
        model_time = model_time.replace(tzinfo=timezone.utc)
    return DibujoBIMOut(
        id=drawing.id,
        modelo_id=drawing.modelo_id,
        expediente_id=drawing.expediente_id,
        tipo=drawing.tipo,
        titulo=drawing.titulo,
        formatos=drawing.formatos,
        estado=drawing.estado,
        error=drawing.error,
        elementos_fuente=drawing.elementos_fuente,
        elementos_con_malla=drawing.elementos_con_malla,
        elementos_sin_malla=drawing.elementos_sin_malla,
        sha256_svg=drawing.sha256_svg,
        sha256_dxf=drawing.sha256_dxf,
        sha256_pdf=drawing.sha256_pdf,
        source_model_updated_at=drawing.source_model_updated_at,
        metadatos=drawing.metadatos,
        obsoleto=(source_time != model_time or drawing.source_model_version != model.version_ifc),
    )


@router.post(
    "/{expediente_id}/modelos/{modelo_id}/dibujos",
    response_model=DibujoBIMOut,
    status_code=202,
)
async def crear_dibujo_bim(
    expediente_id: UUID,
    modelo_id: UUID,
    data: CrearDibujoRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_strict),
):
    from app.services.bim_drawing_service import BIMDrawingService

    drawing = await BIMDrawingService(db, current_user.tenant_id).crear_dibujo(
        expediente_id=expediente_id,
        modelo_id=modelo_id,
        creado_por_id=current_user.id,
        tipo=data.tipo,
        titulo=data.titulo,
        parametros=data.parametros,
        formatos=data.formatos,
        permitir_geometria_parcial=data.permitir_geometria_parcial,
    )
    model = await BIMService(db, current_user.tenant_id)._validar_modelo_en_expediente(
        modelo_id, expediente_id
    )
    return _dibujo_bim_out(drawing, model)


@router.get(
    "/{expediente_id}/modelos/{modelo_id}/dibujos",
    response_model=List[DibujoBIMOut],
)
async def listar_dibujos_bim(
    expediente_id: UUID,
    modelo_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_standard),
):
    from app.models.bim import DibujoBIM

    model = await BIMService(db, current_user.tenant_id)._validar_modelo_en_expediente(
        modelo_id, expediente_id
    )
    drawings = (await db.scalars(
        select(DibujoBIM).where(
            DibujoBIM.tenant_id == current_user.tenant_id,
            DibujoBIM.expediente_id == expediente_id,
            DibujoBIM.modelo_id == modelo_id,
        ).order_by(DibujoBIM.created_at.desc()).limit(200)
    )).all()
    return [_dibujo_bim_out(drawing, model) for drawing in drawings]


@router.get(
    "/{expediente_id}/modelos/{modelo_id}/dibujos/{dibujo_id}",
    response_model=DibujoBIMOut,
)
async def obtener_dibujo_bim(
    expediente_id: UUID,
    modelo_id: UUID,
    dibujo_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_standard),
):
    from app.models.bim import DibujoBIM

    model = await BIMService(db, current_user.tenant_id)._validar_modelo_en_expediente(
        modelo_id, expediente_id
    )
    drawing = await db.scalar(select(DibujoBIM).where(
        DibujoBIM.id == dibujo_id,
        DibujoBIM.tenant_id == current_user.tenant_id,
        DibujoBIM.expediente_id == expediente_id,
        DibujoBIM.modelo_id == modelo_id,
    ))
    if drawing is None:
        raise MegalodonException(
            ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Dibujo no encontrado", status_code=404
        )
    return _dibujo_bim_out(drawing, model)


@router.get("/{expediente_id}/modelos/{modelo_id}/dibujos/{dibujo_id}/descarga")
async def descargar_dibujo_bim(
    expediente_id: UUID,
    modelo_id: UUID,
    dibujo_id: UUID,
    formato: Literal["SVG", "DXF", "PDF"] = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_standard),
):
    from app.models.bim import DibujoBIM
    from app.integrations.supabase_storage import storage_bim

    await BIMService(db, current_user.tenant_id)._validar_modelo_en_expediente(
        modelo_id, expediente_id
    )
    drawing = await db.scalar(select(DibujoBIM).where(
        DibujoBIM.id == dibujo_id,
        DibujoBIM.tenant_id == current_user.tenant_id,
        DibujoBIM.expediente_id == expediente_id,
        DibujoBIM.modelo_id == modelo_id,
    ))
    if drawing is None:
        raise MegalodonException(
            ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Dibujo no encontrado", status_code=404
        )
    if drawing.estado != "COMPLETADO":
        raise MegalodonException(
            ErrorCode.BIM_ERROR, "El dibujo todavía no está disponible", status_code=409
        )
    path = {"SVG": drawing.ruta_svg, "DXF": drawing.ruta_dxf, "PDF": drawing.ruta_pdf}[formato]
    if not path:
        raise MegalodonException(
            ErrorCode.DOCUMENTO_NO_ENCONTRADO, "El formato solicitado no fue generado", status_code=404
        )

    filename = f"dibujo-{drawing.id}.{formato.lower()}"
    content_type = {"SVG": "image/svg+xml", "DXF": "application/dxf", "PDF": "application/pdf"}[formato]
    if settings.BIM_STORAGE_PROVIDER == "filesystem":
        if settings.is_production:
            raise MegalodonException(ErrorCode.ARCHIVO_ERROR, "Almacenamiento local no habilitado en producción")
        from app.integrations.filesystem_storage import FilesystemBIMStorage

        file_path = FilesystemBIMStorage().path(path)
        if not file_path.is_file():
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Archivo de dibujo no encontrado", status_code=404
            )
        return FileResponse(file_path, media_type=content_type, filename=filename)

    url = await storage_bim().url_firmada(path, 3600)
    if not url:
        raise MegalodonException(ErrorCode.ARCHIVO_ERROR, "No se pudo generar la descarga del dibujo")
    return {"url": url, "expira_en_segundos": 3600}


@router.get('/{expediente_id}/modelos/{modelo_id}/trabajos')
async def listar_trabajos_bim(expediente_id: UUID, modelo_id: UUID,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from sqlalchemy import or_
    from app.models.bim import GeneracionBIM4D5D, AnalisisClash, DibujoBIM
    from app.models.process_job import TrabajoProceso
    await BIMService(db, current_user.tenant_id)._validar_modelo_en_expediente(modelo_id, expediente_id)
    generations = select(GeneracionBIM4D5D.id).where(GeneracionBIM4D5D.modelo_id == modelo_id)
    analyses = select(AnalisisClash.id).where(AnalisisClash.modelo_id == modelo_id)
    drawings = select(DibujoBIM.id).where(DibujoBIM.modelo_id == modelo_id)
    jobs = (await db.scalars(select(TrabajoProceso).where(
        TrabajoProceso.tenant_id == current_user.tenant_id,
        or_(TrabajoProceso.entidad_id == modelo_id, TrabajoProceso.entidad_id.in_(generations),
            TrabajoProceso.entidad_id.in_(analyses),
            TrabajoProceso.entidad_id.in_(drawings)))
        .order_by(TrabajoProceso.created_at.desc()).limit(100))).all()
    return [{'id':str(j.id), 'tipo':j.tipo, 'entidad_id':str(j.entidad_id),
        'estado':j.estado, 'intentos':j.intentos,
        'mensaje':j.error or j.error_publicacion} for j in jobs]


@router.post('/{expediente_id}/modelos/{modelo_id}/trabajos/{trabajo_id}/reintentar')
async def reintentar_trabajo_bim(expediente_id: UUID, modelo_id: UUID, trabajo_id: UUID,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_strict)):
    from datetime import timezone
    from app.models.process_job import TrabajoProceso
    from app.core.process_queue import _entidad, reintentar_trabajo_dibujo

    # Drawing retries must coordinate with their durable cleanup job. The helper
    # enforces the same lock order as the worker before mutating either job.
    candidate = await db.scalar(select(TrabajoProceso).where(
        TrabajoProceso.id == trabajo_id,
        TrabajoProceso.tenant_id == current_user.tenant_id,
    ))
    if candidate is None:
        raise MegalodonException(
            ErrorCode.DOCUMENTO_NO_ENCONTRADO, 'Trabajo no encontrado', status_code=404
        )
    if candidate.tipo in ('BIM_DRAWING', 'BIM_DRAWING_CLEANUP'):
        result = await reintentar_trabajo_dibujo(
            db,
            trabajo_id=trabajo_id,
            tenant_id=current_user.tenant_id,
            expediente_id=expediente_id,
            modelo_id=modelo_id,
        )
        await db.commit()
        return result

    # Lock order for the other job types remains job -> entity/model.
    job = await db.scalar(select(TrabajoProceso).where(
        TrabajoProceso.id == trabajo_id,
        TrabajoProceso.tenant_id == current_user.tenant_id,
    ).with_for_update())
    if job is None:
        raise MegalodonException(
            ErrorCode.DOCUMENTO_NO_ENCONTRADO, 'Trabajo no encontrado', status_code=404
        )
    entity, state_field, error_field = await _entidad(db, job)
    actual_model_id = entity.id if job.tipo == 'BIM_IFC' else entity.modelo_id
    if actual_model_id != modelo_id:
        raise MegalodonException(
            ErrorCode.DOCUMENTO_NO_ENCONTRADO, 'Trabajo no encontrado', status_code=404
        )
    await BIMService(db, current_user.tenant_id)._validar_modelo_en_expediente(
        modelo_id, expediente_id
    )
    if job.estado != 'ERROR':
        raise MegalodonException(
            ErrorCode.BIM_ERROR, 'Este trabajo ya está en curso o terminado', status_code=409
        )
    job.estado, job.intentos, job.error = 'PENDIENTE', 0, None
    job.error_publicacion = None
    job.id_ejecucion = None
    job.proxima_publicacion = datetime.now(timezone.utc)
    setattr(entity, state_field, 'PENDIENTE')
    setattr(entity, error_field, None)
    await db.commit()
    return {'id':str(job.id), 'estado':job.estado}


@router.get('/{expediente_id}/modelos/{modelo_id}/generaciones-4d5d', response_model=List[GeneracionBIM4D5DOut])
async def listar_generaciones_bim(expediente_id: UUID, modelo_id: UUID,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.models.bim import GeneracionBIM4D5D
    await BIMService(db, current_user.tenant_id)._validar_modelo_en_expediente(modelo_id, expediente_id)
    return (await db.scalars(select(GeneracionBIM4D5D).where(
        GeneracionBIM4D5D.modelo_id == modelo_id, GeneracionBIM4D5D.tenant_id == current_user.tenant_id)
        .order_by(GeneracionBIM4D5D.created_at.desc()).limit(100))).all()


@router.get('/{expediente_id}/modelos/{modelo_id}/archivo')
async def descargar_ifc_local(expediente_id: UUID, modelo_id: UUID,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if settings.BIM_STORAGE_PROVIDER != 'filesystem' or settings.is_production:
        raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, 'Archivo no encontrado', status_code=404)
    from app.integrations.filesystem_storage import FilesystemBIMStorage
    model = await BIMService(db, current_user.tenant_id)._validar_modelo_en_expediente(modelo_id, expediente_id)
    path = FilesystemBIMStorage().path(model.ruta_archivo)
    if not path.is_file():
        raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, 'Archivo no encontrado', status_code=404)
    return FileResponse(path, media_type='application/x-step', filename='original.ifc')


class ReprocesarModeloRequest(BaseModel):
    tipos_elementos: Optional[List[str]] = None
    extraer_malla: bool = True
    revision_esperada_id: Optional[UUID] = None


@router.post('/{expediente_id}/modelos/{modelo_id}/reprocesar', response_model=ModeloBIMOut)
async def reprocesar_modelo(expediente_id: UUID, modelo_id: UUID, data: ReprocesarModeloRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_strict)):
    from datetime import timezone
    from app.models.process_job import TrabajoProceso
    from app.core.process_queue import registrar_trabajo
    query = select(TrabajoProceso).where(TrabajoProceso.tenant_id == current_user.tenant_id,
        TrabajoProceso.entidad_id == modelo_id, TrabajoProceso.tipo == 'BIM_IFC')
    job = await db.scalar(query.with_for_update())
    model = await BIMService(db, current_user.tenant_id)._validar_modelo_en_expediente(
        modelo_id, expediente_id, bloquear=True)
    if data.revision_esperada_id is not None and data.revision_esperada_id != model.revision_actual_id:
        raise MegalodonException(ErrorCode.BIM_ERROR, 'Cambió la revisión; actualiza la cobertura', status_code=409)
    if job is None:
        # A concurrent legacy request may have created the intent while we
        # waited for the model. Never acquire a job lock after a model lock.
        if await db.scalar(query) is not None:
            raise MegalodonException(ErrorCode.BIM_ERROR, 'Ya se registró el procesamiento; actualiza el modelo', status_code=409)
    if job is not None and job.estado not in ('ERROR', 'COMPLETADO'):
        raise MegalodonException(ErrorCode.BIM_ERROR, 'El modelo ya está en procesamiento', status_code=409)
    params = data.model_dump(exclude={"revision_esperada_id"})
    if job is None:
        registrar_trabajo(db, model, 'BIM_IFC', params)
    else:
        job.parametros, job.estado, job.intentos = params, 'PENDIENTE', 0
        job.error = job.error_publicacion = job.id_ejecucion = None
        job.proxima_publicacion = datetime.now(timezone.utc)
    model.estado_procesamiento, model.error_procesamiento = 'PENDIENTE', None
    await db.commit()
    return model

# Operational coverage and measurement policy share the model's tenant boundary.
@router.get('/{expediente_id}/modelos/{modelo_id}/revisiones')
async def revisiones_bim(expediente_id: UUID, modelo_id: UUID,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    from app.services.bim_operational import BIMOperationalService
    from app.models.bim_revision import RevisionBIM
    model = await BIMOperationalService(db, user.tenant_id).modelo(modelo_id, expediente_id)
    rows = (await db.scalars(select(RevisionBIM).where(RevisionBIM.modelo_id == modelo_id,
        RevisionBIM.tenant_id == user.tenant_id).order_by(RevisionBIM.created_at.desc()))).all()
    return [{'id': str(r.id), 'fuente_sha256': r.fuente_sha256, 'tipos_admitidos': r.tipos_admitidos,
        'creado_en': r.created_at.isoformat(), 'actual': r.id == model.revision_actual_id} for r in rows]


@router.get('/{expediente_id}/modelos/{modelo_id}/cobertura')
async def cobertura_bim(expediente_id: UUID, modelo_id: UUID, revision_id: Optional[UUID] = None,
    estado: Optional[str] = None, skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    from app.services.bim_operational import BIMOperationalService
    return await BIMOperationalService(db, user.tenant_id).cobertura(modelo_id, expediente_id, revision_id, estado, skip, limit)


@router.get('/{expediente_id}/modelos/{modelo_id}/familias/{global_id}')
async def familia_bim(expediente_id: UUID, modelo_id: UUID, global_id: str, revision_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    from app.services.bim_operational import BIMOperationalService, rechazar
    ops = BIMOperationalService(db, user.tenant_id)
    revision = await ops.revision(await ops.modelo(modelo_id, expediente_id), revision_id)
    root = next((r for r in revision.cobertura if r['global_id'] == global_id), None)
    if root is None:
        rechazar('Familia no encontrada', 404)
    members = {global_id, *root['descendientes']}
    return [r for r in revision.cobertura if r['global_id'] in members]


@router.get('/{expediente_id}/modelos/{modelo_id}/referencias-contractuales')
async def referencias_bim(expediente_id: UUID, modelo_id: UUID,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    from app.services.bim_operational import BIMOperationalService
    return await BIMOperationalService(db, user.tenant_id).referencias(modelo_id, expediente_id)


class IncorporarTiposBIM(BaseModel):
    revision_id: UUID
    tipos: List[Literal['IfcMember', 'IfcPlate', 'IfcCurtainWall', 'IfcRamp', 'IfcRampFlight', 'IfcStairFlight']] = Field(min_length=1, max_length=6)


@router.post('/{expediente_id}/modelos/{modelo_id}/incorporar-tipos')
async def incorporar_tipos_bim(expediente_id: UUID, modelo_id: UUID, data: IncorporarTiposBIM,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_strict)):
    from app.services.bim_operational import BIMOperationalService
    ops = BIMOperationalService(db, user.tenant_id)
    model = await ops.modelo(modelo_id, expediente_id)
    revision = await ops.revision(model, data.revision_id)
    request = ReprocesarModeloRequest(tipos_elementos=sorted(set(revision.tipos_admitidos) | set(data.tipos)),
        extraer_malla=True, revision_esperada_id=revision.id)
    return await reprocesar_modelo(expediente_id, modelo_id, request, db, user, _rate_limit)


class LineaMedicionBIM(BaseModel):
    global_id: str = Field(min_length=1, max_length=100)
    catalogo_apu_id: Optional[UUID] = None
    cantidad: str = Field(min_length=1, max_length=40)
    referencia_medicion: str = Field(min_length=5, max_length=1000)
    alcance: str = Field(min_length=5, max_length=1000)


class GuardarDecisionBIM(BaseModel):
    revision_id: UUID
    familia_global_id: str = Field(min_length=1, max_length=100)
    criterio: Literal['PADRE', 'COMPONENTES']
    confirmar: bool = False
    lineas: List[LineaMedicionBIM] = Field(default_factory=list, max_length=500)
    referencia_contractual: str = Field(default='', max_length=2000)
    documento_id: Optional[UUID] = None
    exclusiones: Dict[str, str] = Field(default_factory=dict, max_length=2000)


@router.get('/{expediente_id}/modelos/{modelo_id}/decisiones-medicion')
async def decisiones_bim(expediente_id: UUID, modelo_id: UUID, revision_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    from app.services.bim_operational import BIMOperationalService
    return await BIMOperationalService(db, user.tenant_id).listar_decisiones(modelo_id, expediente_id, revision_id)


@router.post('/{expediente_id}/modelos/{modelo_id}/decisiones-medicion')
async def guardar_decision_bim(expediente_id: UUID, modelo_id: UUID, data: GuardarDecisionBIM,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_strict)):
    from app.services.bim_operational import BIMOperationalService
    ops = BIMOperationalService(db, user.tenant_id)
    decision = await ops.guardar_decision(modelo_id, expediente_id, user.id, data.model_dump())
    return {'id': str(decision.id), **await ops.estado_decision(decision)}


class PresupuestoDecisionesBIM(BaseModel):
    decisiones_ids: List[UUID] = Field(min_length=1, max_length=1000)
    parametros_costeo: ParametrosCosteoInput


@router.post('/{expediente_id}/modelos/{modelo_id}/presupuesto-decisiones')
async def presupuesto_decisiones_bim(expediente_id: UUID, modelo_id: UUID, data: PresupuestoDecisionesBIM,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_strict)):
    from app.services.bim_operational import BIMOperationalService
    from app.api.v1.presupuestos import PresupuestoOut
    result = await BIMOperationalService(db, user.tenant_id).crear_presupuesto(
        modelo_id, expediente_id, user.id, data.decisiones_ids, data.parametros_costeo.to_domain())
    return PresupuestoOut.model_validate(result)
