"""Revision-bound IFC coverage and explicit, auditable measurement policies."""
from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import json
from uuid import UUID
from sqlalchemy import select, func

from app.core.authorization import authorize_by_id
from app.core.errors import MegalodonException, ErrorCode
from app.models.bim import ModeloBIM
from app.models.bim_revision import RevisionBIM, DecisionMedicionBIM
from app.models.catalogo_apu import CatalogoAPU
from app.models.expediente import Documento
from app.engines.bim.coverage import inventario_cobertura
from app.engines.bim.motor_bim import TIPOS_DEFAULT

INCORPORABLES = ['IfcMember', 'IfcPlate', 'IfcCurtainWall', 'IfcRamp', 'IfcRampFlight', 'IfcStairFlight']


def huella(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def apu_snapshot(apu):
    return {k: format(Decimal(str(getattr(apu, k))).quantize(Decimal('0.0001')), 'f') if k == 'precio_unitario' else getattr(apu, k)
            for k in ['clave', 'descripcion', 'tipo', 'unidad', 'precio_unitario', 'fuente',
                      'vigencia_inicio', 'vigencia_fin', 'zona_economica', 'estado', 'desglose', 'origen']}


def documento_snapshot(doc):
    return {'id': str(doc.id), 'hash_sha256': doc.hash_sha256, 'version': doc.row_version,
            'tipo': doc.tipo_documental}


def rechazar(message, status=422):
    raise MegalodonException(ErrorCode.BIM_ERROR, message, status_code=status)


async def registrar_revision(db, model, ifc, result, content, tipos):
    source = hashlib.sha256(content).hexdigest()
    types = sorted(set(tipos or TIPOS_DEFAULT))
    geometry = hashlib.sha256()
    quantities = []
    for element in sorted(result.elementos, key=lambda e:e.global_id):
        mesh = element.malla
        geometry.update(json.dumps([element.global_id, mesh.vertices if mesh else None, mesh.caras if mesh else None],
                                   separators=(',', ':'), allow_nan=False).encode())
        quantities.append([element.global_id,element.volumen,element.area,element.longitud,element.fuente_volumen,element.fuente_area])
    geometry_hash = geometry.hexdigest()
    digest = huella({'fuente': source, 'geometria': geometry_hash, 'cantidades': quantities,
                     'tipos': types, 'adaptador': 'megalodon-ifc-coverage-v1'})
    revision = await db.scalar(select(RevisionBIM).where(
        RevisionBIM.modelo_id == model.id, RevisionBIM.tenant_id == model.tenant_id, RevisionBIM.huella == digest))
    if revision is None:
        revision = RevisionBIM(modelo_id=model.id, tenant_id=model.tenant_id,
            fuente_sha256=source, geometria_sha256=geometry_hash, huella=digest, tipos_admitidos=types,
            cobertura=inventario_cobertura(ifc, result.elementos), creado_por_id=model.creado_por_id)
        db.add(revision)
        await db.flush()
    model.revision_actual_id = revision.id
    return revision


class BIMOperationalService:
    def __init__(self, db, tenant_id):
        self.db, self.tenant_id = db, UUID(str(tenant_id))

    async def modelo(self, model_id, expediente_id, lock=False):
        stmt = select(ModeloBIM).where(ModeloBIM.id == model_id, ModeloBIM.expediente_id == expediente_id,
                                       ModeloBIM.tenant_id == self.tenant_id)
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        model = await self.db.scalar(stmt)
        if not model:
            rechazar('Modelo no encontrado en este expediente', 404)
        return model

    async def revision(self, model, revision_id=None):
        rid = revision_id or model.revision_actual_id
        row = await self.db.scalar(select(RevisionBIM).where(RevisionBIM.id == rid,
            RevisionBIM.modelo_id == model.id, RevisionBIM.tenant_id == self.tenant_id))
        if not row:
            rechazar('Reprocesa el modelo para registrar su cobertura por revisión', 409)
        return row

    async def cobertura(self, model_id, expediente_id, revision_id=None, estado=None, skip=0, limit=100):
        model = await self.modelo(model_id, expediente_id)
        revision = await self.revision(model, revision_id)
        rows = revision.cobertura
        filtered = [r for r in rows if estado is None or r['estado_cobertura'] == estado]
        return {'revision_id': str(revision.id), 'actual': revision.id == model.revision_actual_id,
            'modelo_estado': model.estado_procesamiento, 'fuente_sha256': revision.fuente_sha256,
            'geometria_sha256':revision.geometria_sha256,
            'tipos_admitidos': revision.tipos_admitidos, 'incorporables': INCORPORABLES,
            'tipos_pendientes':dict(Counter(r['tipo'] for r in rows if not r['admitido'])),
            'resumen': dict(Counter(r['estado_cobertura'] for r in rows)),
            'total': len(filtered), 'items': filtered[skip:skip+limit]}

    async def referencias(self, model_id, expediente_id):
        await self.modelo(model_id, expediente_id)
        rows = (await self.db.scalars(select(Documento).where(Documento.expediente_id == expediente_id))).all()
        return [{'id': str(d.id), 'nombre': d.nombre, 'tipo': d.tipo_documental,
                 'hash_sha256': d.hash_sha256, 'version': d.row_version} for d in rows]

    async def estado_decision(self, decision, model=None, lock=False):
        revision = await self.db.get(RevisionBIM, decision.revision_id)
        if model is None:
            model = await self.db.get(ModeloBIM, revision.modelo_id)
        reasons = []
        if model.revision_actual_id != decision.revision_id:
            reasons.append('CAMBIO_REVISION_MODELO')
        if model.estado_procesamiento != 'COMPLETADO':
            reasons.append('MODELO_EN_PROCESAMIENTO_O_ERROR')
        latest_query = select(func.max(DecisionMedicionBIM.version)).where(
            DecisionMedicionBIM.revision_id == decision.revision_id,
            DecisionMedicionBIM.familia_global_id == decision.familia_global_id,
            DecisionMedicionBIM.tenant_id == self.tenant_id)
        if decision.confirmada:
            latest_query = latest_query.where(DecisionMedicionBIM.confirmada.is_(True))
        latest = await self.db.scalar(latest_query)
        if latest != decision.version:
            reasons.append('DECISION_SUSTITUIDA')
        for line in decision.datos.get('lineas', []):
            if not line.get('catalogo_apu_id'):
                continue
            stmt = select(CatalogoAPU).where(CatalogoAPU.id == UUID(line['catalogo_apu_id']), CatalogoAPU.tenant_id == self.tenant_id).execution_options(populate_existing=True)
            if lock:
                stmt = stmt.with_for_update(read=True)
            apu = await self.db.scalar(stmt)
            if apu is None or huella(apu_snapshot(apu)) != line.get('apu_huella'):
                reasons.append('CAMBIO_CONCEPTO_O_PRECIO')
        evidence = decision.datos.get('documento')
        if evidence:
            stmt = select(Documento).where(Documento.id == UUID(evidence['id']), Documento.expediente_id == model.expediente_id).execution_options(populate_existing=True)
            if lock:
                stmt = stmt.with_for_update(read=True)
            doc = await self.db.scalar(stmt)
            if doc is None or documento_snapshot(doc) != evidence:
                reasons.append('CAMBIO_SUSTENTO_CONTRACTUAL')
        return {'estado': 'OBSOLETA' if reasons else 'VIGENTE' if decision.confirmada else 'BORRADOR',
                'causas': sorted(set(reasons))}

    async def listar_decisiones(self, model_id, expediente_id, revision_id=None):
        model = await self.modelo(model_id, expediente_id)
        revision = await self.revision(model, revision_id)
        decisions = (await self.db.scalars(select(DecisionMedicionBIM).where(
            DecisionMedicionBIM.revision_id == revision.id, DecisionMedicionBIM.tenant_id == self.tenant_id)
            .order_by(DecisionMedicionBIM.created_at.desc(), DecisionMedicionBIM.version.desc()))).all()
        from app.models.user import User
        actors = (await self.db.scalars(select(User).where(User.id.in_({d.creado_por_id for d in decisions}), User.tenant_id == self.tenant_id))).all()
        names = {a.id: a.full_name or a.email for a in actors}
        families = {r['global_id']: r.get('nombre') or r['tipo'] for r in revision.cobertura}
        return [{'id': str(d.id), 'revision_id': str(d.revision_id), 'familia_global_id': d.familia_global_id,
            'familia_nombre': families.get(d.familia_global_id, d.familia_global_id), 'usuario_nombre': names.get(d.creado_por_id, 'Responsable no disponible'),
            'version': d.version, 'criterio': d.criterio, 'datos': d.datos,
            'usuario_id': str(d.creado_por_id), 'creado_en': d.created_at.isoformat(),
            **await self.estado_decision(d, model)} for d in decisions]

    async def guardar_decision(self, model_id, expediente_id, actor_id, data):
        await authorize_by_id(self.db, actor_id, self.tenant_id)
        model = await self.modelo(model_id, expediente_id, lock=True)
        revision = await self.revision(model, data['revision_id'])
        if model.estado_procesamiento != 'COMPLETADO' or revision.id != model.revision_actual_id:
            rechazar('La revisión cambió; vuelve a consultar la cobertura', 409)
        rows = {r['global_id']: r for r in revision.cobertura}
        family = rows.get(data['familia_global_id'])
        if family is None:
            rechazar('La familia no pertenece a esta revisión')
        mode = data['criterio']
        if mode not in ('PADRE', 'COMPONENTES'):
            rechazar('Criterio de medición no admitido')
        members = {family['global_id'], *family['descendientes']}
        lines, seen = [], set()
        for item in data.get('lineas', []):
            gid = item['global_id']
            if gid not in members or (mode == 'PADRE' and gid != family['global_id']) or (mode == 'COMPONENTES' and gid == family['global_id']):
                rechazar('La línea contradice el criterio padre/componentes o pertenece a otra familia')
            row = rows.get(gid)
            if row is None or not row['admitido'] or not row.get('malla_disponible') or row['tipo'] == 'IfcBuildingElementProxy':
                rechazar('Incorpora el elemento y clasifica los Proxy antes de mapearlos económicamente')
            apu_id = item.get('catalogo_apu_id')
            apu = None
            if apu_id:
                apu = await self.db.scalar(select(CatalogoAPU).where(CatalogoAPU.id == UUID(str(apu_id)),
                    CatalogoAPU.tenant_id == self.tenant_id).with_for_update())
                if apu is None:
                    rechazar('Concepto ajeno al catálogo de este tenant', 404)
            key = (gid, str(apu_id))
            if key in seen:
                rechazar('Concepto repetido para el mismo elemento')
            seen.add(key)
            try:
                quantity = Decimal(str(item['cantidad']))
                if not quantity.is_finite() or not 0 < quantity < Decimal('1e12'):
                    raise ValueError()
            except (InvalidOperation, ValueError, KeyError):
                rechazar('La cantidad revisada debe ser positiva y finita')
            reference = str(item.get('referencia_medicion', '')).strip()
            scope = str(item.get('alcance', '')).strip()
            if len(reference) < 5 or len(scope) < 5:
                rechazar('Indica alcance y referencia de medición para cada concepto')
            lines.append({'global_id': gid, 'catalogo_apu_id': str(apu.id) if apu else None,
                'cantidad': str(quantity), 'referencia_medicion': reference, 'alcance': scope,
                'apu': apu_snapshot(apu) if apu else None,
                'apu_huella': huella(apu_snapshot(apu)) if apu else None})
        chosen = {line['global_id'] for line in lines}
        if any(set(rows[gid]['ancestros']) & chosen for gid in chosen):
            rechazar('No se puede cobrar un componente y su propio conjunto a la vez')
        doc = None
        if data.get('documento_id'):
            doc = await self.db.scalar(select(Documento).where(Documento.id == data['documento_id'],
                Documento.expediente_id == expediente_id).with_for_update())
            if doc is None:
                rechazar('El documento no pertenece al expediente', 404)
        contract_ref = str(data.get('referencia_contractual', '')).strip()
        confirmed = bool(data.get('confirmar'))
        excluded = data.get('exclusiones', {})
        for gid, reference in excluded.items():
            if gid not in members or gid in chosen or len(reference.strip()) < 5:
                rechazar('Exclusión sin sustento o ajena a la familia')
        covered = set(excluded)
        for gid in chosen:
            covered.update({gid, *rows[gid]['descendientes']})
        leaves = {gid for gid in members if gid in rows and not rows[gid]['componentes']}
        if confirmed:
            if (not doc or len(contract_ref) < 5 or not doc.hash_sha256 or len(doc.hash_sha256) != 64
                    or not any(word in doc.tipo_documental.upper() for word in ('CONTRATO', 'BASE', 'ANEXO', 'ACTA', 'ACLARACION'))):
                rechazar('Falta sustento contractual de esta obra; guarda la propuesta como borrador')
            if not lines or any(not line['apu'] or Decimal(line['apu']['precio_unitario']) <= 0 for line in lines):
                rechazar('Vincula conceptos con precio antes de confirmar')
            if not (leaves | (members - set(rows))).issubset(covered):
                rechazar('Faltan componentes por medir o excluir con referencia contractual')
        previous = await self.db.scalar(select(func.max(DecisionMedicionBIM.version)).where(
            DecisionMedicionBIM.revision_id == revision.id,
            DecisionMedicionBIM.familia_global_id == family['global_id']))
        version = (previous or 0) + 1
        decision = DecisionMedicionBIM(tenant_id=self.tenant_id, revision_id=revision.id,
            familia_global_id=family['global_id'], version=version, criterio=mode, confirmada=confirmed,
            creado_por_id=actor_id, datos={'lineas': lines, 'exclusiones': excluded,
                'referencia_contractual': contract_ref, 'documento': documento_snapshot(doc) if doc else None,
                'fuente_revision_sha256': revision.fuente_sha256})
        self.db.add(decision)
        await self.db.commit()
        return decision

    async def crear_presupuesto(self, model_id, expediente_id, actor_id, decision_ids, parametros):
        from app.services.presupuesto_service import PresupuestoService
        await authorize_by_id(self.db, actor_id, self.tenant_id)
        model = await self.modelo(model_id, expediente_id, lock=True)
        revision = await self.revision(model)
        decisions, covered, items, used_families, economic_lines = [], set(), [], set(), []
        rows = {r['global_id']: r for r in revision.cobertura}
        for did in decision_ids:
            decision = await self.db.scalar(select(DecisionMedicionBIM).where(
                DecisionMedicionBIM.id == did, DecisionMedicionBIM.tenant_id == self.tenant_id,
                DecisionMedicionBIM.revision_id == revision.id))
            if not decision or not decision.confirmada or (await self.estado_decision(decision, model, lock=True))['estado'] != 'VIGENTE':
                rechazar('Solo pueden presupuestarse decisiones confirmadas y vigentes', 409)
            family = rows[decision.familia_global_id]
            if family['global_id'] in used_families or set(family['ancestros']) & used_families or set(family['descendientes']) & used_families:
                rechazar('Decisiones de familias superpuestas')
            used_families.add(family['global_id'])
            covered.update({family['global_id'], *family['descendientes']})
            decisions.append(str(decision.id))
            for line in decision.datos['lineas']:
                apu = line['apu']
                economic_lines.append({'global_id':line['global_id'], 'catalogo_apu_id':line['catalogo_apu_id'], 'cantidad':line['cantidad'], 'unidad':apu['unidad'], 'referencia_medicion':line['referencia_medicion']})
                items.append({'descripcion': f"{apu['descripcion']} · {line['alcance']}",
                    'unidad': apu['unidad'], 'cantidad': float(line['cantidad']),
                    'precio_unitario': float(apu['precio_unitario'])})
        if not items:
            rechazar('Selecciona decisiones confirmadas con mediciones')
        pending = sorted(set(rows) - covered)
        coverage = {'modelo_id': str(model.id), 'revision_id': str(revision.id),
            'decisiones_ids': decisions, 'mediciones_decisiones':economic_lines, 'completa': not pending, 'elementos_totales': len(rows),
            'elementos_medidos': len(covered & set(rows)), 'elementos_pendientes': pending, 'capturas': []}
        return await PresupuestoService(self.db, self.tenant_id).crear_desde_costeo(
            expediente_id=expediente_id, nombre='Presupuesto desde decisiones BIM',
            partidas_data=items, parametros_costeo=parametros, creado_por_id=actor_id, evidencia_bim=coverage)

    async def presupuesto_obsoleto(self, budget, lock=False):
        coverage = (budget.metadatos or {}).get('bim_cobertura', {})
        if not coverage.get('revision_id'):
            return False
        model = await self.modelo(UUID(coverage['modelo_id']), budget.expediente_id, lock=lock)
        if str(model.revision_actual_id) != coverage['revision_id'] or model.estado_procesamiento != 'COMPLETADO':
            return True
        for did in coverage.get('decisiones_ids', []):
            decision = await self.db.scalar(select(DecisionMedicionBIM).where(
                DecisionMedicionBIM.id == UUID(did), DecisionMedicionBIM.tenant_id == self.tenant_id))
            if not decision or (await self.estado_decision(decision, model, lock=lock))['estado'] != 'VIGENTE':
                return True
        return False
