# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
PresupuestoService - Gestión de presupuestos programables con costeo.
"""
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4
from decimal import Decimal, ROUND_HALF_UP
from copy import deepcopy
from datetime import datetime, timezone

from app.core.authorization import authorize_by_id

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.presupuesto import Presupuesto, Partida, Concepto, Insumo, ZonaEconomica, EstadoPresupuesto
from app.models.expediente import ExpedienteObra
from app.models.catalogo_apu import CatalogoAPU
from app.services.base import BaseService
from app.engines.costos.motor_costeo import MotorCosteo, PresupuestoCosteo, PartidaCosteo, ConceptoCosteo, InsumoCosteo
from app.engines.costos.parametros import ParametrosCosteoSnapshot, verificar_snapshot_almacenado
from app.core.errors import MegalodonException, ErrorCode


def partidas_pendientes(partidas) -> list[int]:
    return [p.numero for p in partidas if any(v is None or v <= 0
        for v in (p.cantidad, p.precio_unitario, p.importe))]


def presupuesto_completo(presupuesto) -> bool:
    return bool(cobertura_completa(presupuesto) and presupuesto.partidas and not partidas_pendientes(presupuesto.partidas)
                and presupuesto.monto_total and presupuesto.monto_total > 0)


def cobertura_completa(presupuesto) -> bool:
    from app.engines.topografia.evidencia import partidas_coinciden
    metadata = getattr(presupuesto, "metadatos", None) or {}
    return (not getattr(presupuesto, "fuentes_bim_obsoletas", False) and all(metadata.get(key, {}).get("completa", True) for key in ("bim_cobertura", "topografia_cobertura"))
            and partidas_coinciden(presupuesto))


def nombre_exportacion(presupuesto) -> str:
    metadata = presupuesto.metadatos or {}
    pendientes = []
    if not metadata.get("bim_cobertura", {}).get("completa", True):
        pendientes.append("mediciones BIM")
    if not metadata.get("topografia_cobertura", {}).get("completa", True):
        pendientes.append("cobertura topográfica")
    return presupuesto.nombre + (" [PARCIAL: falta " + " y ".join(pendientes) + "]" if pendientes else "")


class PresupuestoService(BaseService[Presupuesto]):
    """Servicio de presupuestos con motor de costeo integrado."""

    def __init__(self, db: AsyncSession, tenant_id: UUID | None = None):
        super().__init__(Presupuesto, db, tenant_id=tenant_id, tenant_required=True)
        self.motor_costeo = MotorCosteo()

    @staticmethod
    def _exigir_editable(presupuesto: Presupuesto) -> None:
        if presupuesto.estado in (EstadoPresupuesto.VALIDADO.value, EstadoPresupuesto.APROBADO.value):
            raise MegalodonException(ErrorCode.PRESUPUESTO_ERROR,
                'El presupuesto validado o aprobado es inmutable; cree una revisión para modificarlo',
                status_code=409)

    async def crear_revision(self, presupuesto_id: UUID, expediente_id: UUID,
                             motivo: str, creado_por_id: UUID) -> Presupuesto:
        """Copy the full aggregate and provenance; never reuse children or approval."""
        await authorize_by_id(self.db, creado_por_id, self.tenant_id)
        if not motivo or not motivo.strip():
            raise MegalodonException(ErrorCode.PRESUPUESTO_ERROR, 'Indique el motivo de la revisión', 422)
        original = await self._reconstruir_partidas_desde_db(presupuesto_id, expediente_id, bloquear=True)
        self._validar_origen_topografia(original)
        self._partidas_costeo_desde_orm(original)
        self._parametros_desde_orm(original)
        fields = ('nombre', 'descripcion', 'monto_directo', 'monto_indirecto', 'monto_financiamiento',
                  'monto_utilidad', 'monto_riesgo', 'monto_cargos_adicionales', 'monto_impuesto',
                  'monto_total', 'moneda', 'factor_indirecto', 'factor_financiamiento',
                  'factor_utilidad', 'factor_cargos_adicionales', 'factor_impuesto', 'factor_riesgo',
                  'zona_economica', 'plazo_dias')
        revision_id = uuid4()
        metadata = deepcopy(original.metadatos or {})
        if "bim_cobertura" in metadata:
            metadata["bim_cobertura"].pop("solicitud", None)
        metadata['revision'] = {
            'presupuesto_origen_id': str(original.id), 'estado_origen': original.estado,
            'motivo': motivo.strip(), 'creado_por_id': str(creado_por_id),
            'creado_en': datetime.now(timezone.utc).isoformat(),
        }
        revision = Presupuesto(id=revision_id, tenant_id=self.tenant_id, expediente_id=expediente_id,
            identificador=f'REV-{revision_id.hex}', estado=EstadoPresupuesto.BORRADOR.value,
            creado_por_id=creado_por_id, actualizado_por_id=creado_por_id,
            metadatos=metadata, partidas=[], **{key: getattr(original, key) for key in fields})
        indices = {}
        for partida in original.partidas:
            nueva = Partida(id=uuid4(), tenant_id=self.tenant_id, conceptos=[],
                **{key: deepcopy(getattr(partida, key)) for key in ('numero', 'descripcion', 'unidad',
                    'cantidad', 'precio_unitario', 'importe', 'metadatos', 'elemento_tipo', 'elemento_ifc_id')})
            for concepto in partida.conceptos:
                nuevo = Concepto(id=uuid4(), tenant_id=self.tenant_id, insumos=[],
                    **{key: getattr(concepto, key) for key in ('clave', 'descripcion', 'unidad',
                        'cantidad', 'costo_directo_unitario')})
                for insumo in concepto.insumos:
                    copia = Insumo(id=uuid4(), tenant_id=self.tenant_id,
                        **{key: deepcopy(getattr(insumo, key)) for key in ('clave', 'descripcion', 'tipo',
                            'unidad', 'cantidad', 'precio_unitario', 'importe', 'fuente_catalogo',
                            'actualizacion_precio', 'rendimiento')})
                    if copia.actualizacion_precio:
                        indices[str(copia.id)] = copia.actualizacion_precio['sha256']
                    nuevo.insumos.append(copia)
                nueva.conceptos.append(nuevo)
            revision.partidas.append(nueva)
        if indices or 'actualizaciones_indices' in metadata:
            metadata['actualizaciones_indices'] = indices
        try:
            self.db.add(revision)
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return await self._reconstruir_partidas_desde_db(revision_id, expediente_id)

    async def _registrar_corrida(self) -> None:
        from app.models.user import Tenant
        from app.services.entitlements_service import EntitlementsService
        tenant = (await self.db.execute(select(Tenant).where(
            Tenant.id == self.tenant_id).with_for_update())).scalar_one()
        await EntitlementsService(self.db).verificar_y_registrar_uso(
            tenant, "corridas_costeo", auto_commit=False)

    async def listar_por_expediente(
        self, expediente_id: UUID, skip: int = 0, limit: int = 20,
    ) -> List[Presupuesto]:
        """Lista presupuestos de un expediente con partidas/conceptos/
        insumos precargados (BaseService.get_multi() no lo hace, y
        PresupuestoOut ahora expone `partidas`)."""
        from sqlalchemy.orm import selectinload

        result = await self.db.execute(
            select(Presupuesto)
            .join(ExpedienteObra, ExpedienteObra.id == Presupuesto.expediente_id)
            .where(Presupuesto.expediente_id == expediente_id, ExpedienteObra.tenant_id == self.tenant_id)
            .options(
                selectinload(Presupuesto.partidas)
                .selectinload(Partida.conceptos)
                .selectinload(Concepto.insumos)
            )
            .order_by(Presupuesto.created_at.desc())
            .offset(skip)
            .limit(limit)
            # Keep totals and selectinloaded details in the same aggregate revision.
            .with_for_update(of=Presupuesto, read=True)
            .execution_options(populate_existing=True)
        )
        items = list(result.scalars().all())
        from app.services.bim_operational import BIMOperationalService
        ops = BIMOperationalService(self.db, self.tenant_id)
        for item in items:
            item.fuentes_bim_obsoletas = await ops.presupuesto_obsoleto(item)
        return items

    async def crear_desde_costeo(
        self,
        *,
        expediente_id: UUID,
        nombre: str,
        descripcion: Optional[str] = None,
        partidas_data: List[Dict[str, Any]],
        parametros_costeo: ParametrosCosteoSnapshot,
        zona_economica: str = "CENTRO",
        creado_por_id: Optional[UUID] = None,
        evidencia_bim: Optional[dict] = None,
        auto_commit: bool = True,
    ) -> Presupuesto:
        """Crea presupuesto desde datos de costeo con cálculo completo.

        Dos formas válidas de mandar una partida en `partidas_data`:

        1) Tabulador / precio ya conocido (ej. tabulador CDMX importado):
           solo manda `precio_unitario` y NO manda `conceptos`. Ese precio
           se respeta tal cual, sin recalcular desde insumos.

        2) APU real (uno o más conceptos): manda `conceptos`, y cada
           concepto trae SUS PROPIOS `insumos` anidados (no se comparten
           entre conceptos). El precio_unitario de la partida se calcula
           sumando el costo de todos los conceptos.
        """

        self._effective_tenant(None)
        # Validar expediente existe
        result = await self.db.execute(
            select(ExpedienteObra).where(ExpedienteObra.id == expediente_id, ExpedienteObra.tenant_id == self.tenant_id)
        )
        expediente = result.scalar_one_or_none()
        if not expediente:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Expediente {expediente_id} no encontrado",
            )

        # Resolve catalogue prices on the server; client amounts are not evidence.
        from app.services.catalogo_libro import resolver
        referencias = {}
        referencias_catalogos = {}
        partidas_data = deepcopy(partidas_data)
        for index, data in enumerate(partidas_data, 1):
            if data.get('catalogo_apu_id'):
                from app.services.catalogo_costeo import resolve_catalogue
                if data.get('catalogo_libro_id') or data.get('conceptos') or data.get('insumos'):
                    raise MegalodonException(ErrorCode.BAD_REQUEST, 'Seleccione un solo origen de catálogo/APU por partida')
                catalogo, concept, price, snapshot = await resolve_catalogue(self.db, self.tenant_id,
                    data['catalogo_apu_id'], creado_por_id)
                data.update(descripcion=catalogo.descripcion, unidad=catalogo.unidad, precio_unitario=price,
                    conceptos=[{'clave': concept.clave, 'descripcion': concept.descripcion, 'unidad': concept.unidad,
                        'cantidad': 1, 'insumos': deepcopy(snapshot['desglose'])}] if concept else [])
                referencias_catalogos[index] = snapshot
            if data.get("catalogo_libro_id"):
                item = resolver(data["catalogo_libro_id"])
                if data.get("conceptos") or data.get("insumos"):
                    raise MegalodonException(ErrorCode.BAD_REQUEST, "No mezclar catálogo con APU")
                data.update(descripcion=item["descripcion"], unidad=item["unidad"],
                            precio_unitario=Decimal(item["precio_unitario"]))
                referencias[str(index)] = item

        # Resolve every requested update before any budget row is inserted.
        # Prices, identity and units come from the reviewed source snapshot.
        from app.models.user import User
        from app.schemas.indices_costos import ActualizacionPrecioInput
        from app.schemas.apu_costeo import InsumoCosteoInput
        from app.services.indices_costos_service import IndicesCostosService
        from pydantic import ValidationError
        actor = None
        for partida_data in partidas_data:
            for concepto_data in [partida_data, *(partida_data.get('conceptos') or [])]:
                for insumo_data in concepto_data.get('insumos') or []:
                    if '_snapshot_indice' in insumo_data:
                        raise MegalodonException(ErrorCode.BAD_REQUEST, 'No se admite evidencia calculada por el cliente')
                    try:
                        validado = InsumoCosteoInput.model_validate(insumo_data)
                    except ValidationError as exc:
                        raise MegalodonException(ErrorCode.BAD_REQUEST, 'Cantidades o precios del insumo inválidos') from exc
                    insumo_data.clear()
                    insumo_data.update(validado.model_dump(mode='python'))
                    if insumo_data.get('actualizacion_precio') is None:
                        continue
                    if actor is None:
                        actor = await self.db.get(User, creado_por_id) if creado_por_id else None
                        if actor is None or actor.tenant_id != self.tenant_id or not actor.is_active:
                            raise MegalodonException(ErrorCode.PERMISO_DENEGADO, 'La actualización requiere un usuario del tenant', status_code=403)
                    try:
                        solicitud = ActualizacionPrecioInput.model_validate(insumo_data['actualizacion_precio'])
                    except ValidationError as exc:
                        raise MegalodonException(ErrorCode.BAD_REQUEST, 'Referencia de actualización inválida') from exc
                    snapshot = await IndicesCostosService(self.db, actor).resolver(solicitud)
                    original = snapshot['vinculo']['insumo_original']
                    insumo_data.update(clave=original['clave'], descripcion=original['descripcion'],
                                       tipo=original['tipo'], unidad=original['unidad'],
                                       precio_unitario=Decimal(snapshot['precio_actualizado']), _snapshot_indice=snapshot)
            if partida_data.get('conceptos') and partida_data.get('insumos'):
                raise MegalodonException(ErrorCode.BAD_REQUEST, 'No mezclar insumos de partida y de conceptos')

        # Independent of concurrent creations and deletions; fits String(100).
        presupuesto_id = uuid4()
        identificador = f"PRE-{expediente.identificador[:62]}-{presupuesto_id.hex}"

        # Construir modelo de costeo
        partidas_costeo = []
        for i, p_data in enumerate(partidas_data, 1):
            conceptos_data = p_data.get("conceptos") or []
            conceptos: List[ConceptoCosteo] = []

            if conceptos_data:
                # Caso APU: cada concepto trae SUS PROPIOS insumos.
                # BUG ORIGINAL: todos los conceptos de la partida compartían
                # la misma lista de insumos del nivel partida, y encima
                # solo el primer concepto se quedaba con ellos (los demás
                # recibían insumos=[] y quedaban en costo cero).
                for c_data in conceptos_data:
                    insumos_concepto = [
                        InsumoCosteo(
                            clave=ins_data.get("clave", ""),
                            descripcion=ins_data.get("descripcion", ""),
                            tipo=ins_data.get("tipo", "MATERIAL"),
                            unidad=ins_data.get("unidad", ""),
                            cantidad=Decimal(str(ins_data.get("cantidad", 0))),
                            precio_unitario=Decimal(str(ins_data.get("precio_unitario", 0))),
                            rendimiento=Decimal(str(ins_data.get("rendimiento", 1.0))),
                            actualizacion_precio=ins_data.get('_snapshot_indice'),
                        )
                        for ins_data in c_data.get("insumos", [])
                    ]
                    conceptos.append(ConceptoCosteo(
                        clave=c_data.get("clave", ""),
                        descripcion=c_data.get("descripcion", ""),
                        unidad=c_data.get("unidad", ""),
                        cantidad=Decimal(str(c_data.get("cantidad", 1.0))),
                        insumos=insumos_concepto,
                    ))
            else:
                # Sin conceptos explícitos: si vienen insumos sueltos a
                # nivel partida, se agrupan en un concepto implícito.
                insumos_partida = [
                    InsumoCosteo(
                        clave=ins_data.get("clave", ""),
                        descripcion=ins_data.get("descripcion", ""),
                        tipo=ins_data.get("tipo", "MATERIAL"),
                        unidad=ins_data.get("unidad", ""),
                        cantidad=Decimal(str(ins_data.get("cantidad", 0))),
                        precio_unitario=Decimal(str(ins_data.get("precio_unitario", 0))),
                        rendimiento=Decimal(str(ins_data.get("rendimiento", 1.0))),
                        actualizacion_precio=ins_data.get('_snapshot_indice'),
                    )
                    for ins_data in p_data.get("insumos", [])
                ]
                if insumos_partida:
                    conceptos.append(ConceptoCosteo(
                        clave=f"CON-{i:03d}",
                        descripcion=p_data.get("descripcion", ""),
                        unidad=p_data.get("unidad", ""),
                        insumos=insumos_partida,
                    ))

            # Precio manual (tabulador): solo aplica si NO hay conceptos,
            # es decir, el precio ya viene resuelto de un catálogo oficial
            # y no debe recalcularse desde una APU que no existe.
            precio_manual = None
            if not conceptos and p_data.get("precio_unitario") is not None:
                precio_manual = Decimal(str(p_data["precio_unitario"]))

            partidas_costeo.append(PartidaCosteo(
                numero=i,
                descripcion=p_data.get("descripcion", ""),
                unidad=p_data.get("unidad", ""),
                cantidad=Decimal(str(p_data.get("cantidad", 0))),
                conceptos=conceptos,
                precio_unitario_manual=precio_manual,
            ))

        presupuesto_costeo = PresupuestoCosteo(
            identificador=identificador,
            nombre=nombre,
            partidas=partidas_costeo,
            parametros=parametros_costeo,
        )

        # Calcular
        presupuesto_costeo = self.motor_costeo.calcular_presupuesto(presupuesto_costeo)

        await self._registrar_corrida()

        # Crear en DB
        presupuesto = Presupuesto(**{
            "id": presupuesto_id,
            "identificador": identificador,
            "nombre": nombre,
            "descripcion": descripcion,
            "expediente_id": expediente_id,
            "monto_directo": presupuesto_costeo.monto_directo,
            "monto_indirecto": presupuesto_costeo.monto_indirecto,
            "monto_financiamiento": presupuesto_costeo.monto_financiamiento,
            "monto_utilidad": presupuesto_costeo.monto_utilidad,
            "monto_riesgo": presupuesto_costeo.monto_riesgo,
            "monto_cargos_adicionales": presupuesto_costeo.monto_cargos_adicionales,
            "monto_impuesto": presupuesto_costeo.monto_impuesto,
            "monto_total": presupuesto_costeo.monto_total,
            "factor_indirecto": parametros_costeo.factor_indirecto,
            "factor_financiamiento": parametros_costeo.factor_financiamiento,
            "factor_utilidad": parametros_costeo.factor_utilidad,
            "factor_cargos_adicionales": parametros_costeo.factor_cargos_adicionales,
            "factor_impuesto": parametros_costeo.factor_impuesto,
            "factor_riesgo": parametros_costeo.factor_riesgo,
            "zona_economica": zona_economica,
            "metadatos": {"parametros_costeo": parametros_costeo.to_dict(), "catalogo_libro": referencias,
                          **({"bim_cobertura": evidencia_bim} if evidencia_bim is not None else {})},
            "estado": (EstadoPresupuesto.CALCULADO.value if presupuesto_completo(presupuesto_costeo) and
                (evidencia_bim is None or evidencia_bim["completa"])
                else EstadoPresupuesto.BORRADOR.value),
            "tenant_id": self.tenant_id,
            "creado_por_id": creado_por_id,
            "actualizado_por_id": creado_por_id,
        })
        self.db.add(presupuesto)
        await self.db.flush()

        # Crear partidas, conceptos e insumos
        referencias_indices = {}
        for p_costeo in presupuesto_costeo.partidas:
            partida = Partida(
                id=uuid4(),
                tenant_id=presupuesto.tenant_id,
                presupuesto_id=presupuesto.id,
                numero=p_costeo.numero,
                descripcion=p_costeo.descripcion,
                unidad=p_costeo.unidad,
                cantidad=p_costeo.cantidad,
                precio_unitario=p_costeo.precio_unitario,
                importe=p_costeo.importe,
                metadatos={'catalogo_asignado': referencias_catalogos[p_costeo.numero]} if p_costeo.numero in referencias_catalogos else {},
            )
            self.db.add(partida)

            for c_costeo in p_costeo.conceptos:
                concepto = Concepto(
                    id=uuid4(),
                    tenant_id=presupuesto.tenant_id,
                    partida_id=partida.id,
                    clave=c_costeo.clave,
                    descripcion=c_costeo.descripcion,
                    unidad=c_costeo.unidad,
                    cantidad=c_costeo.cantidad,
                    costo_directo_unitario=c_costeo.costo_directo_unitario,
                )
                self.db.add(concepto)

                for i_costeo in c_costeo.insumos:
                    insumo = Insumo(
                        id=uuid4(),
                        tenant_id=presupuesto.tenant_id,
                        concepto_id=concepto.id,
                        clave=i_costeo.clave,
                        descripcion=i_costeo.descripcion,
                        tipo=i_costeo.tipo,
                        unidad=i_costeo.unidad,
                        cantidad=i_costeo.cantidad,
                        precio_unitario=i_costeo.precio_unitario,
                        importe=i_costeo.importe,
                        rendimiento=i_costeo.rendimiento,
                        actualizacion_precio=i_costeo.actualizacion_precio,
                    )
                    if i_costeo.actualizacion_precio:
                        referencias_indices[str(insumo.id)] = i_costeo.actualizacion_precio['sha256']
                    self.db.add(insumo)

        if referencias_indices:
            presupuesto.metadatos = {**presupuesto.metadatos, 'actualizaciones_indices': referencias_indices}
        if auto_commit:
            await self.db.commit()
        else:
            await self.db.flush()

        # BUG EVITADO: db.refresh(presupuesto) solo recarga columnas
        # escalares, no relaciones -- si el caller (o el response_model)
        # intentara leer presupuesto.partidas después de esto, sería un
        # lazy-load implícito que en AsyncSession truena con
        # MissingGreenlet. Se re-consulta ya con todo precargado.
        return await self._reconstruir_partidas_desde_db(presupuesto.id, expediente_id)

    async def _reconstruir_partidas_desde_db(self, presupuesto_id: UUID, expediente_id: UUID, *, bloquear: bool = False) -> "Presupuesto":
        """Recarga un presupuesto con partidas → conceptos → insumos completos.
        Valida que el presupuesto pertenezca al expediente de la ruta.

        BUG ORIGINAL: recalcular() y generar_excel() reconstruían las
        partidas con conceptos=[] (sin recargar nada de la BD). Como
        PartidaCosteo.precio_unitario ahora depende de sus conceptos, eso
        significaba que CADA recálculo o exportación a Excel ponía el
        presupuesto entero en $0.00, pisando los montos reales guardados.
        """
        from sqlalchemy.orm import selectinload

        statement = (
            select(Presupuesto)
            .where(Presupuesto.id == presupuesto_id)
            .where(Presupuesto.expediente_id == expediente_id)
            .where(Presupuesto.tenant_id == self.tenant_id)
            .options(
                selectinload(Presupuesto.partidas)
                .selectinload(Partida.conceptos)
                .selectinload(Concepto.insumos)
            )
        )
        # Shared locks give selectinload a coherent aggregate under READ COMMITTED;
        # all writers acquire an exclusive parent lock before loading children.
        statement = statement.with_for_update(of=Presupuesto, read=not bloquear).execution_options(populate_existing=True)
        result = await self.db.execute(statement)
        presupuesto = result.scalar_one_or_none()
        if not presupuesto:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Presupuesto {presupuesto_id} no encontrado en el expediente {expediente_id}",
            )
        from app.services.bim_operational import BIMOperationalService
        presupuesto.fuentes_bim_obsoletas = await BIMOperationalService(self.db, self.tenant_id).presupuesto_obsoleto(presupuesto, lock=bloquear)
        return presupuesto

    def _partidas_costeo_desde_orm(self, presupuesto: "Presupuesto") -> List[PartidaCosteo]:
        """Convierte las partidas ORM (con conceptos e insumos ya cargados)
        a PartidaCosteo, preservando el precio manual de partidas tipo
        tabulador (las que no tienen conceptos)."""
        from app.engines.costos.indices import verificar_snapshot
        self._verificar_catalogos_asignados(presupuesto)
        referencias = (presupuesto.metadatos or {}).get('actualizaciones_indices', {})
        encontradas = {}
        try:
            for p in presupuesto.partidas:
                for c in p.conceptos:
                    for ins in c.insumos:
                        if ins.actualizacion_precio:
                            verificar_snapshot(ins.actualizacion_precio, Decimal(ins.precio_unitario))
                            original = ins.actualizacion_precio['vinculo']['insumo_original']
                            if any(getattr(ins, key) != original[key] for key in ('clave', 'descripcion', 'tipo', 'unidad')):
                                raise ValueError('La identidad o unidad del material difiere de su evidencia')
                            if ins.actualizacion_precio['vinculo']['tenant_id'] != str(self.tenant_id):
                                raise ValueError('Correspondencia de otro tenant')
                            encontradas[str(ins.id)] = ins.actualizacion_precio['sha256']
            if referencias != encontradas:
                raise ValueError('Referencias de actualización incompletas o alteradas')
        except (KeyError, TypeError, ValueError) as exc:
            raise MegalodonException(ErrorCode.PRESUPUESTO_ERROR, f'Evidencia de índices inválida: {exc}') from exc
        partidas_costeo = []
        for p in presupuesto.partidas:
            conceptos = [
                ConceptoCosteo(
                    clave=c.clave,
                    descripcion=c.descripcion,
                    unidad=c.unidad,
                    cantidad=Decimal(str(c.cantidad)),
                    insumos=[
                        InsumoCosteo(
                            clave=ins.clave,
                            descripcion=ins.descripcion,
                            tipo=ins.tipo,
                            unidad=ins.unidad,
                            cantidad=Decimal(str(ins.cantidad)),
                            precio_unitario=Decimal(str(ins.precio_unitario)),
                            rendimiento=Decimal(str(ins.rendimiento)),
                            actualizacion_precio=ins.actualizacion_precio,
                        )
                        for ins in c.insumos
                    ],
                )
                for c in p.conceptos
            ]
            # Partida tipo tabulador (sin conceptos): preserva el precio
            # unitario ya guardado en vez de recalcularlo desde cero.
            precio_manual = Decimal(str(p.precio_unitario)) if not conceptos else None
            partidas_costeo.append(PartidaCosteo(
                numero=p.numero,
                descripcion=p.descripcion,
                unidad=p.unidad,
                cantidad=Decimal(str(p.cantidad)),
                conceptos=conceptos,
                precio_unitario_manual=precio_manual,
                origen_catalogo=deepcopy((p.metadatos or {}).get('catalogo_asignado')),
            ))
        return partidas_costeo

    @staticmethod
    def _parametros_desde_orm(presupuesto: "Presupuesto") -> ParametrosCosteoSnapshot:
        snapshot = (presupuesto.metadatos or {}).get("parametros_costeo")
        try:
            return verificar_snapshot_almacenado(
                snapshot,
                (
                    presupuesto.factor_indirecto,
                    presupuesto.factor_financiamiento,
                    presupuesto.factor_utilidad,
                    presupuesto.factor_cargos_adicionales,
                    presupuesto.factor_impuesto,
                    presupuesto.factor_riesgo,
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise MegalodonException(
                ErrorCode.PRESUPUESTO_ERROR,
                f"Snapshot de parámetros de costeo inválido: {exc}",
                details={"presupuesto_id": str(presupuesto.id)},
            ) from exc

    async def actualizar_parametros_costeo(
        self,
        presupuesto_id: UUID,
        expediente_id: UUID,
        parametros: ParametrosCosteoSnapshot,
        actualizado_por_id: Optional[UUID] = None,
    ) -> Presupuesto:
        presupuesto = await self._reconstruir_partidas_desde_db(presupuesto_id, expediente_id, bloquear=True)
        self._exigir_editable(presupuesto)
        metadatos = dict(presupuesto.metadatos or {})
        metadatos["parametros_costeo"] = parametros.to_dict()
        presupuesto_costeo = PresupuestoCosteo(
            identificador=presupuesto.identificador,
            nombre=presupuesto.nombre,
            partidas=self._partidas_costeo_desde_orm(presupuesto),
            parametros=parametros,
        )
        self.motor_costeo.calcular_presupuesto(presupuesto_costeo)

        await self._registrar_corrida()

        for p_orm, p_costeo in zip(presupuesto.partidas, presupuesto_costeo.partidas):
            p_orm.precio_unitario = p_costeo.precio_unitario
            p_orm.importe = p_costeo.importe
            for c_orm, c_costeo in zip(p_orm.conceptos, p_costeo.conceptos):
                c_orm.costo_directo_unitario = c_costeo.costo_directo_unitario
                for i_orm, i_costeo in zip(c_orm.insumos, c_costeo.insumos):
                    i_orm.importe = i_costeo.importe
        presupuesto.factor_indirecto = parametros.factor_indirecto
        presupuesto.factor_financiamiento = parametros.factor_financiamiento
        presupuesto.factor_utilidad = parametros.factor_utilidad
        presupuesto.factor_cargos_adicionales = parametros.factor_cargos_adicionales
        presupuesto.factor_impuesto = parametros.factor_impuesto
        presupuesto.factor_riesgo = parametros.factor_riesgo
        presupuesto.monto_directo = presupuesto_costeo.monto_directo
        presupuesto.monto_indirecto = presupuesto_costeo.monto_indirecto
        presupuesto.monto_financiamiento = presupuesto_costeo.monto_financiamiento
        presupuesto.monto_utilidad = presupuesto_costeo.monto_utilidad
        presupuesto.monto_riesgo = presupuesto_costeo.monto_riesgo
        presupuesto.monto_cargos_adicionales = presupuesto_costeo.monto_cargos_adicionales
        presupuesto.monto_impuesto = presupuesto_costeo.monto_impuesto
        presupuesto.monto_total = presupuesto_costeo.monto_total
        presupuesto.metadatos = metadatos
        if actualizado_por_id is not None:
            presupuesto.actualizado_por_id = actualizado_por_id
        await self.db.commit()
        return await self._reconstruir_partidas_desde_db(presupuesto_id, expediente_id)

    async def recalcular(
        self, presupuesto_id: UUID, expediente_id: UUID, actualizado_por_id: Optional[UUID] = None,
    ) -> Presupuesto:
        """Recalcula un presupuesto existente a partir de sus partidas,
        conceptos e insumos reales guardados en BD."""
        presupuesto = await self._reconstruir_partidas_desde_db(presupuesto_id, expediente_id, bloquear=True)
        self._exigir_editable(presupuesto)
        partidas_costeo = self._partidas_costeo_desde_orm(presupuesto)

        presupuesto_costeo = PresupuestoCosteo(
            identificador=presupuesto.identificador,
            nombre=nombre_exportacion(presupuesto),
            partidas=partidas_costeo,
            parametros=self._parametros_desde_orm(presupuesto),
        )

        presupuesto_costeo = self.motor_costeo.calcular_presupuesto(presupuesto_costeo)

        await self._registrar_corrida()

        # Actualizar también el importe/precio_unitario de cada partida,
        # por si cambiaron insumos desde la última vez.
        for p_orm, p_costeo in zip(presupuesto.partidas, presupuesto_costeo.partidas):
            p_orm.precio_unitario = p_costeo.precio_unitario
            p_orm.importe = p_costeo.importe
            for c_orm, c_costeo in zip(p_orm.conceptos, p_costeo.conceptos):
                c_orm.costo_directo_unitario = c_costeo.costo_directo_unitario
                for i_orm, i_costeo in zip(c_orm.insumos, c_costeo.insumos):
                    i_orm.importe = i_costeo.importe

        nuevo_estado = (EstadoPresupuesto.CALCULADO.value if presupuesto_completo(presupuesto_costeo)
            and cobertura_completa(presupuesto)
            else EstadoPresupuesto.BORRADOR.value)

        await self.update(
            presupuesto_id,
            {
                "monto_directo": presupuesto_costeo.monto_directo,
                "monto_indirecto": presupuesto_costeo.monto_indirecto,
                "monto_financiamiento": presupuesto_costeo.monto_financiamiento,
                "monto_utilidad": presupuesto_costeo.monto_utilidad,
                "monto_riesgo": presupuesto_costeo.monto_riesgo,
                "monto_cargos_adicionales": presupuesto_costeo.monto_cargos_adicionales,
                "monto_impuesto": presupuesto_costeo.monto_impuesto,
                "monto_total": presupuesto_costeo.monto_total,
                "estado": nuevo_estado,
            },
            actualizado_por_id=actualizado_por_id,
        )

        # self.update() termina en un get() plano (sin selectinload); se
        # re-consulta con las relaciones precargadas por la misma razón
        # que en crear_desde_costeo (evitar un lazy-load async al serializar).
        return await self._reconstruir_partidas_desde_db(presupuesto_id, expediente_id)

    async def generar_excel(self, presupuesto_id: UUID, expediente_id: UUID) -> bytes:
        """Genera Excel del presupuesto a partir de los datos reales en BD."""
        presupuesto = await self._reconstruir_partidas_desde_db(presupuesto_id, expediente_id)
        self._validar_origen_topografia(presupuesto)
        partidas_costeo = self._partidas_costeo_desde_orm(presupuesto)

        presupuesto_costeo = PresupuestoCosteo(
            identificador=presupuesto.identificador,
            nombre=nombre_exportacion(presupuesto),
            partidas=partidas_costeo,
            parametros=self._parametros_desde_orm(presupuesto),
            cobertura_bim=(presupuesto.metadatos or {}).get("bim_cobertura"),
            evidencia_topografia=(presupuesto.metadatos or {}).get("topografia_evidencia"),
        )
        presupuesto_costeo = self.motor_costeo.calcular_presupuesto(presupuesto_costeo)

        return self.motor_costeo.generar_excel(presupuesto_costeo)

    _TRANSICIONES_ESTADO = {
        EstadoPresupuesto.BORRADOR.value: {EstadoPresupuesto.CALCULADO.value},
        EstadoPresupuesto.CALCULADO.value: {EstadoPresupuesto.VALIDADO.value, EstadoPresupuesto.RECHAZADO.value},
        EstadoPresupuesto.VALIDADO.value: {EstadoPresupuesto.APROBADO.value, EstadoPresupuesto.RECHAZADO.value},
        EstadoPresupuesto.RECHAZADO.value: {EstadoPresupuesto.CALCULADO.value},
        EstadoPresupuesto.APROBADO.value: set(),  # terminal; las modificaciones requieren una revisión independiente
    }

    async def cambiar_estado(
        self, presupuesto_id: UUID, expediente_id: UUID, nuevo_estado: str,
        actualizado_por_id: Optional[UUID] = None,
    ) -> Presupuesto:
        """Transiciona el estado del presupuesto (VALIDADO/APROBADO/
        RECHAZADO) validando que la transición sea válida -- no existía
        ningún mecanismo para esto porque el campo `estado` tampoco
        existía antes de esta ronda de unificación."""
        presupuesto = await self._reconstruir_partidas_desde_db(presupuesto_id, expediente_id, bloquear=True)
        self._verificar_catalogos_asignados(presupuesto)
        if nuevo_estado not in {e.value for e in EstadoPresupuesto}:
            raise MegalodonException(
                ErrorCode.PRESUPUESTO_ERROR,
                f"Estado inválido: {nuevo_estado}. Válidos: {[e.value for e in EstadoPresupuesto]}",
            )
        if nuevo_estado in (EstadoPresupuesto.CALCULADO.value, EstadoPresupuesto.VALIDADO.value,
                            EstadoPresupuesto.APROBADO.value):
            pendientes = partidas_pendientes(presupuesto.partidas)
            cobertura_bim = (presupuesto.metadatos or {}).get("bim_cobertura")
            if cobertura_bim and not cobertura_bim.get("area_requiere_revision") and any(
                (partida.unidad or "").strip().lower() == "m2" for partida in presupuesto.partidas
            ):
                raise MegalodonException(
                    ErrorCode.PRESUPUESTO_ERROR,
                    "Genere una revisión desde BIM con superficies verificadas antes de aprobar",
                    status_code=409,
                )
            if not presupuesto_completo(presupuesto):
                raise MegalodonException(ErrorCode.PRESUPUESTO_ERROR,
                    "Presupuesto incompleto: complete cantidades, precios y cobertura antes de validar o aprobar",
                    details={"partidas_pendientes": pendientes,
                             "topografia_cobertura": (presupuesto.metadatos or {}).get("topografia_cobertura")})
        permitidas = self._TRANSICIONES_ESTADO.get(presupuesto.estado, set())
        if nuevo_estado not in permitidas:
            raise MegalodonException(
                ErrorCode.PRESUPUESTO_ERROR,
                f"Transición de estado inválida: {presupuesto.estado} -> {nuevo_estado}",
                details={"transiciones_permitidas": sorted(permitidas)},
            )
        await self.update(
            presupuesto_id, {"estado": nuevo_estado}, actualizado_por_id=actualizado_por_id,
        )
        return await self._reconstruir_partidas_desde_db(presupuesto_id, expediente_id)

    async def generar_pdf(self, presupuesto_id: UUID, expediente_id: UUID) -> bytes:
        """Genera PDF del presupuesto a partir de los datos reales en BD.
        Mismo patrón que generar_excel()."""
        presupuesto = await self._reconstruir_partidas_desde_db(presupuesto_id, expediente_id)
        self._validar_origen_topografia(presupuesto)
        partidas_costeo = self._partidas_costeo_desde_orm(presupuesto)

        presupuesto_costeo = PresupuestoCosteo(
            identificador=presupuesto.identificador,
            nombre=nombre_exportacion(presupuesto),
            partidas=partidas_costeo,
            parametros=self._parametros_desde_orm(presupuesto),
            cobertura_bim=(presupuesto.metadatos or {}).get("bim_cobertura"),
            evidencia_topografia=(presupuesto.metadatos or {}).get("topografia_evidencia"),
        )
        presupuesto_costeo = self.motor_costeo.calcular_presupuesto(presupuesto_costeo)

        return self.motor_costeo.generar_pdf(presupuesto_costeo)

    @staticmethod
    def _validar_origen_topografia(presupuesto):
        if getattr(presupuesto, "fuentes_bim_obsoletas", False):
            raise MegalodonException(ErrorCode.PRESUPUESTO_ERROR,
                'Cambió la revisión BIM o el sustento económico; genera una nueva versión del presupuesto', status_code=409)
        from app.engines.topografia.evidencia import partidas_coinciden
        if not partidas_coinciden(presupuesto):
            raise MegalodonException(ErrorCode.PRESUPUESTO_ERROR,
                "Las cantidades no corresponden a su evidencia topográfica; genere una nueva versión desde el terreno")

    @staticmethod
    def _verificar_catalogos_asignados(presupuesto):
        from app.engines.topografia.evidencia import huella
        from decimal import InvalidOperation
        try:
            for partida in presupuesto.partidas:
                metadata = partida.metadatos or {}
                snapshot = metadata.get('catalogo_asignado')
                if snapshot is None:
                    if metadata.get('topografia') and partida.precio_unitario > 0:
                        raise ValueError('Falta el origen del precio medido')
                    continue
                payload = dict(snapshot)
                digest = payload.pop('sha256')
                if digest != huella(payload) or Decimal(snapshot['precio_aplicado']) != partida.precio_unitario:
                    raise ValueError('Precio o huella distintos de la revisión asignada')
                if snapshot['desglose']:
                    if len(partida.conceptos) != 1:
                        raise ValueError('Cambió el APU asignado')
                    concepto = partida.conceptos[0]
                    if (concepto.clave != snapshot['clave'] or concepto.descripcion != snapshot['descripcion']
                            or concepto.unidad != partida.unidad or concepto.cantidad != 1
                            or concepto.costo_directo_unitario != Decimal(snapshot['precio_aplicado'])):
                        raise ValueError('Cambió la identidad del APU asignado')
                    campos = ('clave', 'descripcion', 'tipo', 'unidad', 'cantidad', 'precio_unitario', 'rendimiento')
                    def values(item):
                        return tuple(Decimal(str(item[key])) if key in campos[4:] else item[key] for key in campos)
                    expected = sorted(values(item) for item in snapshot['desglose'])
                    actual = sorted(values({key: getattr(item,key) for key in campos}) for item in concepto.insumos)
                    if expected != actual or any(i.actualizacion_precio is not None for i in concepto.insumos):
                        raise ValueError('Cambió el desglose del precio asignado')
                elif partida.conceptos:
                    raise ValueError('Un precio observado fue sustituido por otro APU')
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise MegalodonException(ErrorCode.PRESUPUESTO_ERROR,
                'El precio o APU no corresponde al catálogo asignado; revise el concepto antes de recalcular, aprobar o exportar') from exc

    async def validar_sobrecostos(
        self,
        presupuesto_id: UUID,
        expediente_id: UUID,
        presupuesto_base_id: UUID,
    ) -> Dict[str, Any]:
        """Valida sobrecostos vs presupuesto base.

        BUG ORIGINAL: reconstruía ambos presupuestos con partidas=[], así
        que monto_total siempre daba $0 para los dos lados y la validación
        reportaba "dentro de tolerancia" sin importar los datos reales.
        Ahora se usan directamente los montos ya calculados y guardados
        en BD (que ya reflejan sus partidas reales).
        """
        expediente = await self.db.execute(
            select(ExpedienteObra).where(ExpedienteObra.id == expediente_id, ExpedienteObra.tenant_id == self.tenant_id)
        )
        expediente_obj = expediente.scalar_one_or_none()
        if not expediente_obj:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Expediente {expediente_id} no encontrado",
            )

        result_actual = await self.db.execute(
            select(Presupuesto)
            .join(ExpedienteObra, Presupuesto.expediente_id == ExpedienteObra.id)
            .where(Presupuesto.id == presupuesto_id, Presupuesto.expediente_id == expediente_id)
            .where(ExpedienteObra.tenant_id == expediente_obj.tenant_id)
        )
        actual = result_actual.scalar_one_or_none()

        result_base = await self.db.execute(
            select(Presupuesto)
            .join(ExpedienteObra, Presupuesto.expediente_id == ExpedienteObra.id)
            .where(Presupuesto.id == presupuesto_base_id, Presupuesto.expediente_id == expediente_id)
            .where(ExpedienteObra.tenant_id == expediente_obj.tenant_id)
        )
        base = result_base.scalar_one_or_none()

        if not actual or not base:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                "Presupuesto no encontrado",
            )

        monto_actual = Decimal(str(actual.monto_total))
        monto_base = Decimal(str(base.monto_total))
        sobrecosto = monto_actual - monto_base
        if not monto_base.is_finite() or monto_base <= 0 or not monto_actual.is_finite():
            raise MegalodonException(ErrorCode.PRESUPUESTO_ERROR,
                'Comparación no calculable: la base debe ser positiva y los importes finitos', status_code=409)
        factor = sobrecosto / monto_base
        tolerancia = Decimal(str(self.motor_costeo.constantes.TOLERANCIA_FACTOR_SOBRECOSTO))

        return {
            "presupuesto_base": float(monto_base),
            "presupuesto_actual": float(monto_actual),
            "sobrecosto": float(sobrecosto),
            "factor_sobrecosto": float(factor),
            "dentro_tolerancia": factor <= tolerancia,
            "tolerancia_permitida": self.motor_costeo.constantes.TOLERANCIA_FACTOR_SOBRECOSTO,
        }

    # ─── Gestión incremental de partidas (desde catálogo real) ─────────
    #
    # ANTES: la única forma de meter partidas era crear_desde_costeo(),
    # todas de golpe al crear el presupuesto. No había manera de ir
    # agregando/editando/quitando una partida a la vez sobre un
    # presupuesto ya existente -- justo lo que hace falta para una UI de
    # costeo real donde el usuario busca un concepto en el catálogo
    # (CatalogoAPU: CMIC, CFE, Pemex, investigación de mercado, etc.),
    # decide una cantidad, y lo agrega.

    async def agregar_partida_desde_catalogo(
        self, presupuesto_id: UUID, expediente_id: UUID, catalogo_apu_id: UUID,
        cantidad: Decimal, actualizado_por_id: Optional[UUID] = None,
    ) -> Presupuesto:
        """Add and price a line atomically using the same audited assignment seam."""
        presupuesto = await self._reconstruir_partidas_desde_db(presupuesto_id, expediente_id, bloquear=True)
        self._exigir_editable(presupuesto)
        if (presupuesto.metadatos or {}).get('bim_cobertura'):
            raise MegalodonException(ErrorCode.PRESUPUESTO_ERROR, 'Las partidas BIM conservan la cobertura del modelo; genere una nueva versión')
        q = Decimal(str(cantidad))
        if not q.is_finite() or q <= 0 or q.quantize(Decimal('.0001')) != q:
            raise MegalodonException(ErrorCode.PRESUPUESTO_ERROR, 'La cantidad debe ser positiva y persistible con cuatro decimales')
        catalogo = await self.db.scalar(select(CatalogoAPU).where(
            CatalogoAPU.id == catalogo_apu_id, CatalogoAPU.tenant_id == self.tenant_id,
        ).with_for_update(read=True).execution_options(populate_existing=True))
        if catalogo is None:
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, 'Concepto de catálogo no encontrado')
        partida = Partida(id=uuid4(), tenant_id=self.tenant_id, presupuesto_id=presupuesto.id,
            numero=max((p.numero for p in presupuesto.partidas), default=0) + 1,
            descripcion=catalogo.descripcion, unidad=catalogo.unidad, cantidad=q,
            precio_unitario=0, importe=0, metadatos={})
        try:
            self.db.add(partida)
            await self.db.flush()
            return await self.asignar_catalogo_partida(presupuesto_id, expediente_id, partida.id,
                                                       catalogo_apu_id, actualizado_por_id)
        except Exception:
            await self.db.rollback()
            raise

    async def actualizar_cantidad_partida(
        self,
        presupuesto_id: UUID,
        expediente_id: UUID,
        partida_id: UUID,
        nueva_cantidad: float,
        actualizado_por_id: Optional[UUID] = None,
    ) -> Presupuesto:
        presupuesto = await self._reconstruir_partidas_desde_db(presupuesto_id, expediente_id, bloquear=True)
        self._exigir_editable(presupuesto)
        if (presupuesto.metadatos or {}).get('bim_cobertura'):
            raise MegalodonException(ErrorCode.PRESUPUESTO_ERROR,
                'Corrija las mediciones por elemento en BIM y genere una nueva versión; la cantidad agregada conserva su evidencia.')
        partida = next((p for p in presupuesto.partidas if str(p.id) == str(partida_id)), None)
        if not partida:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Partida {partida_id} no encontrada en el presupuesto {presupuesto_id}",
            )
        if (partida.metadatos or {}).get('topografia'):
            raise MegalodonException(ErrorCode.PRESUPUESTO_ERROR,
                'Corrija el terreno y genere una nueva versión; la cantidad conserva el cálculo topográfico de origen.')
        q = Decimal(str(nueva_cantidad))
        if not q.is_finite() or q <= 0 or q >= Decimal('1e14') or q.quantize(Decimal('.0001')) != q:
            raise MegalodonException(ErrorCode.PRESUPUESTO_ERROR, 'La cantidad debe ser positiva y persistible con cuatro decimales', 422)
        partida.cantidad = q
        await self.db.flush()
        return await self.recalcular(presupuesto_id, expediente_id, actualizado_por_id)

    async def asignar_catalogo_partida(
        self, presupuesto_id: UUID, expediente_id: UUID, partida_id: UUID,
        catalogo_apu_id: UUID, actualizado_por_id: UUID,
    ) -> Presupuesto:
        """Price a measured line without replacing its quantity or source."""
        from app.services.catalogo_costeo import resolve_catalogue
        presupuesto = await self._reconstruir_partidas_desde_db(presupuesto_id, expediente_id, bloquear=True)
        self._exigir_editable(presupuesto)
        self._validar_origen_topografia(presupuesto)
        partida = next((p for p in presupuesto.partidas if p.id == partida_id), None)
        if partida is None:
            raise MegalodonException(ErrorCode.DOCUMENTO_NO_ENCONTRADO, 'Partida no encontrada en el presupuesto')
        catalogo, concepto_costeo, precio, snapshot = await resolve_catalogue(
            self.db, self.tenant_id, catalogo_apu_id, actualizado_por_id)
        normalizar = lambda unidad: unidad.strip().lower().replace('³', '3').replace('²', '2')
        if normalizar(catalogo.unidad) != normalizar(partida.unidad):
            raise MegalodonException(ErrorCode.PRESUPUESTO_ERROR, 'Seleccione un concepto cotizable con la misma unidad de la partida')
        concepto = None
        if concepto_costeo:
            concepto = Concepto(id=uuid4(), tenant_id=self.tenant_id, clave=catalogo.clave,
                descripcion=catalogo.descripcion, unidad=partida.unidad, cantidad=1, costo_directo_unitario=precio,
                insumos=[Insumo(id=uuid4(), tenant_id=self.tenant_id, clave=item.clave, descripcion=item.descripcion,
                    tipo=item.tipo, unidad=item.unidad, cantidad=item.cantidad, precio_unitario=item.precio_unitario,
                    rendimiento=item.rendimiento, importe=item.importe) for item in concepto_costeo.insumos])
        try:
            partida.conceptos.clear()
            if concepto is not None:
                partida.conceptos.append(concepto)
            partida.precio_unitario = precio
            partida.metadatos = {**(partida.metadatos or {}), 'catalogo_asignado': snapshot}
            await self.db.flush()
            return await self.recalcular(presupuesto_id, expediente_id, actualizado_por_id)
        except Exception:
            await self.db.rollback()
            raise

    async def eliminar_partida(
        self,
        presupuesto_id: UUID,
        expediente_id: UUID,
        partida_id: UUID,
        actualizado_por_id: Optional[UUID] = None,
    ) -> Presupuesto:
        presupuesto = await self._reconstruir_partidas_desde_db(presupuesto_id, expediente_id, bloquear=True)
        self._exigir_editable(presupuesto)
        if (presupuesto.metadatos or {}).get('bim_cobertura'):
            raise MegalodonException(ErrorCode.PRESUPUESTO_ERROR,
                'Las partidas BIM conservan la cobertura del modelo; genere una nueva versión para corregirlas.')
        partida = next((p for p in presupuesto.partidas if str(p.id) == str(partida_id)), None)
        if not partida:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Partida {partida_id} no encontrada en el presupuesto {presupuesto_id}",
            )
        if (partida.metadatos or {}).get('topografia'):
            raise MegalodonException(ErrorCode.PRESUPUESTO_ERROR,
                'Las partidas de movimiento de tierras conservan el cálculo de origen; genere una nueva versión.')
        await self.db.delete(partida)
        if (presupuesto.metadatos or {}).get('actualizaciones_indices'):
            eliminados = {str(i.id) for c in partida.conceptos for i in c.insumos}
            presupuesto.metadatos = {**presupuesto.metadatos, 'actualizaciones_indices': {
                key: value for key, value in presupuesto.metadatos['actualizaciones_indices'].items()
                if key not in eliminados}}
        await self.db.flush()
        return await self.recalcular(presupuesto_id, expediente_id, actualizado_por_id)
