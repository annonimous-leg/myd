"""Import verified source editions into the actual tenant costing catalogue.

SQL supplied in a package is never executed. Original extraction rows remain
immutable; usable projections must reproduce every published component cent.
Parametric models and unpriced assemblies do not become contractual APUs.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import asyncio
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import re
from uuid import UUID, uuid4

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode, MegalodonException
from app.models.catalogo_apu import CatalogoAPU
from app.models.catalogo_importacion import CatalogoImportacion, CatalogoRegistro, EstimacionParametrica
from app.models.user import Tenant, User
from app.services.catalogo_package import KEYS, PARENT, VerifiedPackage, strict_json, verify_package

CENT = Decimal('.01')
SIX = Decimal('.000001')
UNITS = {'m', 'm2', 'm3', 'm3/km', 'm3/est', 'kg', 't', 't/km', 'km', 'l', 'pza', 'jgo',
         'ha', 'hm', 'dm2', 'dm3', 'm3/hm', 'km-carril', 'sondeo', 'plaza', 'sitio', 'analisis',
         'nucleo', 'prueba', 'informe', 'reporte', 'muestra', 'muestreo', 'h', 'dia', 'jornada', 'mes', 'lote', 'viaje', 'tiro', 'junta', 'uso', 'pt', 'millar', 'caja', 'cubeta'}
ALIASES = {'m²': 'm2', 'm³': 'm3', 'm³/km': 'm3/km', 'm³/est': 'm3/est', 'pz': 'pza', 'pieza': 'pza',
           'hr': 'h', 'hora': 'h', 'juego': 'jgo', 'ml': 'm', 'mt': 'm', 'ton': 't', 'día': 'dia', 'dm³': 'dm3', 'dm²': 'dm2', 'm³/hm': 'm3/hm', 'jornal': 'jornada',
           'análisis': 'analisis', 'núcleo': 'nucleo'}
COMPONENT_TYPES = {'MATERIALES': 'MATERIAL', 'MANO DE OBRA': 'MANO_OBRA', 'DE OBRA': 'MANO_OBRA',
                   'EQUIPO Y HERRAMIENTA': 'EQUIPO', 'Y HERRAMIENTA': 'EQUIPO', 'BASICOS': 'AUXILIAR'}


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


async def _lock_writer(db, user):
    actor_id, tenant_id, version = user.id, user.tenant_id, user.auth_version
    # Administration locks tenant then user too. Recheck after acquiring that
    # order, including when source verification or another import took time.
    active = await db.scalar(select(Tenant.is_active).where(Tenant.id == tenant_id).with_for_update())
    actor = await db.scalar(select(User).where(User.id == actor_id, User.tenant_id == tenant_id)
        .with_for_update().execution_options(populate_existing=True))
    if (not active or actor is None or not actor.is_active or actor.auth_version != version
            or actor.role not in {'superadmin', 'admin', 'tecnico', 'revisor'}):
        raise MegalodonException(ErrorCode.PERMISO_DENEGADO,
            'Sus permisos cambiaron antes de guardar el catálogo o la estimación', status_code=403)


def unit(value: str, *, component=False) -> str:
    result = ALIASES.get(value.strip().lower(), value.strip().lower())
    if result not in UNITS and not (component and result in {'%mo', '%eq', '%ma', '%mat', '%mdo'}):
        raise ValueError('UNIDAD_NO_INTERPRETABLE')
    return result


def number(value: str, *, positive=True) -> Decimal:
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError('VALOR_NO_COTIZABLE') from exc
    if not result.is_finite() or result < 0 or (positive and result == 0):
        raise ValueError('VALOR_NO_COTIZABLE')
    return result


def components_projection(children: list[dict], price: Decimal) -> list[dict]:
    normalized = []
    for child in sorted(children, key=lambda r: int(r['orden'])):
        q = number(child['cantidad'])
        pu = number(child['costo_unitario'], positive=False)
        amount = number(child['importe'], positive=False)
        mode = strict_json(child['registro_bruto']).get('modo_calculo_verificado', 'MULTIPLICACION')
        if mode == 'DIVISION_RENDIMIENTO':
            # Convert performance to consumption only when the persisted six
            # decimals independently reproduce the original published cent.
            q = (Decimal(1) / q).quantize(SIX, rounding=ROUND_HALF_UP)
        elif mode not in {'MULTIPLICACION', 'MULTIPLICACION_REDONDEO_CANTIDAD'}:
            raise ValueError('FORMULA_COMPONENTE_NO_SOPORTADA')
        if q.quantize(SIX) != q or pu.quantize(CENT) != pu:
            raise ValueError('PRECISION_COMPONENTE_NO_PERSISTIBLE')
        if (q * pu).quantize(CENT, rounding=ROUND_HALF_UP) != amount:
            raise ValueError('ARITMETICA_COMPONENTE_NO_REPRODUCIBLE')
        kind = COMPONENT_TYPES.get(child['tipo_componente'])
        if kind is None:
            raise ValueError('TIPO_COMPONENTE_REQUIERE_REVISION')
        u = unit(child['unidad'], component=True)
        if u.startswith('%'):
            kind = 'HERRAMIENTA'
        if not child['codigo'] or len(child['codigo']) > 50:
            raise ValueError('CLAVE_COMPONENTE_NO_PERSISTIBLE')
        normalized.append({'clave': child['codigo'], 'descripcion': child['descripcion'], 'tipo': kind, 'unidad': u,
                           'cantidad': str(q), 'precio_unitario': str(pu), 'rendimiento': '1'})
    total = sum((Decimal(c['cantidad']) * Decimal(c['precio_unitario'])).quantize(CENT, rounding=ROUND_HALF_UP)
                for c in normalized)
    if total != price:
        raise ValueError('DESGLOSE_NO_CIERRA')
    return normalized


def source_without_vat(records, sid):
    # Preserve the signed paragraph and page proving the CMIC direct-cost
    # basis. A CFE table without a tax declaration is not assumed tax-free.
    for row in records['pagina_fuente']:
        if row['fuente_id'] != sid:
            continue
        text = row['texto_bruto']
        match = re.search(r'(?:no\s+incluyen?|excluyendo)\s+(?:el\s+)?(?:impuesto\s+al\s+valor\s+agregado\s*\(\s*IVA\s*\)|IVA)', text, re.I)
        if match:
            return {'pagina_pdf': row['pagina_pdf'], 'texto_sha256': row['texto_sha256'],
                    'declaracion': match.group(0)}
    source = next(r for r in records['fuente'] if r['fuente_id'] == sid)
    metadata = strict_json(source['metadatos'])
    if (source['familia'] != 'SICT_DGST_2026' or source['tipo_fuente'] != 'TABULADOR_COSTO_DIRECTO'
            or not isinstance(metadata, dict) or metadata.get('perfil') not in {'construccion', 'maquinaria'}):
        return None
    pages = [r for r in records['pagina_fuente'] if r['fuente_id'] == sid]
    direct = next((r for r in pages if re.search(r'a\s+costo\s+directo', r['texto_bruto'], re.I)), None)
    for row in pages:
        match = re.search(r'En\s+general\s+a\s+todos\s+los\s+precios\s+cotizados\s+que\s+incluyen\s+el\s+IVA,\s*'
                          r'se\s+les\s+deduce\s+el\s+16%\s+por\s+concepto\s+de\s+este\s+impuesto', row['texto_bruto'], re.I)
        if direct and match:
            # The published direct cost already uses the source's tax basis.
            # Preserve its exceptions (fuel/IEPS, exempt assets); never divide
            # the final price by 1.16 a second time or recompute its components.
            return {'pagina_pdf': row['pagina_pdf'], 'texto_sha256': row['texto_sha256'],
                    'declaracion': match.group(0), 'metodo': 'SICT_PRECIO_DIRECTO_PUBLICADO',
                    'pagina_costo_directo': direct['pagina_pdf'], 'texto_costo_directo_sha256': direct['texto_sha256'],
                    'condiciones': 'Se conserva la metodología y excepciones fiscales del PDF; no se modifica el precio publicado'}
    return None


def prepare(verified: VerifiedPackage, selected: set[str]):
    records = verified.records
    sources = {r['fuente_id']: r for r in records['fuente']}
    if not selected or not selected <= sources.keys():
        raise ValueError('Seleccione identidades de fuente existentes en el paquete')
    parents = {table: {r[KEYS[table]]: r for r in records[table]}
               for table in ('partida_catalogo', 'modelo_parametrico')}
    children = defaultdict(list)
    for row in records['componente_partida']:
        children[row['partida_id']].append(row)
    vat = {sid: source_without_vat(records, sid) for sid in selected}
    rows, projections = [], {}
    for table, items in records.items():
        for original in items:
            sid = original.get('fuente_id')
            if table in PARENT:
                parent_table, key = PARENT[table]
                sid = parents[parent_table][original[key]]['fuente_id']
            if table != 'ubicacion' and sid not in selected:
                continue
            eid = f"{sid}:{original['pagina_pdf']}" if table == 'pagina_fuente' else original[KEYS[table]]
            state, reasons = 'CONSULTA', []
            if table != 'ubicacion':
                if sid not in verified.verified_source_ids: reasons.append('PDF_ORIGINAL_NO_COTEJADO')
                if sid in verified.blocked_source_ids or (table, eid) in verified.blocked:
                    reasons.append('INCIDENCIA_O_COMPONENTE_PENDIENTE')
            if original.get('estado_revision') in {'CUARENTENA', 'REQUIERE_REVISION'}:
                reasons.append('REVISION_PENDIENTE')
            if reasons:
                state = 'CUARENTENA'
            elif table == 'partida_catalogo':
                try:
                    if original['estado_revision'] != 'VALIDADO_ESTRUCTURAL': raise ValueError('REGISTRO_INFORMATIVO')
                    if strict_json(original['aplicabilidad']).get('no_usar_para_costear'):
                        raise ValueError('NO_USAR_PARA_COSTEAR')
                    if original['moneda'] != 'MXN' or sources[sid]['moneda'] != 'MXN': raise ValueError('MONEDA_NO_SOPORTADA')
                    if not vat[sid]: raise ValueError('IVA_NO_DOCUMENTADO')
                    date.fromisoformat(original['fecha_precio'])
                    pu = number(original['costo'])
                    if pu.quantize(CENT) != pu: raise ValueError('PRECIO_NO_PERSISTIBLE')
                    u = unit(original['unidad'])
                    if not original['codigo'] or len(original['codigo']) > 50: raise ValueError('CLAVE_NO_PERSISTIBLE')
                    kind = {'CONCEPTO_TRABAJO': 'CONCEPTO', 'PRECIO_UNITARIO': 'CONCEPTO',
                            'MATERIAL': 'MATERIAL', 'MAQUINARIA_EQUIPO': 'MAQUINARIA', 'COSTO_HORARIO': 'MAQUINARIA'}.get(original['tipo_registro'])
                    cs = children[eid]
                    if original['tipo_registro'] == 'INSUMO_O_CONCEPTO' and cs: kind = 'CONCEPTO'
                    if kind is None: raise ValueError('TIPO_AMBIGUO_REQUIERE_REVISION')
                    # Hourly fixed-charge formulae are preserved as evidence;
                    # their observed hourly cost is an input, not a fake APU.
                    insumos = components_projection(cs, pu) if cs and original['tipo_registro'] != 'COSTO_HORARIO' else []
                    projections[eid] = dict(clave=original['codigo'], descripcion=original['descripcion'], tipo=kind,
                        unidad=u, precio_unitario=pu, fuente=f"{sid}@{verified.package_sha256[:12]}",
                        zona_economica=original['zona'] or '', vigencia_inicio=original['fecha_precio'],
                        incluye_iva=False, desglose={'insumos': insumos} if insumos else None,
                        origen={'esquema': 1, 'paquete_sha256': verified.package_sha256, 'entidad_id': eid,
                                'fila_sha256': fingerprint(original), 'fuente': sources[sid],
                                'paginas': [original['pagina_inicio'], original['pagina_fin']],
                                'iva': vat[sid], 'tipo_registro': original['tipo_registro'],
                                'naturaleza_costo': original['naturaleza_costo'],
                                'aplicabilidad': strict_json(original['aplicabilidad']),
                                'componentes_originales': cs, 'revision': 'ESTRUCTURAL; NO CERTIFICA REVISION VISUAL'})
                    state = 'COTIZABLE' if kind == 'CONCEPTO' else 'INSUMO'
                except (ValueError, InvalidOperation) as exc:
                    state, reasons = 'CUARENTENA', [str(exc) or 'VALOR_NO_COTIZABLE']
            elif table in {'modelo_parametrico', 'factor_geografico'}:
                try:
                    if original['estado_revision'] != 'VALIDADO_ESTRUCTURAL': raise ValueError('REGISTRO_INFORMATIVO')
                    if table == 'modelo_parametrico':
                        number(original['costo_por_unidad'])
                        unit(original['unidad_medida_base'])
                        if original['moneda'] != 'MXN': raise ValueError('MONEDA_NO_SOPORTADA')
                        if strict_json(original['aplicabilidad']).get('no_usar_para_costear'):
                            raise ValueError('NO_USAR_PARA_COSTEAR')
                        state = 'PARAMETRICO'
                    else:
                        number(original['valor'])
                        if original['tipo_factor'] != 'FIC_INTERCIUDAD': raise ValueError('FACTOR_NO_SOPORTADO')
                        state = 'FACTOR'
                except (ValueError, InvalidOperation) as exc:
                    state, reasons = 'CUARENTENA', [str(exc)]
            rows.append(dict(tabla=table, entidad_id=eid, fuente_id=sid or '__COMUN__', estado=state,
                             motivos=reasons, original=original, sha256=fingerprint(original)))
    return rows, projections


async def import_package(db: AsyncSession, user: User, package: Path, originals: Path, selected: set[str]):
    if user.role not in {'superadmin', 'admin', 'tecnico', 'revisor'} or not user.is_active:
        raise MegalodonException(ErrorCode.PERMISO_DENEGADO, 'Su perfil no permite importar catálogos', status_code=403)
    verified = await asyncio.to_thread(verify_package, package, originals)
    rows, projections = await asyncio.to_thread(prepare, verified, selected)
    selection_hash = fingerprint(sorted(selected))
    tenant_id, actor_id = user.tenant_id, user.id
    try:
        # Serialize this tenant's imports. The unique edition key remains a
        # database constraint, so retries cannot create duplicate catalogues.
        await _lock_writer(db, user)
        existing = await db.scalar(select(CatalogoImportacion).where(
            CatalogoImportacion.tenant_id == tenant_id,
            CatalogoImportacion.paquete_sha256 == verified.package_sha256,
            CatalogoImportacion.seleccion_sha256 == selection_hash))
        if existing:
            await db.commit()
            return existing, False
        batch = CatalogoImportacion(id=uuid4(), tenant_id=tenant_id, creado_por_id=actor_id,
            paquete_sha256=verified.package_sha256, seleccion_sha256=selection_hash, fuentes=sorted(selected),
            resumen={'verificacion': verified.report(), 'registros': len(rows),
                     'estados': dict(Counter(r['estado'] for r in rows)),
                     'cuarentena_motivos': dict(Counter(m for r in rows for m in r['motivos'])),
                     'proyecciones_costeo': len(projections), 'revision_visual_certificada': False})
        db.add(batch)
        await db.flush()
        for row in rows:
            row.update(id=uuid4(), tenant_id=tenant_id, importacion_id=batch.id)
        for start in range(0, len(rows), 500):
            await db.execute(insert(CatalogoRegistro), rows[start:start + 500])
        projected = []
        for row in rows:
            if row['tabla'] != 'partida_catalogo' or row['entidad_id'] not in projections:
                continue
            values = projections[row['entidad_id']]
            values['origen'] = {**values['origen'], 'importacion_id': str(batch.id), 'registro_id': str(row['id'])}
            projected.append(dict(id=uuid4(), tenant_id=tenant_id, creado_por_id=actor_id,
                                  registro_importado_id=row['id'], **values))
        for start in range(0, len(projected), 500):
            await db.execute(insert(CatalogoAPU), projected[start:start + 500])
        await db.commit()
        return batch, True
    except Exception:
        await db.rollback()
        raise


async def estimate(db, user, modelo_id: UUID, factor_id: UUID, cantidad: Decimal,
                   ajuste: Decimal, justificacion: str):
    if user.role not in {'superadmin', 'admin', 'tecnico', 'revisor'} or not user.is_active:
        raise MegalodonException(ErrorCode.PERMISO_DENEGADO, 'Su perfil no permite guardar estimaciones', status_code=403)
    try:
        await _lock_writer(db, user)
        model = await db.scalar(select(CatalogoRegistro).where(CatalogoRegistro.id == modelo_id,
                                                             CatalogoRegistro.tenant_id == user.tenant_id))
        factor = await db.scalar(select(CatalogoRegistro).where(CatalogoRegistro.id == factor_id,
                                                              CatalogoRegistro.tenant_id == user.tenant_id))
        if model is None or factor is None:
            raise MegalodonException(ErrorCode.NOT_FOUND, 'Modelo o factor no encontrado', status_code=404)
        if (model.tabla != 'modelo_parametrico' or model.estado != 'PARAMETRICO'
                or factor.tabla != 'factor_geografico' or factor.estado != 'FACTOR'
                or model.importacion_id != factor.importacion_id):
            raise MegalodonException(ErrorCode.BAD_REQUEST, 'Seleccione un modelo y FIC habilitados de la misma edición')
        if fingerprint(model.original) != model.sha256 or fingerprint(factor.original) != factor.sha256:
            raise MegalodonException(ErrorCode.CONFLICT, 'La evidencia fuente fue alterada')
        if not cantidad.is_finite() or cantidad <= 0 or not ajuste.is_finite() or ajuste <= 0 or not justificacion.strip():
            raise MegalodonException(ErrorCode.BAD_REQUEST, 'Indique cantidad, ajuste positivo y justificación del proyecto')
        # Same batch is not enough: it may contain unrelated publishers or
        # SICT columns for different kinds of work. Never silently use General.
        sources = (await db.scalars(select(CatalogoRegistro).where(
            CatalogoRegistro.importacion_id == model.importacion_id,
            CatalogoRegistro.tenant_id == user.tenant_id, CatalogoRegistro.tabla == 'fuente',
            CatalogoRegistro.entidad_id.in_([model.fuente_id, factor.fuente_id])))).all()
        by_source = {r.entidad_id: r for r in sources}
        if (len(by_source) != len({model.fuente_id, factor.fuente_id})
                or any(fingerprint(r.original) != r.sha256 for r in sources)):
            raise MegalodonException(ErrorCode.CONFLICT, 'La procedencia del modelo o factor fue alterada')
        family = by_source[model.fuente_id].original['familia']
        if family != by_source[factor.fuente_id].original['familia']:
            raise MegalodonException(ErrorCode.BAD_REQUEST, 'Modelo y factor pertenecen a familias de fuentes diferentes')
        if family == 'SICT_DGST_2026':
            scope = strict_json(model.original['aplicabilidad']).get('fic_especialidad')
            actual_scope = strict_json(factor.original['instrucciones']).get('fic_especialidad')
            if (model.fuente_id != factor.fuente_id or not scope or scope == 'GENERAL' or scope != actual_scope):
                raise MegalodonException(ErrorCode.BAD_REQUEST, 'El FIC SICT debe corresponder a la especialidad y fuente del modelo')
        base = model.original
        fic = Decimal(factor.original['valor'])
        pu = Decimal(base['costo_por_unidad'])
        amount = (cantidad * pu * fic * ajuste).quantize(CENT, rounding=ROUND_HALF_UP)
        if amount >= Decimal('10000000000000000'):
            raise MegalodonException(ErrorCode.BAD_REQUEST, 'La estimación excede el límite persistible')
        evidence = {'tipo': 'ANTEPRESUPUESTO_PARAMETRICO', 'apto_aprobacion_contractual': False,
            'importacion_id': str(model.importacion_id), 'modelo': base, 'modelo_sha256': model.sha256,
            'factor': factor.original, 'factor_sha256': factor.sha256,
            'cantidad': str(cantidad), 'precio_base': str(pu), 'fic': str(fic), 'ajuste_proyecto': str(ajuste),
            'justificacion': justificacion.strip(), 'monto': str(amount), 'usuario_id': str(user.id),
            'fecha_base': 'FUENTE_ORIGINAL; SIN ACTUALIZACION POR INFLACION'}
        evidence['sha256'] = fingerprint(evidence)
        result = EstimacionParametrica(tenant_id=user.tenant_id, creado_por_id=user.id,
            modelo_registro_id=model.id, factor_registro_id=factor.id, cantidad=cantidad, monto=amount, evidencia=evidence)
        db.add(result)
        await db.commit()
        await db.refresh(result)
        return result
    except Exception:
        await db.rollback()
        raise


async def verify_projection(db, catalog):
    """An imported price must still match its immutable extraction edition."""
    if catalog.registro_importado_id is None:
        return
    try:
        record = await db.scalar(select(CatalogoRegistro).where(CatalogoRegistro.id == catalog.registro_importado_id,
            CatalogoRegistro.tenant_id == catalog.tenant_id).execution_options(populate_existing=True))
        origin = catalog.origen
        if record is None or record.tabla != 'partida_catalogo' or record.estado != 'COTIZABLE':
            raise ValueError('No es una partida cotizable importada')
        if fingerprint(record.original) != record.sha256 or origin['fila_sha256'] != record.sha256:
            raise ValueError('Cambió la evidencia de extracción')
        row = record.original
        source = await db.scalar(select(CatalogoRegistro).where(CatalogoRegistro.importacion_id == record.importacion_id,
            CatalogoRegistro.tenant_id == catalog.tenant_id, CatalogoRegistro.tabla == 'fuente',
            CatalogoRegistro.entidad_id == record.fuente_id))
        if source is None or fingerprint(source.original) != source.sha256 or origin['fuente'] != source.original:
            raise ValueError('Cambió la fuente')
        if (catalog.tipo != 'CONCEPTO' or catalog.clave != row['codigo'] or catalog.descripcion != row['descripcion']
                or catalog.unidad != unit(row['unidad']) or catalog.precio_unitario != Decimal(row['costo'])
                or catalog.incluye_iva or catalog.vigencia_inicio != row['fecha_precio']
                or catalog.zona_economica != (row['zona'] or '') or origin['importacion_id'] != str(record.importacion_id)
                or origin['registro_id'] != str(record.id) or not origin['iva']):
            raise ValueError('El precio o identidad difiere de la edición')
        children = origin['componentes_originales']
        ids = [c['componente_id'] for c in children]
        persisted = (await db.scalars(select(CatalogoRegistro).where(CatalogoRegistro.importacion_id == record.importacion_id,
            CatalogoRegistro.tenant_id == catalog.tenant_id, CatalogoRegistro.tabla == 'componente_partida',
            CatalogoRegistro.entidad_id.in_(ids)))).all() if ids else []
        if (len(persisted) != len(children) or any(fingerprint(c.original) != c.sha256 for c in persisted)
                or {c.sha256 for c in persisted} != {fingerprint(c) for c in children}):
            raise ValueError('Cambió el desglose fuente')
        expected = components_projection(children, Decimal(row['costo'])) if children else []
        if (catalog.desglose or {}).get('insumos', []) != expected:
            raise ValueError('Cambió el APU proyectado')
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise MegalodonException(ErrorCode.PRESUPUESTO_ERROR,
            'El catálogo importado difiere de su edición; revise la evidencia antes de costear') from exc
