import { useEffect, useState } from 'react';
import { Shield, CheckCircle2, AlertTriangle } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';
import { useAuthStore } from '@/stores/useAuthStore';
import { approveRoles } from './WorkspaceFields';

export default function FiniquitoPanel({ expedienteId }: { expedienteId: string }) {
  const role = useAuthStore(s => s.user?.role) || '';
  const canApprove = approveRoles.includes(role);
  const [workspace, setWorkspace] = useState<any>(null); const [date, setDate] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const load = async () => { try { setWorkspace(await megalodonClient.licitacionesObra.workspace(expedienteId)); } catch (e) { setError((e as Error).message); } };
  useEffect(() => { void load(); }, [expedienteId]);
  const finish = async () => { setBusy(true); setError(''); try { await megalodonClient.licitacionesObra.finiquito.generar(expedienteId, { fecha_finiquito: date }); await load(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  const terminate = async () => { setBusy(true); setError(''); try { await megalodonClient.licitacionesObra.finiquito.terminarContrato(expedienteId); await load(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  const c = workspace?.contrato;
  return <div className="space-y-6"><header><h2 className="text-xl font-bold flex items-center gap-2"><Shield className="w-5 h-5 text-teal-400" /> Finiquito</h2><p className="text-sm text-zinc-500">El cierre sólo se permite cuando el contrato está TERMINADO o RESCINDIDO.</p></header>{error && <div className="rounded-lg border border-red-800 bg-red-950/30 p-3 text-sm text-red-300 flex gap-2"><AlertTriangle className="w-4 h-4"/>{error}</div>}{!c ? <div className="rounded-xl border border-zinc-800 p-6 text-sm text-zinc-500">No existe contrato.</div> : <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5 space-y-4"><div className="grid md:grid-cols-3 gap-3"><Metric l="Contrato" v={c.numero_contrato}/><Metric l="Estado" v={c.estado}/><Metric l="Monto" v={`$${Number(c.monto_total).toLocaleString()}`}/></div><div className="grid md:grid-cols-2 gap-3"><Field label="Fecha de finiquito" value={date} onChange={setDate}/><div className="flex flex-wrap gap-2"><button disabled={busy || !canApprove || c.estado !== 'VIGENTE'} onClick={() => void terminate()} className="flex items-center justify-center gap-2 rounded-lg bg-amber-500/20 border border-amber-500/30 text-amber-300 disabled:opacity-40"><CheckCircle2 className="w-4 h-4"/> Marcar terminado</button><button disabled={busy || !canApprove || !date || !['TERMINADO','RESCINDIDO'].includes(c.estado)} onClick={() => void finish()} className="flex items-center justify-center gap-2 rounded-lg bg-teal-500/20 border border-teal-500/30 text-teal-300 disabled:opacity-40"><CheckCircle2 className="w-4 h-4"/> Cerrar finiquito</button></div></div>{c.fecha_finiquito && <div className="rounded-lg border border-emerald-800 bg-emerald-950/20 p-3 text-sm text-emerald-300">Finiquito registrado: {c.fecha_finiquito} · ${Number(c.monto_finiquito || 0).toLocaleString()}</div>}</div>}
  </div>;
}
function Field({label,value,onChange}:{label:string;value:string;onChange:(v:string)=>void}){return <div><label className="text-xs text-zinc-500">{label}</label><input aria-label={label} type="date" value={value} onChange={e=>onChange(e.target.value)} className="mt-1 w-full rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm"/></div>}
function Metric({l,v}:{l:string;v:string}){return <div className="rounded-lg border border-zinc-800 p-3"><div className="text-xs text-zinc-500">{l}</div><div className="font-semibold text-zinc-200 mt-1">{v}</div></div>}
