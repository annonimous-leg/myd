import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { megalodonClient } from '@/lib/api-client';
import type { ProviderRecord } from '@/lib/licitacion-types';
import { WorkspaceField, WorkspaceError, inputClass, buttonClass } from './WorkspaceFields';

export default function ProposicionForm({ licitacionId, onSaved }: { licitacionId: string; onSaved: () => Promise<void> }) {
  const [providers, setProviders] = useState<ProviderRecord[]>([]);
  const [query, setQuery] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const [total, setTotal] = useState(0);
  const [providerId, setProviderId] = useState('');
  const [creating, setCreating] = useState(false);
  const [provider, setProvider] = useState<Pick<ProviderRecord, 'rfc' | 'razon_social' | 'tipo_persona'>>({ rfc: '', razon_social: '', tipo_persona: 'MORAL' });
  const [amount, setAmount] = useState('');
  const [days, setDays] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    setLoading(true); setError(''); setProviderId('');
    megalodonClient.proveedores.listar({ q: search, skip: page * 50, limit: 50 }).then(result => {
      if (active) { setProviders(result.items); setTotal(result.total); }
    }).catch(e => { if (active) { setProviders([]); setError((e as Error).message); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [search, page]);
  async function createProvider(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const row = await megalodonClient.proveedores.crear(provider);
      setProviders(previous => [row, ...previous]); setProviderId(row.id); setCreating(false); setTotal(previous => previous + 1);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      await megalodonClient.licitacionesObra.proposiciones.create(licitacionId, { proveedor_id: providerId, monto: Number(amount), plazo_dias: Number(days) });
      setAmount(''); setDays(''); setProviderId(''); await onSaved();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return <section className="space-y-4 rounded-xl border border-zinc-700 bg-zinc-900/40 p-5">
    <h3 className="font-semibold text-lg">Registrar proposición</h3>
    <p className="text-sm text-zinc-400">Registra los términos presentados por el licitante. Su admisión requiere revisión documental y evaluación posteriores.</p>
    <form onSubmit={e => { e.preventDefault(); setSearch(query.trim()); setPage(0); }} className="flex items-end gap-3">
      <div className="flex-1"><WorkspaceField label="Buscar proveedor por RFC o razón social" value={query} maxLength={200} disabled={busy || loading} onChange={e => setQuery(e.target.value)} /></div>
      <button disabled={busy || loading} className={buttonClass}>Buscar proveedor</button>
    </form>
    <button type="button" disabled={busy || loading} onClick={() => setCreating(!creating)} className={buttonClass}>{creating ? 'Cerrar alta de proveedor' : 'Dar de alta proveedor'}</button>
    {creating && <form onSubmit={createProvider} className="space-y-3 border border-zinc-700 rounded-lg p-4">
      <fieldset disabled={busy} className="grid gap-3 sm:grid-cols-2">
        <WorkspaceField label="RFC del proveedor" required minLength={12} maxLength={13} pattern="[A-ZÑ&]{3,4}[0-9]{6}[A-Z0-9]{3}" value={provider.rfc} onChange={e => setProvider({ ...provider, rfc: e.target.value.toUpperCase() })} />
        <WorkspaceField label="Razón social del proveedor" required minLength={2} maxLength={500} value={provider.razon_social} onChange={e => setProvider({ ...provider, razon_social: e.target.value })} />
        <label className="text-sm">Tipo de persona<select className={inputClass} value={provider.tipo_persona} onChange={e => setProvider({ ...provider, tipo_persona: e.target.value as ProviderRecord['tipo_persona'] })}><option value="MORAL">Persona moral</option><option value="FISICA">Persona física</option><option value="CONSORCIO">Consorcio</option></select></label>
        <button className={`${buttonClass} self-end`}>Guardar proveedor</button>
      </fieldset>
      <p className="text-xs text-zinc-400">El alta identifica al proveedor dentro de tu organización; no acredita su situación fiscal ni legal.</p>
    </form>}
    <form onSubmit={submit} className="space-y-4">
      <fieldset disabled={busy || loading} className="space-y-4">
        <label className="block text-sm">Proveedor de la proposición<select aria-label="Proveedor de la proposición" required value={providerId} onChange={e => setProviderId(e.target.value)} className={inputClass}><option value="">Seleccionar proveedor</option>{providers.map(row => <option key={row.id} value={row.id} disabled={row.estado !== 'ACTIVO'}>{row.razon_social} · {row.rfc} · {row.estado}</option>)}</select></label>
        <div className="flex items-center gap-3 text-sm text-zinc-400"><span>{total} proveedores encontrados</span><button type="button" disabled={page === 0} onClick={() => setPage(page - 1)}>Página anterior</button><button type="button" disabled={(page + 1) * 50 >= total} onClick={() => setPage(page + 1)}>Página siguiente</button></div>
        <div className="grid gap-4 sm:grid-cols-2"><WorkspaceField label="Monto de la proposición (MXN)" required type="number" min={0} step="0.01" value={amount} onChange={e => setAmount(e.target.value)} /><WorkspaceField label="Plazo de la proposición (días)" required type="number" min={1} step={1} value={days} onChange={e => setDays(e.target.value)} /></div>
        <button type="submit" disabled={!providerId || busy || creating} className={buttonClass}>{busy ? 'Registrando…' : 'Registrar proposición recibida'}</button>
      </fieldset>
    </form>
    {loading && <p role="status" className="text-sm text-zinc-400">Cargando proveedores…</p>}
    <WorkspaceError message={error} />
  </section>;
}
