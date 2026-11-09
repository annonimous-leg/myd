import { useState } from 'react';
import type { FormEvent } from 'react';
import { megalodonClient } from '@/lib/api-client';
import type { EvaluationInputs, LicitacionWorkspace } from '@/lib/licitacion-types';
import { useAuthStore } from '@/stores/useAuthStore';
import { useWorkspace } from '../useWorkspace';
import { WorkspaceField, WorkspaceError, approveRoles, buttonClass, inputClass } from './WorkspaceFields';

type Layer = keyof EvaluationInputs;
type Draft = Record<string, Record<Layer, Record<string, string>>>;
const kinds = { legal: 'LEGAL', tecnico: 'TECNICA', economico: 'ECONOMICA' } as const;
const labels = { legal: 'Legal', tecnico: 'Técnica', economico: 'Económica' };
const legalFacts = ['firma_valida', 'integridad_valida', 'cumplimiento_documental'] as const;
function initialInputs(workspace: LicitacionWorkspace): Draft {
  const result: Draft = {};
  for (const prop of workspace.proposiciones) {
    result[prop.id] = { legal: {}, tecnico: {}, economico: {} };
    for (const layer of ['legal', 'tecnico', 'economico'] as const) {
      const latest = workspace.evaluaciones.filter(row => row.proposicion_id === prop.id && row.tipo === kinds[layer]).sort((a, b) => b.revision - a.revision)[0];
      for (const [code, spec] of Object.entries(workspace.licitacion.matriz_evaluacion?.[layer] || {})) {
        const field = layer === 'legal' ? spec.campo || code : code;
        const value = latest?.criterios?.datos?.[field];
        result[prop.id][layer][field] = value === undefined ? '' : String(value);
      }
    }
  }
  return result;
}

export default function EvaluacionPanel({ expedienteId }: { expedienteId: string }) {
  const { workspace, loading, error, reload } = useWorkspace(expedienteId);
  return <div className="space-y-5">
    <header className="flex justify-between gap-3"><div><h2 className="text-xl font-bold">Evaluación de proposiciones</h2><p className="text-sm text-zinc-400">Insumos por criterio, dictámenes por capa e historial de revisiones.</p></div><button className={buttonClass} disabled={loading} onClick={() => void reload()}>Actualizar evaluación</button></header>
    <WorkspaceError message={error} />
    {loading ? <p role="status">Cargando evaluación…</p> : workspace && <EvaluationForm key={`${workspace.licitacion.id}:${workspace.licitacion.row_version}`} workspace={workspace} expedienteId={expedienteId} onSaved={reload} />}
  </div>;
}

function EvaluationForm({ workspace, expedienteId, onSaved }: { workspace: LicitacionWorkspace; expedienteId: string; onSaved: () => Promise<void> }) {
  const [draft, setDraft] = useState(() => initialInputs(workspace));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const role = useAuthStore(s => s.user?.role) || '';
  const { licitacion: lic, proposiciones, evaluaciones } = workspace;
  const enabled = approveRoles.includes(role) && lic.bases_congeladas && ['RECEPCION_PROPUESTAS', 'APERTURA', 'EVALUACION'].includes(lic.estado) && proposiciones.length > 0;
  function update(id: string, layer: Layer, field: string, value: string) {
    setDraft(previous => ({ ...previous, [id]: { ...previous[id], [layer]: { ...previous[id][layer], [field]: value } } }));
  }
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const insumos: Record<string, EvaluationInputs> = {};
      for (const prop of proposiciones) {
        const source = draft[prop.id];
        insumos[prop.id] = { legal: Object.fromEntries(Object.entries(source.legal).filter(([field]) => !legalFacts.includes(field as typeof legalFacts[number])).map(([key, value]) => [key, value === 'true'])),
          tecnico: Object.fromEntries(Object.entries(source.tecnico).map(([key, value]) => [key, Number(value)])),
          economico: Object.fromEntries(Object.entries(source.economico).map(([key, value]) => [key, Number(value)])) };
      }
      await megalodonClient.licitacionesObra.evaluacion.evaluar(expedienteId, { revision_esperada: lic.row_version, insumos });
      await onSaved();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return <div className="space-y-5">
    <p className="text-sm text-zinc-400">{lic.folio} · {lic.estado} · Bases versión {lic.bases_version} · Revisión {lic.row_version}</p>
    {!enabled && <p className="text-sm text-amber-300">La emisión requiere permiso de aprobación, bases congeladas y proposiciones en recepción, apertura o evaluación.</p>}
    <form onSubmit={submit} className="space-y-4">
      <fieldset disabled={!enabled || busy} className="space-y-4">
        {proposiciones.map(prop => <section key={prop.id} className="rounded-xl border border-zinc-700 bg-zinc-900/40 p-5 space-y-4">
          <h3 className="font-semibold">{prop.proveedor.razon_social || prop.proveedor_id} · {prop.estado}</h3>
          <p className="text-sm text-zinc-400">{prop.verificacion_documental ? 'La revisión documental está registrada. Sus verificaciones se incorporan a la decisión.' : 'Revisión documental pendiente: una evaluación no puede acreditar la solvencia sin ella.'}</p>
          {(['legal', 'tecnico', 'economico'] as const).map(layer => <fieldset key={layer} className="space-y-3">
            <legend className="mb-2 font-medium">{labels[layer]}{layer !== 'legal' && ` · mínimo ${lic.matriz_evaluacion?.[layer === 'tecnico' ? 'minimo_tecnico' : 'minimo_economico'] ?? 'pendiente'}`}</legend>
            <div className="grid gap-3 sm:grid-cols-2">{Object.entries(lic.matriz_evaluacion?.[layer] || {}).map(([code, spec]) => {
              const field = layer === 'legal' ? spec.campo || code : code;
              const label = `${labels[layer]} · ${spec.descripcion || code} (${code})`;
              if (layer === 'legal' && legalFacts.includes(field as typeof legalFacts[number])) return <p key={code} className="text-sm text-zinc-400">{label}: {prop[field as typeof legalFacts[number]] === true ? 'Acreditado en revisión' : 'No acreditado'}</p>;
              return layer === 'legal' ? <label key={code} className="text-sm">{label} · {spec.requerido === false ? 'Informativo' : 'Obligatorio'}<select required className={inputClass} value={draft[prop.id].legal[field]} onChange={e => update(prop.id, layer, field, e.target.value)}><option value="">Seleccionar resultado</option><option value="true">Cumple</option><option value="false">No cumple</option></select></label> :
                <div key={code}><WorkspaceField label={label} required type="number" min={0} max={100} step="any" value={draft[prop.id][layer][field]} onChange={e => update(prop.id, layer, field, e.target.value)} /><span className="text-xs text-zinc-500">Puntaje 0–100 · Peso {spec.peso ?? spec.ponderacion}</span></div>;
            })}</div>
          </fieldset>)}
        </section>)}
        {enabled && <button type="submit" className={buttonClass}>{busy ? 'Evaluando…' : 'Evaluar con los insumos revisados'}</button>}
      </fieldset>
    </form>
    <WorkspaceError message={error} />
    <section className="space-y-3"><h3 className="font-semibold">Historial de dictámenes ({evaluaciones.length})</h3>
      {[...evaluaciones].sort((a, b) => b.revision - a.revision).map(row => <details key={row.id} className="rounded-lg border border-zinc-700 p-4">
        <summary className="cursor-pointer text-sm">{proposiciones.find(prop => prop.id === row.proposicion_id)?.proveedor.razon_social || row.proposicion_id} · {row.tipo} · Revisión {row.revision} · {row.resultado} · {row.puntaje ?? '—'} puntos</summary>
        <p className="mt-3 text-sm text-zinc-400">{row.dictamen}</p><dl className="mt-2 grid gap-2 sm:grid-cols-2">{Object.entries(row.criterios?.datos || {}).map(([key, value]) => <div key={key} className="text-sm"><dt className="text-zinc-500">{key}</dt><dd>{typeof value === 'boolean' ? value ? 'Cumple' : 'No cumple' : String(value)}</dd></div>)}</dl>
      </details>)}
    </section>
  </div>;
}
