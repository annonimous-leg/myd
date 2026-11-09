# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
API de topografía: levantamientos, superficies TIN, volúmenes,
curvas de nivel, perfiles y geodesia.

Antes no existía ningún router para este dominio -- "topografía" no era
alcanzable desde la API en absoluto.
"""
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from pydantic import BaseModel, Field

from app.core.deps import (
    get_current_user, get_db, verificar_expediente_tenant,
    verificar_levantamiento_tenant, verificar_superficie_tenant,
)
from app.core.errors import MegalodonException, ErrorCode
from app.engines.topografia.exportacion import ExportadorTopografia
from app.models.expediente import ExpedienteObra
from app.models.topografia import Levantamiento
from app.services.topografia_service import TopografiaService
from app.config import settings
from app.utils.upload_limits import read_upload_with_limit
from app.services.planeacion_obra_service import PlaneacionObraService
from app.models.user import User
from app.schemas.costos import ParametrosCosteoInput
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


# ─── Schemas ─────────────────────────────────────────────────────────

class LevantamientoCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    crs: str = "EPSG:6362"
    srid: int = 6362
    tipo: str = "POLIGONAL"  # POLIGONAL, ALTIMETRICO, BATIMETRICO, CATASTRAL, GEODESICO


class LevantamientoOut(BaseModel):
    id: UUID
    expediente_id: UUID
    identificador: str
    nombre: str
    descripcion: Optional[str] = None
    crs: str
    srid: int
    tipo: str
    estado: str

    class Config:
        from_attributes = True


class PuntoInput(BaseModel):
    identificador: str
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)
    z: Optional[float] = Field(default=None, allow_inf_nan=False, description="Elevación en metros; obligatoria para superficies TIN")
    etiqueta: Optional[str] = None
    descripcion: Optional[str] = None
    precision_xy: float = 0.02
    precision_z: Optional[float] = None
    fuente: Optional[str] = None


class PuntoOut(BaseModel):
    id: UUID
    identificador: str
    etiqueta: Optional[str] = None
    x: float
    y: float
    z: Optional[float] = None

    class Config:
        from_attributes = True


class TriangularRequest(BaseModel):
    nombre: str
    tipo: str = "EXISTENTE"  # EXISTENTE | PROYECTO


class SuperficieOut(BaseModel):
    id: UUID
    levantamiento_id: UUID
    nombre: str
    tipo: str
    malla_vertices: List[float]
    malla_caras: List[int]
    area_plan_m2: float
    area_superficie_m2: float
    elevacion_min: float
    elevacion_max: float
    elevacion_media: float
    pendiente_media_pct: float
    num_puntos: int
    num_triangulos: int

    class Config:
        from_attributes = True


class SuperficieResumenOut(BaseModel):
    """Igual que SuperficieOut pero sin la malla -- para listados donde no
    hace falta cargar toda la geometría."""
    id: UUID
    levantamiento_id: UUID
    nombre: str
    tipo: str
    area_plan_m2: float
    elevacion_min: float
    elevacion_max: float
    num_puntos: int
    num_triangulos: int

    class Config:
        from_attributes = True


class VolumenRequest(BaseModel):
    superficie_existente_id: UUID
    superficie_proyecto_id: Optional[UUID] = None
    elevacion_referencia: Optional[float] = Field(default=None, allow_inf_nan=False, ge=-999999.9999, le=999999.9999)


class GenerarPresupuestoMovimientoRequest(BaseModel):
    nombre: str = "Presupuesto - Movimiento de tierras"
    parametros_costeo: ParametrosCosteoInput


class VolumenOut(BaseModel):
    id: UUID
    superficie_existente_id: UUID
    superficie_proyecto_id: Optional[UUID] = None
    elevacion_referencia: Optional[float] = None
    volumen_corte_m3: float
    volumen_terraplen_m3: float
    volumen_neto_m3: float
    area_analizada_m2: float
    evidencia: Optional[dict] = None

    class Config:
        from_attributes = True


class PerfilRequest(BaseModel):
    eje: List[Tuple[float, float]] = Field(..., min_length=2)
    intervalo_muestreo: float = 5.0


class TransformarRequest(BaseModel):
    puntos: List[Tuple[float, float]]
    crs_origen: str
    crs_destino: str


class CierrePoligonalRequest(BaseModel):
    vertices: List[Tuple[float, float]] = Field(..., min_length=3)


# ─── Levantamientos ──────────────────────────────────────────────────

@router.post("/{expediente_id}/levantamientos", response_model=LevantamientoOut)
async def crear_levantamiento(
    expediente_id: UUID, data: LevantamientoCreate,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
    _tenant_ok: None = Depends(verificar_expediente_tenant), _rate_limit: bool = Depends(rate_limit_strict),
):
    service = TopografiaService(db, current_user.tenant_id)
    return await service.crear_levantamiento(
        expediente_id=expediente_id, nombre=data.nombre, descripcion=data.descripcion,
        crs=data.crs, srid=data.srid, tipo=data.tipo, creado_por_id=current_user.id,
    )


@router.get("/{expediente_id}/levantamientos", response_model=List[LevantamientoOut])
async def listar_levantamientos(
    expediente_id: UUID, limit: int = 50,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
    _tenant_ok: None = Depends(verificar_expediente_tenant), _rate_limit: bool = Depends(rate_limit_standard),
):
    service = TopografiaService(db, current_user.tenant_id)
    return await service.listar_levantamientos(expediente_id, limit=limit)


@router.get("/levantamientos/{levantamiento_id}/superficies", response_model=List[SuperficieResumenOut])
async def listar_superficies(
    levantamiento_id: UUID,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
    _tenant_ok: None = Depends(verificar_levantamiento_tenant), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Lista de referencia sin la malla (más liviano) -- usar
    GET /superficies/{id} para traer la malla completa de una en concreto."""
    service = TopografiaService(db, current_user.tenant_id)
    return await service.listar_superficies(levantamiento_id)


@router.post("/levantamientos/{levantamiento_id}/puntos", response_model=List[PuntoOut])
async def agregar_puntos(
    levantamiento_id: UUID, puntos: List[PuntoInput],
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
    _tenant_ok: None = Depends(verificar_levantamiento_tenant), _rate_limit: bool = Depends(rate_limit_strict),
):
    service = TopografiaService(db, current_user.tenant_id)
    return await service.agregar_puntos(levantamiento_id, [p.model_dump() for p in puntos])


@router.get("/levantamientos/{levantamiento_id}/puntos", response_model=List[PuntoOut])
async def listar_puntos(
    levantamiento_id: UUID, limit: int = 5000,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
    _tenant_ok: None = Depends(verificar_levantamiento_tenant), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Puntos ya persistidos de un levantamiento (antes solo se veían como
    efecto colateral de agregar_puntos/importar_csv en la misma sesión)."""
    service = TopografiaService(db, current_user.tenant_id)
    return await service.listar_puntos(levantamiento_id, limit)


@router.post("/levantamientos/{levantamiento_id}/importar-csv", response_model=List[PuntoOut])
async def importar_csv(
    levantamiento_id: UUID,
    file: UploadFile = File(...),
    formato: str = Form("penzd"),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
    _tenant_ok: None = Depends(verificar_levantamiento_tenant), _rate_limit: bool = Depends(rate_limit_strict),
):
    """formato: 'penzd' (Punto,Este,Norte,Elevación,Descripción, el
    estándar de estación total) o 'generico' (CSV con encabezados)."""
    service = TopografiaService(db, current_user.tenant_id)
    contenido = (await read_upload_with_limit(file, settings.GENERAL_UPLOAD_MAX_FILE_SIZE_MB)).decode("utf-8")
    return await service.importar_puntos_csv(levantamiento_id, contenido, formato)


@router.post("/levantamientos/{levantamiento_id}/triangular", response_model=SuperficieOut)
async def triangular_superficie(
    levantamiento_id: UUID, data: TriangularRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
    _tenant_ok: None = Depends(verificar_levantamiento_tenant), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Construye una superficie TIN real (Delaunay) a partir de todos los
    puntos ya cargados en el levantamiento."""
    service = TopografiaService(db, current_user.tenant_id)
    return await service.triangular_superficie(levantamiento_id, data.nombre, data.tipo, creado_por_id=current_user.id)


# ─── Superficies ─────────────────────────────────────────────────────

@router.get("/superficies/{superficie_id}", response_model=SuperficieOut)
async def obtener_superficie(
    superficie_id: UUID,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
    superficie=Depends(verificar_superficie_tenant), _rate_limit: bool = Depends(rate_limit_standard),
):
    return superficie


@router.get("/superficies/{superficie_id}/curvas-nivel")
async def curvas_nivel(
    superficie_id: UUID, intervalo: float = 1.0,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
    _tenant_ok: None = Depends(verificar_superficie_tenant), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Curvas de nivel reales, cortando la malla TIN a cada elevación."""
    service = TopografiaService(db, current_user.tenant_id)
    curvas = await service.generar_curvas_nivel(superficie_id, intervalo)
    return {"intervalo": intervalo, "curvas": curvas}


@router.post("/superficies/{superficie_id}/perfil")
async def generar_perfil(
    superficie_id: UUID, data: PerfilRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
    _tenant_ok: None = Depends(verificar_superficie_tenant), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Perfil longitudinal de terreno a lo largo de un eje (ej. eje de
    camino), muestreado sobre la superficie TIN ya triangulada."""
    service = TopografiaService(db, current_user.tenant_id)
    perfil = await service.generar_perfil(superficie_id, data.eje, data.intervalo_muestreo)
    return [p.__dict__ for p in perfil]


# ─── Volúmenes ───────────────────────────────────────────────────────

@router.post("/volumenes", response_model=VolumenOut)
async def calcular_volumen(
    data: VolumenRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Corte/terraplén real entre dos superficies TIN, o entre una
    superficie y una elevación de referencia plana."""
    # BUG ORIGINAL: ninguna de las dos superficies se validaba contra el
    # tenant del usuario -- se calculaba volumen mezclando datos de
    # topografía de cualquier tenant con solo conocer sus UUID.
    from app.models.topografia import SuperficieTIN
    from app.models.expediente import ExpedienteObra

    ids = [data.superficie_existente_id, data.superficie_proyecto_id]
    for sid in [i for i in ids if i is not None]:
        result = await db.execute(
            select(SuperficieTIN.id)
            .join(ExpedienteObra, SuperficieTIN.expediente_id == ExpedienteObra.id)
            .where(SuperficieTIN.id == sid)
            .where(ExpedienteObra.tenant_id == current_user.tenant_id)
        )
        if result.scalar_one_or_none() is None:
            raise MegalodonException(ErrorCode.SUPERFICIE_NO_ENCONTRADA, f"Superficie {sid} no encontrada")

    service = TopografiaService(db, current_user.tenant_id)
    return await service.calcular_volumen(
        superficie_existente_id=data.superficie_existente_id,
        superficie_proyecto_id=data.superficie_proyecto_id,
        elevacion_referencia=data.elevacion_referencia,
        creado_por_id=current_user.id,
    )


@router.post("/{expediente_id}/volumenes/{calculo_id}/generar-presupuesto")
async def generar_presupuesto_movimiento_tierras(
    expediente_id: UUID,
    calculo_id: UUID,
    data: GenerarPresupuestoMovimientoRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _tenant_ok: None = Depends(verificar_expediente_tenant), _rate_limit: bool = Depends(rate_limit_strict),
):
    """expediente_id en el path -- antes era query param suelto, lo que
    no validaba que el cálculo perteneciera al expediente."""
    from app.api.v1.presupuestos import PresupuestoOut
    from app.models.topografia import CalculoVolumen

    # CalculoVolumen.expediente_id ya viene denormalizado (antes había
    # que caminar calculo->superficie->levantamiento->expediente).
    calculo = await db.get(CalculoVolumen, calculo_id)
    if not calculo or str(calculo.expediente_id) != str(expediente_id):
        raise MegalodonException(ErrorCode.TOPOGRAFIA_ERROR, "El cálculo no pertenece al expediente indicado")

    service = TopografiaService(db, current_user.tenant_id)
    presupuesto = await service.generar_partida_movimiento_tierras(
        calculo_volumen_id=calculo_id,
        expediente_id=expediente_id,
        nombre=data.nombre,
        parametros_costeo=data.parametros_costeo.to_domain(),
        creado_por_id=current_user.id,
    )
    return PresupuestoOut.model_validate(presupuesto)


# ─── Geodesia ────────────────────────────────────────────────────────

@router.post("/geodesia/transformar")
async def transformar_coordenadas(
    data: TransformarRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    service = TopografiaService(db, current_user.tenant_id)
    transformados = service.transformar_coordenadas(data.puntos, data.crs_origen, data.crs_destino)
    return {"puntos": transformados}


@router.post("/geodesia/cierre-poligonal")
async def cierre_poligonal(
    data: CierrePoligonalRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    service = TopografiaService(db, current_user.tenant_id)
    resultado = service.cierre_poligonal(data.vertices)
    return resultado.__dict__



@router.post("/levantamientos/{levantamiento_id}/importar-las")
async def importar_las(
    levantamiento_id: UUID,
    archivo: UploadFile = File(...),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_standard),
):
    """Importa nube de puntos desde archivo LAS/LAZ a un levantamiento existente."""
    # Verify levantamiento belongs to tenant
    result = await db.execute(
        select(Levantamiento).where(
            Levantamiento.id == levantamiento_id,
            Levantamiento.expediente.has(ExpedienteObra.tenant_id == current_user.tenant_id)
        )
    )
    levantamiento = result.scalar_one_or_none()
    if not levantamiento:
        raise HTTPException(status_code=404, detail="Levantamiento no encontrado o sin acceso")

    # Validate file extension
    if not archivo.filename.lower().endswith(('.las', '.laz')):
        raise HTTPException(status_code=400, detail="Solo archivos .las o .laz son soportados")

    contenido = await read_upload_with_limit(archivo, settings.TENDER_SOURCE_MAX_FILE_SIZE_MB)

    service = TopografiaService(db, current_user.tenant_id)
    resultado = await service.importar_las(levantamiento_id, contenido)

    return resultado

# ═══════════════════════════════════════════════════════════════════════════
# EXPORTACIÓN — DXF, CSV, XYZ, LandXML
# ═══════════════════════════════════════════════════════════════════════════

class PlaneacionObraRequest(BaseModel):
    puntos: List[Tuple[float, float, float]] = Field(..., min_length=3)
    cota_objetivo: float
    salto_terrazas: float = Field(default=0.5, gt=0)
    claves_catalogo: Dict[str, str]
    zona_economica: Optional[str] = None
    estado: Optional[str] = None


@router.post("/planeacion-obra/{expediente_id}")
async def generar_planeacion_obra(
    expediente_id: UUID, data: PlaneacionObraRequest, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _expediente: ExpedienteObra = Depends(verificar_expediente_tenant),
    _rate_limit: bool = Depends(rate_limit_strict),
):
    service = PlaneacionObraService(db)
    resultado = await service.generar_plan(current_user.tenant_id, data.puntos, data.cota_objetivo,
        data.salto_terrazas, data.claves_catalogo, data.zona_economica, data.estado)
    resultado["expediente_id"] = str(expediente_id)
    resultado["tenant_id"] = str(current_user.tenant_id)
    return resultado


class ExportarRequest(BaseModel):
    nombre: str = "levantamiento"
    puntos: List[Tuple[float, float, float]]
    caras: Optional[List[int]] = None
    formato: str = Field(default="csv", pattern=r"^(csv|xyz|dxf|landxml)$")


@router.post("/exportar")
async def exportar_topografia(
    data: ExportarRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
    _rate_limit: bool = Depends(rate_limit_standard),
):
    """Exporta datos topográficos a CSV, XYZ, DXF o LandXML."""
    exportador = ExportadorTopografia()

    if data.formato == "csv":
        resultado = exportador.exportar_puntos_csv(data.puntos, data.nombre)
    elif data.formato == "xyz":
        resultado = exportador.exportar_puntos_xyz(data.puntos, data.nombre)
    elif data.formato == "dxf":
        if not data.caras:
            raise HTTPException(status_code=400, detail="DXF requiere caras (triángulos)")
        # Flatten puntos for vertices
        vertices = []
        for p in data.puntos:
            vertices.extend([p[0], p[1], p[2]])
        resultado = exportador.exportar_superficie_dxf(data.nombre, vertices, data.caras)
    elif data.formato == "landxml":
        if not data.caras:
            raise HTTPException(status_code=400, detail="LandXML requiere caras (triángulos)")
        resultado = exportador.exportar_landxml(data.nombre, data.puntos, data.caras)
    else:
        raise HTTPException(status_code=400, detail=f"Formato no soportado: {data.formato}")

    return {
        "nombre_archivo": resultado.nombre_archivo,
        "media_type": resultado.media_type,
        "formato": resultado.formato,
        "tamano_bytes": len(resultado.contenido),
        "contenido_base64": __import__('base64').b64encode(resultado.contenido).decode('utf-8'),
    }
