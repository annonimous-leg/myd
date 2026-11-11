"""Durable generation of Megalodon-owned IFC technical drawing artifacts."""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
from tempfile import NamedTemporaryFile
from textwrap import wrap
from datetime import datetime, timezone
from typing import Iterable, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode, MegalodonException
from app.engines.bim.drawing import (
    MeshElement,
    Plane,
    build_elevation_document,
    build_plan_document,
    build_section_document,
    to_dxf,
    to_svg,
)
from app.engines.bim.drawing.sheet import SheetMeta, compose_a3_sheet, composed_to_pdf
from app.engines.bim.motor_bim import MotorBIM
from app.integrations.supabase_storage import storage_bim
from app.models.bim import DibujoBIM, ElementoBIM, ModeloBIM
from app.models.expediente import ExpedienteObra


_ALLOWED_TYPES = {"PLAN", "SECTION", "ELEVATION"}
_ALLOWED_FORMATS = {"SVG", "DXF", "PDF"}


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _finite_number(value: object, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise MegalodonException(ErrorCode.BIM_ERROR, f"Parámetro {field} inválido") from exc
    if not math.isfinite(number):
        raise MegalodonException(ErrorCode.BIM_ERROR, f"Parámetro {field} debe ser finito")
    return number


def _canonical_parameters(kind: str, parameters: dict) -> dict:
    if not isinstance(parameters, dict):
        raise MegalodonException(ErrorCode.BIM_ERROR, "Los parámetros de dibujo deben ser un objeto")
    tolerance = _finite_number(parameters.get("tolerancia_m", 1e-6), "tolerancia_m")
    if tolerance <= 0:
        raise MegalodonException(ErrorCode.BIM_ERROR, "tolerancia_m debe ser mayor que cero")
    result = {"tolerancia_m": tolerance}
    for field in ("cotas_elementos", "niveles_ifc"):
        enabled = parameters.get(field, False)
        if not isinstance(enabled, bool):
            raise MegalodonException(ErrorCode.BIM_ERROR, f"{field} debe ser booleano")
        if enabled:
            result[field] = True
    note = parameters.get("nota_lamina", "")
    if not isinstance(note, str) or len(note) > 120:
        raise MegalodonException(ErrorCode.BIM_ERROR, "La nota de lámina admite hasta 120 caracteres")
    if clean_note := " ".join(note.split()):
        result["nota_lamina"] = clean_note

    if kind == "PLAN":
        result["elevacion_m"] = _finite_number(parameters.get("elevacion_m"), "elevacion_m")
    elif kind == "SECTION":
        origin = parameters.get("origen_m")
        normal = parameters.get("normal")
        if not isinstance(origin, (list, tuple)) or not isinstance(normal, (list, tuple)):
            raise MegalodonException(ErrorCode.BIM_ERROR, "La sección requiere origen_m y normal")
        try:
            plane = Plane.from_origin_normal(origin, normal)
        except ValueError as exc:
            raise MegalodonException(ErrorCode.BIM_ERROR, str(exc)) from exc
        if abs(plane.normal[2]) > 1e-6:
            raise MegalodonException(ErrorCode.BIM_ERROR, "El plano de sección debe ser vertical")
        result["origen_m"] = list(plane.origin)
        result["normal"] = list(plane.normal)
    elif kind == "ELEVATION":
        direction = parameters.get("direccion_vista")
        origin = parameters.get("origen_m", (0.0, 0.0, 0.0))
        if not isinstance(direction, (list, tuple)) or not isinstance(origin, (list, tuple)):
            raise MegalodonException(ErrorCode.BIM_ERROR, "El alzado requiere direccion_vista y origen_m")
        try:
            plane = Plane.from_origin_normal(origin, direction)
        except ValueError as exc:
            raise MegalodonException(ErrorCode.BIM_ERROR, str(exc)) from exc
        hidden = parameters.get("mostrar_ocultas", False)
        if not isinstance(hidden, bool):
            raise MegalodonException(ErrorCode.BIM_ERROR, "mostrar_ocultas debe ser booleano")
        if hidden:
            result["mostrar_ocultas"] = True
        result["direccion_vista"] = list(plane.normal)
        result["origen_m"] = list(plane.origin)
    else:
        raise MegalodonException(ErrorCode.BIM_ERROR, "Tipo de dibujo no permitido")
    return result


def _geometry_fingerprint(elements: Iterable[ElementoBIM]) -> str:
    digest = hashlib.sha256()
    for element in elements:
        payload = {
            "global_id": element.global_id,
            "tipo": element.tipo,
            "vertices": element.malla_vertices,
            "caras": element.malla_caras,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


class BIMDrawingService:
    """Owns the request, source-revision checks, geometry pipeline and private output."""

    def __init__(self, db: AsyncSession, tenant_id: UUID | str):
        self.db = db
        self.tenant_id = UUID(str(tenant_id))

    async def _model(self, modelo_id: UUID, expediente_id: UUID, *, lock: bool = False) -> ModeloBIM:
        query = select(ModeloBIM).where(
            ModeloBIM.id == modelo_id,
            ModeloBIM.expediente_id == expediente_id,
            ModeloBIM.tenant_id == self.tenant_id,
        )
        if lock:
            query = query.with_for_update()
        model = await self.db.scalar(query.execution_options(populate_existing=True))
        if model is None:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                "Modelo BIM no encontrado en este expediente",
                status_code=404,
            )
        return model

    async def _elements(self, modelo_id: UUID) -> list[ElementoBIM]:
        result = await self.db.scalars(
            select(ElementoBIM)
            .where(ElementoBIM.modelo_id == modelo_id)
            .order_by(ElementoBIM.global_id, ElementoBIM.id)
        )
        return list(result.all())

    async def crear_dibujo(
        self,
        *,
        expediente_id: UUID,
        modelo_id: UUID,
        creado_por_id: Optional[UUID],
        tipo: str,
        titulo: str,
        parametros: dict,
        formatos: list[str],
        permitir_geometria_parcial: bool = False,
    ) -> DibujoBIM:
        model = await self._model(modelo_id, expediente_id)
        if model.estado_procesamiento != "COMPLETADO":
            raise MegalodonException(
                ErrorCode.BIM_ERROR,
                "El modelo IFC debe estar COMPLETADO antes de generar dibujos",
                status_code=409,
            )
        kind = str(tipo).upper()
        canonical = _canonical_parameters(kind, parametros)
        title = str(titulo).strip()
        if not title or len(title) > 300:
            raise MegalodonException(ErrorCode.BIM_ERROR, "El título del dibujo debe tener entre 1 y 300 caracteres")
        selected_formats = [str(value).upper() for value in formatos]
        if (
            not selected_formats
            or len(set(selected_formats)) != len(selected_formats)
            or not set(selected_formats).issubset(_ALLOWED_FORMATS)
        ):
            raise MegalodonException(ErrorCode.BIM_ERROR, "Formatos permitidos: SVG, DXF y PDF, sin duplicados")

        if "PDF" not in selected_formats and {"cotas_elementos", "niveles_ifc", "nota_lamina"} & canonical.keys():
            raise MegalodonException(ErrorCode.BIM_ERROR, "Las cotas, niveles y notas de lámina requieren formato PDF")

        source_updated_at = model.updated_at
        source_version = model.version_ifc
        elements = await self._elements(model.id)
        if not elements:
            raise MegalodonException(ErrorCode.BIM_ERROR, "El modelo IFC no contiene elementos cuantificados")
        if source_updated_at is None:
            raise MegalodonException(ErrorCode.BIM_ERROR, "El modelo IFC no tiene revisión temporal verificable")

        fingerprint = await asyncio.to_thread(_geometry_fingerprint, elements)
        # Lock only for the revision check and enqueue, after hashing the snapshot.
        model = await self._model(modelo_id, expediente_id, lock=True)
        if (
            model.estado_procesamiento != "COMPLETADO"
            or model.updated_at != source_updated_at
            or model.version_ifc != source_version
        ):
            raise MegalodonException(
                ErrorCode.CONFLICT, "El modelo cambió al preparar el plano. Actualiza y vuelve a solicitarlo.",
                status_code=409,
            )

        drawing = DibujoBIM(
            tenant_id=self.tenant_id,
            modelo_id=model.id,
            expediente_id=expediente_id,
            tipo=kind,
            titulo=title,
            parametros=canonical,
            formatos=selected_formats,
            permitir_geometria_parcial=bool(permitir_geometria_parcial),
            estado="PENDIENTE",
            source_model_updated_at=_as_utc(source_updated_at),
            source_model_version=source_version,
            source_num_elementos=len(elements),
            source_geometry_sha256=fingerprint,
            elementos_fuente=len(elements),
            creado_por_id=creado_por_id,
            actualizado_por_id=creado_por_id,
        )
        self.db.add(drawing)
        # Materialize the UUID before registering a job that stores this
        # aggregate ID. The flush remains inside the same transaction, so
        # the drawing and its durable job still commit or roll back together.
        await self.db.flush()
        from app.core.process_queue import registrar_trabajo

        registrar_trabajo(self.db, drawing, "BIM_DRAWING", {})
        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        await self.db.refresh(drawing)
        return drawing

    async def procesar_dibujo(self, drawing: DibujoBIM) -> None:
        # The fingerprint below binds the in-memory geometry to the requested
        # revision. Rendering and uploading it do not need a model write lock.
        model = await self._model(drawing.modelo_id, drawing.expediente_id)
        if model.estado_procesamiento != "COMPLETADO":
            raise MegalodonException(ErrorCode.BIM_ERROR, "El modelo IFC fuente ya no está COMPLETADO")
        if (
            _as_utc(model.updated_at) != _as_utc(drawing.source_model_updated_at)
            or model.version_ifc != drawing.source_model_version
        ):
            raise MegalodonException(
                ErrorCode.BIM_ERROR,
                "La revisión del modelo cambió después de solicitar el dibujo; vuelve a generarlo",
            )

        elements = await self._elements(model.id)
        if len(elements) != drawing.source_num_elementos:
            raise MegalodonException(
                ErrorCode.BIM_ERROR,
                "La cantidad de elementos del modelo cambió después de solicitar el dibujo",
            )
        if _geometry_fingerprint(elements) != drawing.source_geometry_sha256:
            raise MegalodonException(
                ErrorCode.BIM_ERROR,
                "La geometría IFC cambió después de solicitar el dibujo; vuelve a generarlo",
            )

        meshes: list[MeshElement] = []
        without_mesh: list[str] = []
        for element in elements:
            if not element.malla_vertices or not element.malla_caras:
                without_mesh.append(element.global_id)
                continue
            try:
                meshes.append(MeshElement.from_flat(
                    element_id=str(element.id),
                    global_id=element.global_id,
                    ifc_type=element.tipo,
                    vertices=element.malla_vertices,
                    faces=element.malla_caras,
                ))
            except ValueError as exc:
                raise MegalodonException(
                    ErrorCode.BIM_ERROR,
                    f"Geometría inválida en elemento IFC {element.global_id}: {exc}",
                ) from exc

        if without_mesh and not drawing.permitir_geometria_parcial:
            raise MegalodonException(
                ErrorCode.BIM_ERROR,
                f"Falta geometría para {len(without_mesh)} elementos IFC "
                f"({', '.join(without_mesh[:8])}). Reprocesa el modelo para recuperar los conjuntos "
                "y revisa los componentes que sigan pendientes.",
            )
        if not meshes:
            raise MegalodonException(ErrorCode.BIM_ERROR, "El modelo no contiene mallas geométricas para dibujar")

        parameters = drawing.parametros
        tolerance = float(parameters["tolerancia_m"])
        if drawing.tipo == "PLAN":
            document = build_plan_document(
                meshes,
                elevation_m=float(parameters["elevacion_m"]),
                title=drawing.titulo,
                tolerance_m=tolerance,
            )
        elif drawing.tipo == "SECTION":
            plane = Plane.from_origin_normal(parameters["origen_m"], parameters["normal"])
            document = build_section_document(
                meshes, plane, title=drawing.titulo, tolerance_m=tolerance,
            )
        else:
            document = build_elevation_document(
                meshes,
                view_direction=parameters["direccion_vista"],
                origin=parameters["origen_m"],
                title=drawing.titulo,
                tolerance_m=tolerance,
                include_hidden=parameters.get("mostrar_ocultas", False),
            )

        metadata = {
            **dict(document.metadata),
            "drawing_type": drawing.tipo,
            "source_model_id": str(model.id),
            "source_model_updated_at": _as_utc(model.updated_at).isoformat(),
            "source_model_version": model.version_ifc,
            "source_geometry_sha256": drawing.source_geometry_sha256,
            "source_element_count": len(elements),
            "elements_with_mesh": len(meshes),
            "elements_without_mesh": len(without_mesh),
            "partial_geometry_allowed": drawing.permitir_geometria_parcial,
            "omitted_global_ids_sample": without_mesh[:100],
            "omitted_global_ids_sample_truncated": len(without_mesh) > 100,
        }
        if drawing.tipo == "ELEVATION":
            metadata["drawing_limitations"] = [
                "Visibilidad calculada sobre contornos y pliegues candidatos de la malla triangulada",
                "Los tramos ocultos se dibujan discontinuos" if parameters.get("mostrar_ocultas")
                else "Los tramos ocultos se omiten",
                "No sustituye la revisión profesional de documentación constructiva",
            ]

        storage = storage_bim()
        pdf = None
        if "PDF" in drawing.formatos:
            expediente = await self.db.scalar(
                select(ExpedienteObra).where(
                    ExpedienteObra.id == drawing.expediente_id,
                    ExpedienteObra.tenant_id == self.tenant_id,
                )
            )
            if expediente is None:
                raise MegalodonException(
                    ErrorCode.DOCUMENTO_NO_ENCONTRADO, "Expediente no encontrado", status_code=404
                )
            levels = None
            if parameters.get("niveles_ifc"):
                source = await storage.descargar(model.ruta_archivo)
                with NamedTemporaryFile(suffix=".ifc") as tmp:
                    tmp.write(source)
                    tmp.flush()
                    motor = MotorBIM()
                    motor.cargar_ifc(tmp.name)
                    levels = motor.cotas_niveles()
                metadata["source_ifc_sha256"] = hashlib.sha256(source).hexdigest()
            note = parameters.get("nota_lamina", "")
            try:
                sheet = compose_a3_sheet(
                    document,
                    include_element_dims=parameters.get("cotas_elementos", False),
                    levels=levels,
                    meta=SheetMeta(
                        project_name=expediente.proyecto_nombre or expediente.titulo,
                        subtitle=model.nombre,
                        sheet_code=str(drawing.id),
                        organization=expediente.organo or "",
                        notes=tuple(wrap(note, width=44)),
                    ),
                )
                pdf = composed_to_pdf(sheet)
            except ValueError as exc:
                raise MegalodonException(
                    ErrorCode.BIM_ERROR, f"No se pudo componer la lámina A3: {exc}"
                ) from exc
            for key in ("cotas_elementos", "elementos_visibles", "niveles_ifc"):
                if key in sheet.metadata:
                    metadata[key] = sheet.metadata[key]
            if note:
                metadata["nota_lamina"] = note
            metadata.update(
                sheet_code=sheet.code, sheet_scale=sheet.scale, sheet_bounds_m=list(sheet.bounds_m)
            )

        prefix = (
            f"tenant/{self.tenant_id}/{drawing.expediente_id}/{drawing.modelo_id}"
            f"/drawings/{drawing.id}"
        )
        if "SVG" in drawing.formatos:
            svg = to_svg(document).encode("utf-8")
            path = f"{prefix}/drawing.svg"
            await storage.subir(path, svg, content_type="image/svg+xml", overwrite=True)
            drawing.ruta_svg = path
            drawing.sha256_svg = hashlib.sha256(svg).hexdigest()
        if "DXF" in drawing.formatos:
            dxf = to_dxf(document)
            path = f"{prefix}/drawing.dxf"
            await storage.subir(path, dxf, content_type="application/dxf", overwrite=True)
            drawing.ruta_dxf = path
            drawing.sha256_dxf = hashlib.sha256(dxf).hexdigest()

        if pdf is not None:
            path = f"{prefix}/drawing.pdf"
            await storage.subir(path, pdf, content_type="application/pdf", overwrite=True)
            drawing.ruta_pdf = path
            drawing.sha256_pdf = hashlib.sha256(pdf).hexdigest()

        drawing.elementos_con_malla = len(meshes)
        drawing.elementos_sin_malla = len(without_mesh)
        drawing.metadatos = metadata
        drawing.error = None
        await self.db.flush()
