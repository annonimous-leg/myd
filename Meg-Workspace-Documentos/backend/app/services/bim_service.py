# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
BIMService - Gestión de modelos IFC: cuantificación real, persistencia y
enlace con presupuestos.

BUG ORIGINAL: procesar_ifc() nunca persistía nada en BD (ni el ModeloBIM
ni los ElementoBIM) -- solo regresaba un dict de la request y se perdía
todo. Ahora sí queda guardado, incluida la malla para renderizar en el
frontend y el puente elemento->partida.
"""
import os
import math
try:
    import structlog  # type: ignore
    logger = structlog.get_logger()
except ModuleNotFoundError:  # pragma: no cover - compatibilidad de entorno
    import logging
    logger = logging.getLogger(__name__)

import tempfile
from datetime import datetime, timezone
from typing import BinaryIO, List, Optional, Dict, Any, TYPE_CHECKING
from uuid import UUID, uuid4
from types import SimpleNamespace

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession
from sqlalchemy.orm import defer

from app.models.presupuesto import Presupuesto, Partida
from app.models.bim import ModeloBIM, ElementoBIM
from app.models.base import EstadoProceso
from app.models.expediente import ExpedienteObra
from app.engines.bim.motor_bim import MotorBIM
from app.engines.bim.coverage import conflictos_de_conjuntos
from app.engines.bim.heuristics import estimar_duracion_4d, resumir_grupo_bim4d
from app.integrations.supabase_storage import storage_bim
from app.core.errors import MegalodonException, ErrorCode
from app.engines.costos.parametros import ParametrosCosteoSnapshot

if TYPE_CHECKING:
    from app.models.bim import GeneracionBIM4D5D
    from app.models.programacion import ProgramaObra

# Tipos cuyo insumo relevante es área (m2) en vez de volumen (m3).
TIPOS_POR_AREA = {"IfcWall", "IfcSlab", "IfcRoof", "IfcCovering"}
TIPOS_POR_PIEZA = {"IfcDoor", "IfcWindow"}


def cantidad_bim(elementos, unidad: str) -> float:
    """Incomplete groups stay pending, rather than costing only measurable members."""
    if unidad == "pza":
        return float(len(elementos))
    field = {"m2": "area", "m3": "volumen", "ml": "longitud", "m": "longitud"}.get(unidad)
    if field is None:
        raise MegalodonException(ErrorCode.BIM_ERROR, f"Unidad '{unidad}' no derivable de BIM")
    values = [getattr(e, field) for e in elementos]
    if any(v is None or not math.isfinite(float(v)) or v <= 0 for v in values):
        return 0.0
    return sum(float(v) for v in values)


class BIMService:
    """Servicio de procesamiento BIM/IFC."""

    def __init__(self, db: AsyncSession, tenant_id: Optional[UUID | str] = None):
        self.db = db
        self.tenant_id = UUID(str(tenant_id)) if tenant_id is not None else None
        self.motor = MotorBIM()

    async def listar_modelos(self, expediente_id: UUID) -> List[ModeloBIM]:
        """Lista los modelos BIM de un expediente (más reciente primero).

        BUG ORIGINAL: no existía ningún endpoint para enumerar los modelos
        de un expediente -- solo se podía pedir un modelo si ya sabías su
        modelo_id de antemano (ej. guardado en otra pantalla).
        """
        result = await self.db.execute(
            select(ModeloBIM)
            .where(ModeloBIM.expediente_id == expediente_id, ModeloBIM.tenant_id == self.tenant_id)
            .order_by(ModeloBIM.created_at.desc())
        )
        return list(result.scalars().all())

    async def crear_modelo(
        self,
        *,
        expediente_id: UUID,
        nombre: str,
        file_content: bytes | BinaryIO,
        filename: str,
        file_size: Optional[int] = None,
        opciones_procesamiento: Optional[dict] = None,
        descripcion: Optional[str] = None,
        creado_por_id: Optional[UUID] = None,
    ) -> ModeloBIM:
        """Registra un modelo BIM y sube el IFC original a Supabase
        Storage. El path guardado en BD es el path DENTRO del bucket
        (nunca una URL firmada -- esas expiran; se genera al vuelo cuando
        se necesite descargar, vía SupabaseStorage.url_firmada)."""
        result = await self.db.execute(select(ExpedienteObra).where(ExpedienteObra.id == expediente_id, ExpedienteObra.tenant_id == self.tenant_id))
        expediente_obj = result.scalar_one_or_none()
        if not expediente_obj:
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, f"Expediente {expediente_id} no encontrado")

        modelo_id = uuid4()
        identificador = f"BIM-{modelo_id}"
        # Immutable key independent of the user-supplied filename and row count.
        ruta_storage = f"tenant/{self.tenant_id}/{expediente_id}/{modelo_id}/original.ifc"
        storage = storage_bim()
        await storage.subir(ruta_storage, file_content, content_type="application/x-step", overwrite=False)

        modelo = ModeloBIM(
            id=modelo_id,
            expediente_id=expediente_id,
            tenant_id=expediente_obj.tenant_id,
            identificador=identificador,
            nombre=nombre,
            descripcion=descripcion,
            ruta_archivo=ruta_storage,
            tamano_bytes=file_size if file_size is not None else len(file_content),
            estado_procesamiento=EstadoProceso.PENDIENTE.value,
            creado_por_id=creado_por_id,
            actualizado_por_id=creado_por_id,
        )
        self.db.add(modelo)
        from app.core.process_queue import registrar_trabajo
        registrar_trabajo(self.db, modelo, 'BIM_IFC', opciones_procesamiento or {})
        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            try:
                bind = self.db.bind
                engine = bind.engine if isinstance(bind, AsyncConnection) else bind
                async with AsyncSession(bind=engine) as reconciliation:
                    persisted = await reconciliation.scalar(
                        select(ModeloBIM.id).where(
                            ModeloBIM.id == modelo_id,
                            ModeloBIM.tenant_id == self.tenant_id,
                            ModeloBIM.ruta_archivo == ruta_storage,
                        )
                    )
            except Exception:
                logger.exception("bim_upload_commit_unknown", path=ruta_storage)
            else:
                if persisted is not None:
                    return await self.db.get(ModeloBIM, persisted)
                try:
                    await storage.eliminar([ruta_storage])
                except Exception:
                    logger.exception("bim_storage_cleanup_failed", path=ruta_storage)
            raise
        await self.db.refresh(modelo)
        return modelo

    async def _validar_modelo_en_expediente(self, modelo_id: UUID, expediente_id: UUID, *, bloquear: bool = False) -> ModeloBIM:
        """Obtiene el modelo y verifica que pertenezca al expediente de la URL.
        Levanta 404 si no existe o si el expediente no coincide (no 403, para
        no revelar que el modelo existe bajo otro expediente)."""
        query = select(ModeloBIM).where(ModeloBIM.id == modelo_id, ModeloBIM.expediente_id == expediente_id, ModeloBIM.tenant_id == self.tenant_id)
        if bloquear:
            query = query.with_for_update().execution_options(populate_existing=True)
        modelo = (await self.db.execute(query)).scalar_one_or_none()
        if not modelo or str(modelo.expediente_id) != str(expediente_id) or (self.tenant_id is not None and str(modelo.tenant_id) != str(self.tenant_id)):
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Modelo BIM {modelo_id} no encontrado en el expediente {expediente_id}",
            )
        return modelo

    async def url_descarga_modelo(self, modelo_id: UUID, expediente_id: UUID, expira_segundos: int = 3600) -> str:
        """URL temporal para descargar el IFC original directo de storage."""
        modelo = await self._validar_modelo_en_expediente(modelo_id, expediente_id)
        url = await storage_bim().url_firmada(modelo.ruta_archivo, expira_segundos)
        if not url:
            raise MegalodonException(ErrorCode.ARCHIVO_ERROR, "No se pudo generar la URL de descarga")
        return url

    async def procesar_ifc(
        self,
        *,
        modelo_id: UUID,
        file_content: bytes,
        tipos_elementos: Optional[List[str]] = None,
        extraer_malla: bool = True,
    ) -> ModeloBIM:
        """Procesa el IFC de un ModeloBIM ya registrado: cuantifica y
        persiste elementos reales. Deja el modelo en COMPLETADO o ERROR."""
        modelo = (await self.db.execute(select(ModeloBIM).where(ModeloBIM.id == modelo_id, ModeloBIM.tenant_id == self.tenant_id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if not modelo:
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, f"Modelo BIM {modelo_id} no encontrado")

        savepoint = await self.db.begin_nested()
        modelo.estado_procesamiento = EstadoProceso.EN_PROCESO.value
        modelo.tamano_bytes = len(file_content)
        # Keep the aggregate lock until the replacement and summary commit together.

        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        try:
            ifc_file = self.motor.cargar_ifc(tmp_path)
            try:
                modelo.version_ifc = ifc_file.schema
            except Exception as e:
                # No crítico -- el procesamiento sigue sin la versión de
                # schema, pero se deja traza porque un IFC del que no se
                # puede leer ni el schema suele indicar un archivo
                # corrupto o un parser desactualizado.
                logger.debug("bim_service.procesar_ifc: no se pudo leer version_ifc", modelo_id=str(modelo_id), error=str(e))

            resultado = self.motor.cuantificar(tipos_elementos, extraer_malla=extraer_malla)

            if resultado.errores:
                raise MegalodonException(ErrorCode.BIM_ERROR, "; ".join(resultado.errores[:20]))
            if not resultado.elementos:
                raise MegalodonException(ErrorCode.BIM_ERROR, "El IFC no contiene elementos cuantificables")
            global_ids = [e.global_id for e in resultado.elementos]
            if len(set(global_ids)) != len(global_ids):
                raise MegalodonException(ErrorCode.BIM_ERROR, "GlobalId duplicado en el IFC")
            existing = {e.global_id: e for e in (await self.db.execute(
                select(ElementoBIM).where(ElementoBIM.modelo_id == modelo_id)
            )).scalars().all()}
            for elem in resultado.elementos:
                row = existing.pop(elem.global_id, None)
                if row is None:
                    row = ElementoBIM(id=uuid4(), modelo_id=modelo_id, global_id=elem.global_id)
                    self.db.add(row)
                # Identity, budget mapping and manual zones survive retries/reprocessing.
                for field in ("express_id", "tipo", "nombre", "volumen", "area", "longitud",
                              "fuente_volumen", "fuente_area", "nivel", "bbox", "propiedades"):
                    setattr(row, field, getattr(elem, field))
                row.malla_vertices = elem.malla.vertices if elem.malla else None
                row.malla_caras = elem.malla.caras if elem.malla else None
            for obsolete in existing.values():
                await self.db.delete(obsolete)

            from app.services.bim_operational import registrar_revision
            await registrar_revision(self.db, modelo, ifc_file, resultado, file_content, tipos_elementos)
            modelo.num_elementos = len(resultado.elementos)
            modelo.niveles = resultado.niveles
            # Si TODOS los elementos fallaron, es un error real; si solo
            # algunos, se deja COMPLETADO pero con el detalle en
            # error_procesamiento para que no se pierda silenciosamente.
            if resultado.elementos:
                modelo.estado_procesamiento = EstadoProceso.COMPLETADO.value
            else:
                modelo.estado_procesamiento = EstadoProceso.ERROR.value

            modelo.error_procesamiento = "; ".join(resultado.errores[:20])[:2000] if resultado.errores else None

            await self.db.flush()
            await savepoint.commit()
            await self.db.commit()
            return modelo

        except Exception as e:
            # Antes: el error solo quedaba en error_procesamiento (DB),
            # invisible en logs/observabilidad server-side hasta que
            # alguien abriera ese modelo puntual. Se relanza igual (el
            # caller/worker decide reintentar), pero ahora también queda
            # en logs con contexto de qué modelo falló.
            logger.exception("bim_service.procesar_ifc: fallo procesando IFC", modelo_id=str(modelo_id), error=str(e))
            if self.db.get_nested_transaction() is None:
                # The outer commit failed; its lock is gone. Never overwrite a newer success.
                await self.db.rollback()
                raise
            await savepoint.rollback()
            modelo = (await self.db.execute(select(ModeloBIM).where(ModeloBIM.id == modelo_id, ModeloBIM.tenant_id == self.tenant_id).with_for_update())).scalar_one()
            modelo.estado_procesamiento = EstadoProceso.ERROR.value
            modelo.error_procesamiento = str(e)[:2000]
            await self.db.commit()
            raise
        finally:
            os.unlink(tmp_path)

    async def listar_elementos(
        self,
        modelo_id: UUID,
        expediente_id: UUID,
        tipo: Optional[str] = None,
        nivel: Optional[str] = None,
        incluir_malla: bool = False,
        limit: int = 200,
        offset: int = 0,
    ) -> List[ElementoBIM]:
        await self._validar_modelo_en_expediente(modelo_id, expediente_id)
        query = select(ElementoBIM).join(ModeloBIM, ModeloBIM.id == ElementoBIM.modelo_id).where(ElementoBIM.modelo_id == modelo_id, ModeloBIM.tenant_id == self.tenant_id)
        if tipo:
            query = query.where(ElementoBIM.tipo == tipo)
        if nivel:
            query = query.where(ElementoBIM.nivel == nivel)
        if not incluir_malla:
            query = query.options(defer(ElementoBIM.malla_vertices), defer(ElementoBIM.malla_caras))
        query = query.order_by(ElementoBIM.tipo, ElementoBIM.id).limit(limit).offset(offset)
        result = await self.db.execute(query)
        elementos = list(result.scalars().all())
        # Serialize copies: suppressing mesh must never dirty persisted ORM rows.
        return [SimpleNamespace(**{c.key: (None if not incluir_malla and c.key in
                ("malla_vertices", "malla_caras") else getattr(e, c.key))
                for c in ElementoBIM.__table__.columns}) for e in elementos]

    async def mapear_a_partidas(self, modelo_id: UUID, expediente_id: UUID, mapeos: List[Dict[str, Any]]) -> int:
        """Asocia elementos BIM a partidas de presupuesto ya existentes.

        mapeos: [{"elemento_id": UUID, "partida_id": UUID}, ...]
        """
        await self._validar_modelo_en_expediente(modelo_id, expediente_id, bloquear=True)
        validated = []
        for m in mapeos:
            elem = (await self.db.execute(select(ElementoBIM).where(
                ElementoBIM.id == m["elemento_id"], ElementoBIM.modelo_id == modelo_id
            ).with_for_update())).scalar_one_or_none()
            partida = (await self.db.execute(select(Partida).join(Presupuesto,
                Presupuesto.id == Partida.presupuesto_id).where(
                Partida.id == m["partida_id"], Partida.tenant_id == self.tenant_id,
                Presupuesto.tenant_id == self.tenant_id, Presupuesto.expediente_id == expediente_id
            ))).scalar_one_or_none()
            if elem is None or partida is None:
                raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                    "Elemento o partida no encontrado en este expediente")
            if elem.tipo == 'IfcBuildingElementProxy':
                raise MegalodonException(ErrorCode.BIM_ERROR,
                    'El Proxy requiere clasificación funcional antes del mapeo económico', status_code=409)
            validated.append((elem, partida.id))
        for elem, partida_id in validated:
            elem.partida_id = partida_id
        await self.db.commit()
        return len(validated)

    async def crear_presupuesto_desde_bim(
        self,
        *,
        modelo_id: UUID,
        expediente_id: UUID,
        nombre: str = "Presupuesto desde BIM",
        parametros_costeo: ParametrosCosteoSnapshot,
        mapeo_catalogo: Optional[Dict[str, UUID]] = None,
        mapeo_elementos: Optional[Dict[UUID, UUID]] = None,
        cantidades_complementarias: Optional[List[dict]] = None,
        creado_por_id: Optional[UUID] = None,
        solicitud: dict[str, str] | None = None,
    ) -> Presupuesto:
        """Crea un presupuesto 5D sin asumir que un tipo IFC equivale a un APU.

        `mapeo_catalogo` conserva el atajo {tipo_ifc: catalogo_apu_id}.
        `mapeo_elementos` permite sobrescribirlo por elemento
        {elemento_id: catalogo_apu_id}. Esto evita mezclar en una sola
        partida muros, losas u otros elementos del mismo IfcType pero con
        especificaciones/materiales distintos.

        Elementos que terminan con el mismo tipo y el mismo APU se agregan
        juntos; un APU distinto crea otra partida. Los elementos sin APU
        siguen como cuantificación pendiente de costeo. Toda referencia a
        elemento/APU se valida dentro del modelo, expediente y tenant."""
        source_model = await self._validar_modelo_en_expediente(modelo_id, expediente_id, bloquear=True)
        from app.services.presupuesto_service import PresupuestoService
        from app.models.catalogo_apu import CatalogoAPU

        presupuesto_service = PresupuestoService(self.db, self.tenant_id)
        if solicitud is not None:
            cobertura = Presupuesto.metadatos["bim_cobertura"]
            anterior = (await self.db.execute(
                select(Presupuesto.id, Presupuesto.metadatos).where(
                    Presupuesto.expediente_id == expediente_id,
                    Presupuesto.tenant_id == self.tenant_id,
                    cobertura["modelo_id"].as_string() == str(modelo_id),
                    cobertura["solicitud"]["clave"].as_string() == solicitud["clave"],
                )
            )).one_or_none()
            if anterior is not None:
                if anterior.metadatos["bim_cobertura"]["solicitud"]["huella"] != solicitud["huella"]:
                    raise MegalodonException(
                        ErrorCode.CONFLICT, "La clave ya se usó con otro presupuesto", status_code=409
                    )
                return await presupuesto_service._reconstruir_partidas_desde_db(anterior.id, expediente_id)


        result = await self.db.execute(
            select(ElementoBIM)
            .options(defer(ElementoBIM.malla_vertices), defer(ElementoBIM.malla_caras))
            .join(ModeloBIM, ModeloBIM.id == ElementoBIM.modelo_id)
            .where(
                ElementoBIM.modelo_id == modelo_id,
                ModeloBIM.tenant_id == self.tenant_id,
            )
        )
        elementos = list(result.scalars().all())
        if not elementos:
            raise MegalodonException(
                ErrorCode.BIM_ERROR,
                "El modelo BIM no tiene elementos cuantificados todavía",
            )
        elementos_por_id = {e.id: e for e in elementos}

        mapeo_catalogo = dict(mapeo_catalogo or {})
        mapeo_elementos = dict(mapeo_elementos or {})
        ids_elementos_mapeados = set(mapeo_elementos)
        if not ids_elementos_mapeados.issubset(elementos_por_id):
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                "El mapeo 5D contiene elementos ajenos al modelo.",
            )

        expediente = (
            await self.db.execute(
                select(ExpedienteObra).where(
                    ExpedienteObra.id == expediente_id,
                    *(
                        [ExpedienteObra.tenant_id == self.tenant_id]
                        if self.tenant_id is not None
                        else []
                    ),
                )
            )
        ).scalar_one_or_none()
        if expediente is None:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Expediente {expediente_id} no encontrado",
            )

        # Resolver todos los APUs una sola vez, con aislamiento de tenant.
        requested_apu_ids = set(mapeo_catalogo.values()) | set(mapeo_elementos.values())
        catalogos_por_id: Dict[UUID, CatalogoAPU] = {}
        if requested_apu_ids:
            result_apu = await self.db.execute(
                select(CatalogoAPU).where(
                    CatalogoAPU.id.in_(requested_apu_ids),
                    CatalogoAPU.tenant_id == expediente.tenant_id,
                )
            )
            catalogos_por_id = {c.id: c for c in result_apu.scalars().all()}
            missing_apus = requested_apu_ids - set(catalogos_por_id)
            if missing_apus:
                raise MegalodonException(
                    ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                    "Uno o más conceptos de catálogo del mapeo 5D no existen en este tenant.",
                )

        # El override por elemento gana al atajo por IfcType.
        grupos: Dict[tuple[str, Optional[UUID]], List[ElementoBIM]] = {}
        mapping_snapshot = []
        for element in elementos:
            explicit = mapeo_elementos.get(element.id)
            apu_id = explicit if explicit is not None else mapeo_catalogo.get(element.tipo)
            grupos.setdefault((element.tipo, apu_id), []).append(element)
            if apu_id is not None:
                mapping_snapshot.append({
                    "elemento_id": str(element.id),
                    "global_id": element.global_id,
                    "tipo_ifc": element.tipo,
                    "catalogo_apu_id": str(apu_id),
                    "origen_mapeo": "ELEMENTO" if explicit is not None else "TIPO_IFC",
                })

        conflicts = conflictos_de_conjuntos(elementos)
        conflict_guids = {gid for pair in conflicts for gid in pair.values()}

        # A missing member never discards the measured cost of its siblings.
        captures = {}
        for item in cantidades_complementarias or []:
            key = str(item["elemento_id"])
            value = float(item["cantidad"])
            reference = str(item.get("referencia", "")).strip()
            if (
                key in captures
                or not math.isfinite(value)
                or not 0 < value < 1e14
                or len(reference) < 5
            ):
                raise MegalodonException(
                    ErrorCode.BAD_REQUEST,
                    "Cantidad complementaria o referencia inválida",
                )
            captures[key] = {**item, "cantidad": value, "referencia": reference}
        if captures and creado_por_id is None:
            raise MegalodonException(
                ErrorCode.BAD_REQUEST,
                "La captura requiere un usuario responsable",
            )
        if captures:
            from app.models.user import User

            actor = await self.db.get(User, creado_por_id)
            if not actor or actor.tenant_id != self.tenant_id or not actor.is_active:
                raise MegalodonException(
                    ErrorCode.PERMISO_DENEGADO,
                    "Usuario de captura inválido",
                    status_code=403,
                )

        used = set()
        pending_ids, snapshots, measurements, geometric_pending = [], [], [], []
        partidas_data, grupos_partidas = [], []
        for (tipo, apu_id), elems in grupos.items():
            apu = catalogos_por_id.get(apu_id) if apu_id is not None else None
            unit = (
                (apu.unidad or "").lower().strip()
                if apu
                else "m2"
                if tipo in TIPOS_POR_AREA
                else "pza"
                if tipo in TIPOS_POR_PIEZA
                else "m3"
            )
            # The generic area field cannot distinguish a concept's required face,
            # net/gross basis or finish scope. Cost it only from reviewed capture.
            field = {"m3": "volumen", "m": "longitud", "ml": "longitud"}.get(unit)
            ready, missing, total = [], [], 0.0
            for element in elems:
                # Non-geometric catalogue units (kg, t, etc.) need an explicit
                # reviewed measurement; geometry alone cannot supply mass.
                value = 1.0 if unit == "pza" else getattr(element, field) if field else None
                original_value = value
                geometric = field == "volumen" and element.fuente_volumen == "GEOMETRIA_CALCULADA"
                valid = value is not None and math.isfinite(float(value)) and float(value) > 0 and not geometric
                if element.tipo == "IfcBuildingElementProxy":
                    valid = False
                capture = captures.get(str(element.id))
                if capture:
                    if valid or capture["unidad"].lower().strip() != unit:
                        raise MegalodonException(
                            ErrorCode.BAD_REQUEST,
                            "La captura completa faltantes o revisa estimaciones en la unidad del concepto",
                        )
                    used.add(str(element.id))
                    value, valid = capture["cantidad"], True
                    snapshots.append({
                        "elemento_id": str(element.id),
                        "global_id": element.global_id,
                        "unidad": unit,
                        "cantidad": value,
                        "referencia": capture["referencia"],
                        "usuario_id": str(creado_por_id),
                        "capturado_en": datetime.now(timezone.utc).isoformat(),
                        "fuente_original": element.fuente_volumen if field == "volumen" else "OTRA_MEDICION",
                        "cantidad_original": float(original_value) if original_value is not None else None,
                    })
                if element.global_id in conflict_guids or element.tipo == "IfcBuildingElementProxy":
                    valid = False
                if geometric and not capture:
                    geometric_pending.append(str(element.id))
                if valid:
                    measurements.append({
                        "elemento_id": str(element.id), "global_id": element.global_id,
                        "unidad": unit, "cantidad": float(value),
                        "fuente": "CAPTURA_REVISADA" if capture else element.fuente_volumen if field == "volumen" else "QTO_IFC" if field == "longitud" else "CONTEO",
                    })
                    ready.append(element)
                    total += float(value)
                else:
                    missing.append(element)
                    pending_ids.append(str(element.id))

            for members, quantity, label in [
                (ready, total, "medidos"),
                (missing, 0.0, "PENDIENTES DE MEDICIÓN"),
            ]:
                if not members:
                    continue
                data = {
                    "descripcion": f"{tipo} ({len(members)} elementos {label})"
                    + (f" — {apu.descripcion}" if apu else ""),
                    "unidad": apu.unidad if apu else unit,
                    "cantidad": round(quantity, 4),
                }
                if apu:
                    breakdown = (apu.desglose or {}).get("insumos") or []
                    if breakdown:
                        data["conceptos"] = [{
                            "clave": apu.clave,
                            "descripcion": apu.descripcion,
                            "unidad": apu.unidad,
                            "cantidad": 1.0,
                            "insumos": breakdown,
                        }]
                    else:
                        data["precio_unitario"] = float(apu.precio_unitario)
                partidas_data.append(data)
                grupos_partidas.append(members)

        if set(captures) != used:
            raise MegalodonException(
                ErrorCode.BAD_REQUEST,
                "Hay capturas para elementos ajenos al modelo o sin faltantes",
            )
        coverage = {
            "modelo_id": str(modelo_id),
            "revision_id": str(source_model.revision_actual_id) if source_model.revision_actual_id else None,
            "area_requiere_revision": True,
            "completa": not pending_ids,
            "elementos_totales": len(elementos),
            "elementos_medidos": len(elementos) - len(pending_ids),
            "elementos_pendientes": pending_ids,
            "capturas": snapshots,
            "mediciones_economicas": measurements,
            "volumenes_geometricos_pendientes": geometric_pending,
            "conflictos_conjuntos": conflicts,
            "reglas_candidatas_conjuntos": [{
                **pair, "regla": "PADRE_SI_CONCEPTO_INTEGRAL_O_COMPONENTES_SI_DESGLOSADO",
                "fuente": "JERARQUIA_IFC_Y_COMPONENTES_DE_MALLA",
                "sustento_contractual": None, "estado": "PENDIENTE_DE_APROBACION_ECONOMICA",
            } for pair in conflicts],
            "mapeo_apu_elementos": mapping_snapshot,
        }

        if solicitud is not None:
            coverage["solicitud"] = solicitud

        presupuesto = await presupuesto_service.crear_desde_costeo(
            expediente_id=expediente_id,
            nombre=nombre,
            partidas_data=partidas_data,
            parametros_costeo=parametros_costeo,
            creado_por_id=creado_por_id,
            evidencia_bim=coverage,
            auto_commit=False,
        )

        partidas_result = await self.db.execute(
            select(Partida)
            .join(Presupuesto, Presupuesto.id == Partida.presupuesto_id)
            .join(ExpedienteObra, ExpedienteObra.id == Presupuesto.expediente_id)
            .where(
                Partida.presupuesto_id == presupuesto.id,
                ExpedienteObra.tenant_id == self.tenant_id,
            )
            .order_by(Partida.numero)
        )
        partidas_creadas = list(partidas_result.scalars().all())
        for members, partida in zip(grupos_partidas, partidas_creadas, strict=True):
            for element in members:
                element.partida_id = partida.id

        await self.db.commit()
        return presupuesto

    async def asignar_zona_por_nivel(
        self, modelo_id: UUID, expediente_id: UUID, zona: str, nivel: Optional[str],
    ) -> int:
        await self._validar_modelo_en_expediente(modelo_id, expediente_id, bloquear=True)
        query = update(ElementoBIM).where(ElementoBIM.modelo_id == modelo_id)
        if nivel is not None:
            query = query.where(func.coalesce(func.nullif(ElementoBIM.nivel, ""), "Sin nivel") == nivel)
        result = await self.db.execute(query.values(zona_4d=zona).execution_options(synchronize_session=False))
        await self.db.commit()
        return result.rowcount

    async def asignar_zonas_4d(
        self,
        modelo_id: UUID,
        expediente_id: UUID,
        asignaciones: List[Dict[str, Any]],
    ) -> int:
        """Asigna zona_4d a elementos en lote. `asignaciones`:
        [{"elemento_id": UUID, "zona_4d": str}, ...]. Mismo estilo que
        mapear_a_partidas: sin zona_4d asignada, generar_actividades_4d
        cae de vuelta a `nivel`."""
        await self._validar_modelo_en_expediente(modelo_id, expediente_id, bloquear=True)

        elemento_ids = [a["elemento_id"] for a in asignaciones]
        result = await self.db.execute(
            select(ElementoBIM).join(ModeloBIM, ModeloBIM.id == ElementoBIM.modelo_id).where(
                ElementoBIM.id.in_(elemento_ids),
                ElementoBIM.modelo_id == modelo_id,
                ModeloBIM.tenant_id == self.tenant_id,
            )
        )
        elementos_por_id = {e.id: e for e in result.scalars().all()}

        actualizados = 0
        for a in asignaciones:
            elemento = elementos_por_id.get(a["elemento_id"])
            if elemento is not None:
                elemento.zona_4d = a["zona_4d"]
                actualizados += 1

        await self.db.commit()
        return actualizados

    async def crear_generacion_4d5d(
        self,
        modelo_id: UUID,
        expediente_id: UUID,
        dias_por_defecto: float,
        fecha_inicio: datetime,
        creado_por_id: Optional[UUID] = None,
    ) -> "GeneracionBIM4D5D":
        """Crea el registro de seguimiento PENDIENTE para una corrida de
        generación 4D. El router lo usa para tener un id que devolverle
        al frontend ANTES de encolar la tarea pesada -- la persistencia
        vive aquí, no en el router, igual que el resto del servicio."""
        from app.models.bim import GeneracionBIM4D5D

        modelo = await self._validar_modelo_en_expediente(modelo_id, expediente_id)

        generacion = GeneracionBIM4D5D(
            id=uuid4(),
            modelo_id=modelo_id,
            expediente_id=expediente_id,
            tenant_id=modelo.tenant_id,
            estado=EstadoProceso.PENDIENTE.value,
            dias_por_defecto=dias_por_defecto,
            creado_por_id=creado_por_id,
            actualizado_por_id=creado_por_id,
        )
        self.db.add(generacion)
        from app.core.process_queue import registrar_trabajo
        registrar_trabajo(self.db, generacion, 'BIM_4D', {
            'fecha_inicio_iso':fecha_inicio.isoformat(), 'dias_por_defecto':dias_por_defecto})
        await self.db.commit()
        await self.db.refresh(generacion)
        return generacion

    async def generar_actividades_4d(
        self,
        *,
        modelo_id: UUID,
        expediente_id: UUID,
        fecha_inicio: datetime,
        dias_por_defecto: float = 5.0,
        nombre_programa: Optional[str] = None,
        creado_por_id: Optional[UUID] = None,
        tenant_id: Optional[UUID | str] = None,
    ) -> "ProgramaObra":
        """Genera un ProgramaObra nuevo con una actividad por (zona,tipo)
        a partir de los elementos ya cuantificados de un modelo BIM, y
        las vincula en `elemento_bim_actividad`.

        Deliberadamente NO genera predecesoras/dependencias: secuenciar
        actividades es un criterio profesional del programador de obra,
        no algo que deba inventarse -- exactamente la misma limitación
        que la tesis de origen documenta sobre el cronograma automático
        de Bexel Manager (duraciones/secuencia genéricas que el
        especialista debe ajustar). `dias_por_defecto` sigue sin ser una
        estimación "inteligente" por tipo de elemento (eso requeriría
        rendimientos de obra reales que no tenemos) -- pero ya no se
        aplica igual a cada actividad sin importar su tamaño: se usa como
        el promedio del programa y se escala por el número de elementos
        de cada grupo relativo a ese promedio, acotado a un rango
        razonable. Sigue siendo una estimación gruesa para que el
        especialista la ajuste, no un sustituto de su criterio.

        Reutiliza ProgramacionService.crear_programa tal cual -- incluida
        su llamada a calcular_cpm al final -- en vez de reimplementar la
        creación de ActividadPrograma o el cálculo de ruta crítica. Este
        método nunca toca app/engines/programacion/cpm.py."""
        from app.models.programacion import ActividadPrograma, ProgramaObra
        from app.models.bim import ElementoBIMActividad
        from app.services.programacion_service import ProgramacionService

        modelo = await self._validar_modelo_en_expediente(modelo_id, expediente_id)

        result = await self.db.execute(select(ElementoBIM).join(ModeloBIM, ModeloBIM.id == ElementoBIM.modelo_id).where(ElementoBIM.modelo_id == modelo_id, ModeloBIM.tenant_id == self.tenant_id))
        elementos = list(result.scalars().all())
        if not elementos:
            raise MegalodonException(ErrorCode.BIM_ERROR, "El modelo BIM no tiene elementos cuantificados todavía")

        usa_zona_4d = any(e.zona_4d for e in elementos)
        agrupar_por = "zona_4d" if usa_zona_4d else "nivel"

        grupos: Dict[tuple, List[ElementoBIM]] = {}
        for e in elementos:
            zona = (e.zona_4d if usa_zona_4d else e.nivel) or "Sin zona asignada"
            grupos.setdefault((zona, e.tipo), []).append(e)

        # Costo presupuestado por grupo: prorratea el precio unitario ya
        # real de la partida vinculada (si el 5D ya se hizo) sobre la
        # cantidad de ESTE grupo -- no toma partida.importe completo
        # (que es el total del tipo en TODO el modelo, no solo de esta
        # zona), para no sobre-contar entre actividades de zonas distintas.
        partida_ids = {e.partida_id for e in elementos if e.partida_id}
        precios_por_partida: Dict[UUID, tuple] = {}
        capturas_por_elemento = {}
        presupuesto_por_partida = {}
        presupuestos_bim = set()
        presupuestos_con_snapshot = set()
        if partida_ids:
            result_p = await self.db.execute(select(Partida).join(Presupuesto, Presupuesto.id == Partida.presupuesto_id).join(ExpedienteObra, ExpedienteObra.id == Presupuesto.expediente_id).where(Partida.id.in_(partida_ids), ExpedienteObra.tenant_id == self.tenant_id))
            linked_parts = result_p.scalars().all()
            for p in linked_parts:
                if p.cantidad and p.cantidad > 0:
                    precios_por_partida[p.id] = (float(p.precio_unitario or 0), (p.unidad or "").lower().strip())
                presupuesto_por_partida[p.id] = p.presupuesto_id
            budgets = (await self.db.scalars(select(Presupuesto).where(
                Presupuesto.id.in_({p.presupuesto_id for p in linked_parts}),
                Presupuesto.tenant_id == self.tenant_id))).all()
            for budget in budgets:
                cobertura = (budget.metadatos or {}).get('bim_cobertura')
                if not cobertura:
                    continue
                presupuestos_bim.add(budget.id)
                if 'mediciones_economicas' in cobertura:
                    presupuestos_con_snapshot.add(budget.id)
                for capture in cobertura.get('mediciones_economicas', cobertura.get('capturas', [])):
                    capturas_por_elemento[(budget.id,capture['elemento_id'],capture['unidad'])] = float(capture['cantidad'])

        # Decision budgets may have multiple payment concepts for one element.
        # Use the latest explicit policy version and its persisted line amounts.
        policy_budget = await self.db.scalar(select(Presupuesto).where(
            Presupuesto.tenant_id == self.tenant_id, Presupuesto.expediente_id == expediente_id,
            Presupuesto.metadatos["bim_cobertura"]["modelo_id"].as_string() == str(modelo_id),
            Presupuesto.metadatos["bim_cobertura"]["decisiones_ids"].as_string().is_not(None),
        ).order_by(Presupuesto.created_at.desc()).limit(1))
        policy_costs = None
        if policy_budget is not None and (policy_budget.metadatos or {}).get('bim_cobertura', {}).get('decisiones_ids'):
            from app.services.bim_operational import BIMOperationalService
            if await BIMOperationalService(self.db, self.tenant_id).presupuesto_obsoleto(policy_budget):
                raise MegalodonException(ErrorCode.BIM_ERROR, 'Revisa el presupuesto por decisiones antes de generar 4D', status_code=409)
            parts = (await self.db.scalars(select(Partida).where(Partida.presupuesto_id == policy_budget.id,
                Partida.tenant_id == self.tenant_id).order_by(Partida.numero))).all()
            lines = policy_budget.metadatos['bim_cobertura']['mediciones_decisiones']
            policy_costs = {}
            for line, part in zip(lines, parts, strict=True):
                policy_costs[line['global_id']] = policy_costs.get(line['global_id'], 0.0) + float(part.importe)

        # `dias_por_defecto` funciona como base configurable. La duración
        # final se ajusta por tamaño del grupo y por la magnitud geométrica
        # real del bloque BIM para que la secuencia 4D no herede siempre el
        # mismo valor.
        num_grupos = len(grupos)
        promedio_elementos_por_grupo = (
            sum(len(elems) for elems in grupos.values()) / num_grupos if num_grupos else 1.0
        )
        pesos_grupo = {
            key: resumir_grupo_bim4d(elems).peso_geometrico_promedio
            for key, elems in grupos.items()
        }
        promedio_peso_por_grupo = (
            sum(pesos_grupo.values()) / num_grupos if num_grupos else 1.0
        )

        actividades_data = []
        orden_grupos = []
        for idx, ((zona, tipo), elems) in enumerate(sorted(grupos.items(), key=lambda kv: (kv[0][0], kv[0][1])), 1):
            costo = 0.0
            for e in elems:
                if policy_costs is not None:
                    costo += policy_costs.get(e.global_id, 0.0)
                    continue
                if e.partida_id and e.partida_id in precios_por_partida:
                    precio_unit, unidad = precios_por_partida[e.partida_id]
                    captura = capturas_por_elemento.get((presupuesto_por_partida[e.partida_id],str(e.id),unidad))
                    if captura is not None:
                        costo += precio_unit * captura
                    elif presupuesto_por_partida[e.partida_id] in presupuestos_con_snapshot:
                        continue  # A pending measurement cannot reappear as 4D money.
                    elif unidad == "m2" and presupuesto_por_partida[e.partida_id] not in presupuestos_bim:
                        costo += precio_unit * float(e.area or 0)
                    elif unidad == "m3" and e.fuente_volumen != "GEOMETRIA_CALCULADA":
                        costo += precio_unit * float(e.volumen or 0)
                    elif unidad in ("ml", "m"):
                        costo += precio_unit * float(e.longitud or 0)
                    elif unidad == "pza":
                        costo += precio_unit

            peso_grupo = pesos_grupo.get((zona, tipo), 0.0)
            duracion_grupo = estimar_duracion_4d(
                elementos=elems,
                dias_base=dias_por_defecto,
                promedio_cantidad_grupo=promedio_elementos_por_grupo,
                promedio_peso_grupo=promedio_peso_por_grupo,
            )

            identificador = f"BIM4D-{idx:03d}"
            actividades_data.append({
                "id": identificador,
                "nombre": f"{tipo} — {zona}",
                "descripcion": f"Generado automáticamente desde BIM ({len(elems)} elementos)",
                "wbs_codigo": f"{idx:03d}",
                "duracion": duracion_grupo,
                "tipo": "CONSTRUCCION",
                "costo_presupuestado": round(costo, 2),
                "metadatos": {
                    "origen": "bim_4d",
                    "modelo_id": str(modelo_id),
                    "num_elementos": len(elems),
                    "duracion_base_dias": dias_por_defecto,
                    "peso_geometrico_grupo": round(peso_grupo, 4),
                    "promedio_peso_grupo": round(promedio_peso_por_grupo, 4),
                    "factor_duracion_aplicado": round(duracion_grupo / dias_por_defecto if dias_por_defecto else 1.0, 2),
                },
            })
            orden_grupos.append((identificador, elems))

        prog_service = ProgramacionService(self.db, self.tenant_id, actor_id=creado_por_id)
        programa = await prog_service.crear_programa(
            expediente_id=expediente_id,
            nombre=nombre_programa or f"Cronograma 4D — {modelo.nombre}",
            descripcion=f"Generado desde el modelo BIM '{modelo.nombre}' ({agrupar_por} como agrupación).",
            fecha_inicio=fecha_inicio,
            actividades_data=actividades_data,
            creado_por_id=creado_por_id,
            tenant_id=tenant_id,
        )

        result_act = await self.db.execute(
            select(ActividadPrograma).join(ProgramaObra, ProgramaObra.id == ActividadPrograma.programa_id).join(ExpedienteObra, ExpedienteObra.id == ProgramaObra.expediente_id).where(ActividadPrograma.programa_id == programa.id, ExpedienteObra.tenant_id == self.tenant_id)
        )
        actividades_por_identificador = {a.identificador: a for a in result_act.scalars().all()}

        for identificador, elems in orden_grupos:
            actividad = actividades_por_identificador.get(identificador)
            if actividad is None:
                continue
            for e in elems:
                self.db.add(ElementoBIMActividad(id=uuid4(), elemento_bim_id=e.id, actividad_id=actividad.id))

        await self.db.commit()
        return programa
