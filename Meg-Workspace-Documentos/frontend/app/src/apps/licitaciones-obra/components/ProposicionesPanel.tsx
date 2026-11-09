import { useState } from 'react';
import { useAuthStore } from '@/stores/useAuthStore';
import { useWorkspace } from '../useWorkspace';
import RevisionDocumentalForm from './RevisionDocumentalForm';
import ProposicionForm from './ProposicionForm';
import { WorkspaceError, approveRoles, writeRoles, buttonClass } from './WorkspaceFields';

export default function ProposicionesPanel({ expedienteId }: { expedienteId: string }) {
  const { workspace, loading, error, reload } = useWorkspace(expedienteId);
  const [reviewing, setReviewing] = useState<string | null>(null);
  const role = useAuthStore(s => s.user?.role) || '';
  const lic = workspace?.licitacion;
  const canReview = !loading && lic?.bases_congeladas && approveRoles.includes(role) && ['RECEPCION_PROPUESTAS', 'APERTURA', 'EVALUACION'].includes(lic.estado);
  const canRegister = !loading && lic?.bases_congeladas && writeRoles.includes(role) && ['JUNTA_ACLARACIONES', 'RECEPCION_PROPUESTAS'].includes(lic.estado);
  return <div className="space-y-5">
    <header className="flex justify-between gap-3"><div><h2 className="text-xl font-bold">Proposiciones</h2><p className="text-sm text-zinc-400">{lic?.folio || '—'} · {lic?.estado || '—'}</p></div><button disabled={loading} onClick={() => void reload()} className={buttonClass}>Actualizar proposiciones</button></header>
    <WorkspaceError message={error} />
    {loading && <p role="status">Cargando proposiciones…</p>}
    {canRegister && lic && <ProposicionForm key={lic.id} licitacionId={lic.id} onSaved={reload} />}
    {!loading && lic && !canRegister && ['PLANEACION', 'INVESTIGACION_MERCADO', 'SELECCION_PROCEDIMIENTO', 'CONVOCATORIA'].includes(lic.estado) && <p className="text-sm text-amber-300">Completa y congela las bases; registra el avance de etapas en Convocatoria para habilitar la recepción.</p>}
    {!loading && workspace?.proposiciones.length === 0 && <p className="text-zinc-400">No existen proposiciones registradas para la licitación.</p>}
    {!loading && workspace?.proposiciones.map(prop => <article key={prop.id} className="rounded-xl border border-zinc-700 bg-zinc-900/40 p-5 space-y-3">
      <header className="flex flex-wrap justify-between gap-3"><div><h3 className="font-semibold">{prop.proveedor.razon_social || prop.proveedor_id}</h3><p className="text-sm text-zinc-400">{prop.proveedor.rfc}</p></div><p>{Number(prop.monto).toLocaleString('es-MX', { style: 'currency', currency: 'MXN' })} · {prop.plazo_dias} días · <strong>{prop.estado}</strong></p></header>
      <p className="text-sm text-zinc-400">{prop.verificacion_documental ? `Revisión documental registrada · ${new Date(prop.verificacion_documental.fecha).toLocaleString()}` : 'Revisión documental pendiente'}</p>
      {canReview && reviewing !== prop.id && <button onClick={() => setReviewing(prop.id)} className={buttonClass}>Revisar documentación</button>}
      {canReview && reviewing === prop.id && <RevisionDocumentalForm key={`${expedienteId}:${prop.id}`} expedienteId={expedienteId} licitacionId={workspace.licitacion.id} proposicionId={prop.id} onCancel={() => setReviewing(null)} onSaved={async () => { await reload(); setReviewing(null); }} />}
    </article>)}
  </div>;
}
