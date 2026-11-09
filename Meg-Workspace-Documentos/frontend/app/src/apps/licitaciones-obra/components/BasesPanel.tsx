import { useState } from 'react';
import type { FormEvent } from 'react';
import { megalodonClient } from '@/lib/api-client';
import type { Criterion, EvaluationMatrix, LicitacionRecord } from '@/lib/licitacion-types';
import { useAuthStore } from '@/stores/useAuthStore';
import { useWorkspace } from '../useWorkspace';
import { WorkspaceField, WorkspaceError, inputClass, buttonClass, writeRoles, approveRoles } from './WorkspaceFields';

type Layer = 'legal' | 'tecnico' | 'economico';
type Row = { id: string; code: string; description: string; field: string; required: string; weight: string; original: Criterion };
const labels: Record<Layer, string> = { legal: 'Legal', tecnico: 'Técnica', economico: 'Económica' };
const states: Record<string, string> = {
  INVESTIGACION_MERCADO: 'Investigación de mercado', SELECCION_PROCEDIMIENTO: 'Selección de procedimiento',
  CONVOCATORIA: 'Convocatoria', JUNTA_ACLARACIONES: 'Junta de aclaraciones',
  RECEPCION_PROPUESTAS: 'Recepción de propuestas', APERTURA: 'Apertura',
};
const emptyRow = (): Row => ({ id: crypto.randomUUID(), code: '', description: '', field: '', required: '', weight: '', original: {} });
function rows(matrix: EvaluationMatrix | null, key: Layer): Row[] {
  return Object.entries(matrix?.[key] || {}).map(([code, spec]) => ({ id: crypto.randomUUID(), code,
    description: spec.descripcion || '', field: spec.campo || code,
    required: String(spec.requerido ?? true), weight: String(spec.peso ?? spec.ponderacion ?? ''), original: spec }));
}

export default function BasesPanel({ expedienteId }: { expedienteId: string }) {
  const { workspace, loading, error, reload } = useWorkspace(expedienteId);
  return <section className="rounded-xl border border-zinc-700 bg-zinc-900/40 p-5 space-y-4">
    <h2 className="text-xl font-bold">Bases y criterios de evaluación</h2>
    <WorkspaceError message={error} />
    {loading ? <p role="status">Cargando bases…</p> : workspace &&
      <BasesEditor key={`${workspace.licitacion.id}:${workspace.licitacion.row_version}`} lic={workspace.licitacion} onSaved={reload} />}
  </section>;
}

function BasesEditor({ lic, onSaved }: { lic: LicitacionRecord; onSaved: () => Promise<void> }) {
  const role = useAuthStore(s => s.user?.role) || '';
  const [bases, setBases] = useState(lic.bases || '');
  const [criteria, setCriteria] = useState<Record<Layer, Row[]>>({ legal: rows(lic.matriz_evaluacion, 'legal'), tecnico: rows(lic.matriz_evaluacion, 'tecnico'), economico: rows(lic.matriz_evaluacion, 'economico') });
  const [minimumTech, setMinimumTech] = useState(String(lic.matriz_evaluacion?.minimo_tecnico ?? ''));
  const [minimumEcon, setMinimumEcon] = useState(String(lic.matriz_evaluacion?.minimo_economico ?? ''));
  const [marketMax, setMarketMax] = useState(lic.matriz_evaluacion?.variacion_mercado_max === undefined ? '' : String(lic.matriz_evaluacion.variacion_mercado_max * 100));
  const [marketPenalty, setMarketPenalty] = useState(lic.matriz_evaluacion?.variacion_mercado_penalty === undefined ? '' : String(lic.matriz_evaluacion.variacion_mercado_penalty * 100));
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [next, setNext] = useState('');
  const early = ['PLANEACION', 'INVESTIGACION_MERCADO', 'SELECCION_PROCEDIMIENTO', 'CONVOCATORIA'].includes(lic.estado);
  const editable = writeRoles.includes(role) && !lic.bases_congeladas && early;
  const change = (layer: Layer, id: string, field: keyof Row, value: string) => {
    setDirty(true); setCriteria(previous => ({ ...previous, [layer]: previous[layer].map(row => row.id === id ? { ...row, [field]: value } : row) }));
  };
  async function run(action: () => Promise<unknown>) {
    setBusy(true); setError('');
    try { await action(); await onSaved(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    const matrix: EvaluationMatrix = { ...lic.matriz_evaluacion, minimo_tecnico: Number(minimumTech), minimo_economico: Number(minimumEcon) };
    for (const layer of ['legal', 'tecnico', 'economico'] as const) {
      const list = criteria[layer];
      const codes = list.map(row => row.code.trim());
      if (!list.length || new Set(codes).size !== list.length) { setError(`La capa ${labels[layer]} necesita criterios con códigos únicos.`); return; }
      matrix[layer] = Object.fromEntries(list.map(row => [row.code.trim(), { ...row.original, descripcion: row.description.trim(),
        ...(layer === 'legal' ? { campo: row.field.trim() || row.code.trim(), requerido: row.required === 'true' } : { peso: Number(row.weight) }),
      }]));
      if (layer !== 'legal' && list.reduce((sum, row) => sum + Number(row.weight), 0) <= 0) { setError(`La suma de pesos de ${labels[layer]} debe ser positiva.`); return; }
    }
    if (Boolean(marketMax) !== Boolean(marketPenalty)) { setError('Completa ambos valores de la regla de mercado o deja ambos vacíos.'); return; }
    delete matrix.variacion_mercado_max; delete matrix.variacion_mercado_penalty;
    if (marketMax !== '') { matrix.variacion_mercado_max = Number(marketMax) / 100; matrix.variacion_mercado_penalty = Number(marketPenalty) / 100; }
    await run(() => megalodonClient.licitaciones.actualizar(lic.id, { bases: bases.trim(), matriz_evaluacion: matrix, version_esperada: lic.row_version }));
  }
  return <div className="space-y-5">
    <p className="text-sm text-zinc-400">{lic.folio} · {lic.estado} · Bases versión {lic.bases_version} · {lic.bases_congeladas ? 'Congeladas' : 'Pendientes de aprobación'}</p>
    <form onSubmit={save} onChange={() => setDirty(true)} className="space-y-4">
      <fieldset disabled={!editable || busy} className="space-y-4">
        <label className="block text-sm text-zinc-300">Contenido y referencias de las bases<textarea required value={bases} onChange={e => setBases(e.target.value)} rows={5} className={inputClass} /></label>
        {(['legal', 'tecnico', 'economico'] as const).map(layer => <fieldset key={layer} className="space-y-3 rounded-lg border border-zinc-800 p-4">
          <legend className="px-2 font-semibold">Capa {labels[layer]}</legend>
          {criteria[layer].map((row, index) => <div key={row.id} className="grid gap-3 border-b border-zinc-800 pb-4 sm:grid-cols-2 lg:grid-cols-4">
            <WorkspaceField label={`Código ${labels[layer]} ${index + 1}`} required maxLength={100} value={row.code} onChange={e => change(layer, row.id, 'code', e.target.value)} />
            <WorkspaceField label={`Descripción ${labels[layer]} ${index + 1}`} required maxLength={2000} value={row.description} onChange={e => change(layer, row.id, 'description', e.target.value)} />
            {layer === 'legal' ? <><WorkspaceField label={`Campo legal ${index + 1}`} value={row.field} placeholder="Usar código del criterio" onChange={e => change(layer, row.id, 'field', e.target.value)} />
              <div className="text-sm"><label htmlFor={`required-${row.id}`}>Obligatoriedad {index + 1}</label><select id={`required-${row.id}`} required className={inputClass} value={row.required} onChange={e => change(layer, row.id, 'required', e.target.value)}><option value="">Seleccionar</option><option value="true">Obligatorio</option><option value="false">Informativo</option></select></div></> :
              <WorkspaceField label={`Peso ${labels[layer]} ${index + 1}`} required type="number" min={0} step="any" value={row.weight} onChange={e => change(layer, row.id, 'weight', e.target.value)} />}
            <button type="button" onClick={() => { setDirty(true); setCriteria(previous => ({ ...previous, [layer]: previous[layer].filter(item => item.id !== row.id) })); }} className="self-end text-sm text-red-300">Quitar criterio {labels[layer]} {index + 1}</button>
          </div>)}
          {editable && <button type="button" onClick={() => { setDirty(true); setCriteria(previous => ({ ...previous, [layer]: [...previous[layer], emptyRow()] })); }} className={buttonClass}>Agregar criterio {labels[layer]}</button>}
        </fieldset>)}
        <p className="text-xs text-zinc-400">Los pesos se normalizan por capa. La firma, integridad y cumplimiento documental se comprueban además de los criterios legales.</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <WorkspaceField label="Mínimo técnico (0–100)" required type="number" min={0} max={100} step="any" value={minimumTech} onChange={e => setMinimumTech(e.target.value)} />
          <WorkspaceField label="Mínimo económico (0–100)" required type="number" min={0} max={100} step="any" value={minimumEcon} onChange={e => setMinimumEcon(e.target.value)} />
          <WorkspaceField label="Variación de mercado máxima (%) — opcional" type="number" min={0} max={100} step="any" value={marketMax} onChange={e => setMarketMax(e.target.value)} />
          <WorkspaceField label="Porcentaje del puntaje conservado al exceder la variación (%)" type="number" min={0} max={100} step="any" value={marketPenalty} onChange={e => setMarketPenalty(e.target.value)} />
        </div>
        {editable && <button type="submit" disabled={!dirty || busy} className={buttonClass}>{busy ? 'Guardando…' : 'Guardar bases y criterios'}</button>}
      </fieldset>
    </form>
    {!lic.bases_congeladas && early && approveRoles.includes(role) && <div className="space-y-2 border-t border-zinc-700 pt-4">
      <p className="text-sm text-zinc-400">Revisa la versión guardada. Congelarla fija las reglas para recibir y evaluar propuestas.</p>
      <button disabled={busy || dirty || !lic.bases || !lic.matriz_evaluacion} onClick={() => void run(() => megalodonClient.licitaciones.congelarBases(lic.id, lic.row_version))} className={buttonClass}>Congelar bases revisadas</button>
    </div>}
    {writeRoles.includes(role) && lic.transiciones_disponibles.length > 0 && <div className="space-y-2 border-t border-zinc-700 pt-4">
      <p className="text-sm text-zinc-400">Registra el avance después de completar la etapa correspondiente. La convocatoria y la junta oficiales se realizan fuera de Megalodon.</p>
      <label className="block text-sm">Siguiente etapa<select className={inputClass} value={next} disabled={busy || dirty} onChange={e => setNext(e.target.value)}><option value="">Seleccionar etapa</option>{lic.transiciones_disponibles.map(state => <option key={state} value={state}>{states[state]}</option>)}</select></label>
      <button disabled={busy || dirty || !next} onClick={() => void run(() => megalodonClient.licitaciones.transicionar(lic.id, { nuevo_estado: next }))} className={buttonClass}>Registrar cambio de etapa</button>
    </div>}
    <WorkspaceError message={error} />
  </div>;
}
