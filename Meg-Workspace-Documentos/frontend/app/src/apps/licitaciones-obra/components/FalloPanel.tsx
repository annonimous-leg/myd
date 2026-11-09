import { useEffect, useState } from 'react';
import { Award, Gavel, AlertTriangle } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';
import { useAuthStore } from '@/stores/useAuthStore';

export default function FalloPanel({ expedienteId }: { expedienteId: string }) {
  const [workspace, setWorkspace] = useState<any>(null); const [winner, setWinner] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const load = async () => { try { setWorkspace(await megalodonClient.licitacionesObra.workspace(expedienteId)); } catch (e) { setError((e as Error).message); } };
  useEffect(() => { void load(); }, [expedienteId]);
  const emit = async () => { setBusy(true); setError(''); try { await megalodonClient.licitacionesObra.fallo.emitir(expedienteId, { proposicion_id: winner }); await load(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  const lic = workspace?.licitacion;
  const role = useAuthStore(s => s.user?.role);
  const canEmit = ['EVALUACION','APERTURA'].includes(lic?.estado) &&
    ['admin', 'superadmin', 'revisor'].includes(role || '');
  return <div className="space-y-6"><header><h2 className="text-xl font-bold flex items-center gap-2"><Gavel className="w-5 h-5 text-rose-400" /> Fallo</h2><p className="text-sm text-zinc-500">Megalodon registra el resultado del procedimiento; no sustituye la emisión oficial de la convocante.</p></header>
    {error && <div className="rounded-lg border border-red-800 bg-red-950/30 p-3 text-sm text-red-300 flex gap-2"><AlertTriangle className="w-4 h-4" />{error}</div>}
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5 space-y-4"><div className="text-sm text-zinc-400">Estado de la licitación: <b className="text-zinc-200">{lic?.estado || '—'}</b></div><select aria-label="Proposición adjudicable" value={winner} onChange={e => setWinner(e.target.value)} className="w-full rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm"><option value="">Seleccionar proposición adjudicable</option>{(workspace?.proposiciones || []).filter((p: any) => p.estado === 'ADMITIDA').map((p: any) => <option key={p.id} value={p.id}>{p.proveedor?.razon_social || p.proveedor_id} · ${Number(p.monto).toLocaleString()}</option>)}</select><button disabled={busy || !winner || !canEmit} onClick={() => void emit()} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-rose-500/20 border border-rose-500/30 text-rose-300 disabled:opacity-40"><Award className="w-4 h-4" /> {busy ? 'Registrando…' : 'Registrar fallo'}</button></div>
  </div>;
}
