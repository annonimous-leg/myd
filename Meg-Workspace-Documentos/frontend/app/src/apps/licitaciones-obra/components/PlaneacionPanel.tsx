import { useEffect, useState, useId } from 'react';
import { CheckCircle2, FileText, Save, AlertTriangle } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';
import { MegalodonApiError } from '@/lib/megalodon-client';

const PROCEDIMIENTOS = [
  ['LICITACION_PUBLICA', 'Licitación pública'],
  ['INVITACION_A_CUANDO_MENOS_TRES', 'Invitación a cuando menos tres'],
  ['ADJUDICACION_DIRECTA', 'Adjudicación directa'],
  ['OBRA_PUBLICA', 'Obra pública'],
] as const;

export default function PlaneacionPanel({ expedienteId }: { expedienteId: string }) {
  const [form, setForm] = useState({ jurisdiction_code: '', folio: '', tipo_procedimiento: 'LICITACION_PUBLICA', objeto: '', monto_estimado: '', plazo_dias: '', fecha_convocatoria: '', tipo_obra: '', fuente_financiamiento: '' });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let active = true;
    megalodonClient.licitacionesObra.workspace(expedienteId).then((w) => {
      if (!active) return;
      const p = w.licitacion?.planeacion || {};
      setForm({
        jurisdiction_code: w.licitacion?.jurisdiction_code || '',
        folio: w.licitacion?.folio || '',
        tipo_procedimiento: w.licitacion?.tipo_procedimiento || 'LICITACION_PUBLICA',
        objeto: w.licitacion?.objeto || '',
        monto_estimado: w.licitacion?.monto_estimado ? String(w.licitacion.monto_estimado) : '',
        plazo_dias: w.licitacion?.plazo_dias ? String(w.licitacion.plazo_dias) : '',
        fecha_convocatoria: w.licitacion?.fecha_convocatoria || '',
        tipo_obra: p.tipo_obra || '',
        fuente_financiamiento: p.fuente_financiamiento || '',
      });
    }).catch((e) => { if (active && !(e instanceof MegalodonApiError && e.status === 404)) setError((e as Error).message); }).finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [expedienteId]);

  const save = async () => {
    setSaving(true); setSaved(false); setError('');
    try {
      await megalodonClient.licitacionesObra.planeacion.create({
        expediente_id: expedienteId,
        ...form,
        monto_estimado: form.monto_estimado ? Number(form.monto_estimado) : null,
        plazo_dias: form.plazo_dias ? Number(form.plazo_dias) : null,
      });
      setSaved(true);
    } catch (e) { setError((e as Error).message); }
    finally { setSaving(false); }
  };

  if (loading) return <div className="p-6 text-sm text-zinc-400">Cargando planeación...</div>;

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <div><h2 className="text-xl font-bold flex items-center gap-2"><FileText className="w-5 h-5 text-blue-400" /> Planeación pre-licitación</h2><p className="text-sm text-zinc-500">La selección se persiste en la licitación real. Los umbrales jurídicos se resuelven en backend.</p></div>
        <button onClick={() => void save()} disabled={saving || !form.folio || !form.objeto || !form.jurisdiction_code.trim()} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-500/20 border border-blue-500/30 text-blue-300 disabled:opacity-40"><Save className="w-4 h-4" /> {saving ? 'Guardando…' : saved ? 'Guardado' : 'Guardar'}</button>
      </header>
      <div className="grid md:grid-cols-2 gap-4">
        <Field label="Dependencia convocante (código del expediente)" value={form.jurisdiction_code} onChange={(v) => setForm({ ...form, jurisdiction_code: v })} />
        <Field label="Folio" value={form.folio} onChange={(v) => setForm({ ...form, folio: v })} />
        <div><label className="text-xs text-zinc-500">Procedimiento</label><select aria-label="Procedimiento" value={form.tipo_procedimiento} onChange={(e) => setForm({ ...form, tipo_procedimiento: e.target.value })} className="mt-1 w-full rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm">{PROCEDIMIENTOS.map(([v,l]) => <option key={v} value={v}>{l}</option>)}</select></div>
        <div className="md:col-span-2"><label className="text-xs text-zinc-500">Objeto</label><textarea aria-label="Objeto" value={form.objeto} onChange={(e) => setForm({ ...form, objeto: e.target.value })} className="mt-1 w-full min-h-24 rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm" /></div>
        <Field label="Monto estimado" value={form.monto_estimado} onChange={(v) => setForm({ ...form, monto_estimado: v })} type="number" />
        <Field label="Plazo (días)" value={form.plazo_dias} onChange={(v) => setForm({ ...form, plazo_dias: v })} type="number" />
        <Field label="Fecha de convocatoria" value={form.fecha_convocatoria} onChange={(v) => setForm({ ...form, fecha_convocatoria: v })} type="date" />
        <Field label="Tipo de obra" value={form.tipo_obra} onChange={(v) => setForm({ ...form, tipo_obra: v })} />
        <Field label="Fuente de financiamiento" value={form.fuente_financiamiento} onChange={(v) => setForm({ ...form, fuente_financiamiento: v })} />
      </div>
      {error && <div className="rounded-lg border border-red-800 bg-red-950/30 p-3 text-sm text-red-300 flex items-center gap-2"><AlertTriangle className="w-4 h-4" />{error}</div>}
      {saved && <div className="rounded-lg border border-emerald-800 bg-emerald-950/20 p-3 text-sm text-emerald-300 flex items-center gap-2"><CheckCircle2 className="w-4 h-4" />Planeación guardada en la licitación del expediente.</div>}
    </div>
  );
}

function Field({ label, value, onChange, type = 'text' }: { label: string; value: string; onChange: (v: string) => void; type?: string }) {
  const id = useId();
  return <div><label htmlFor={id} className="text-xs text-zinc-500">{label}</label><input id={id} type={type} value={value} onChange={(e) => onChange(e.target.value)} className="mt-1 w-full rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm" /></div>;
}
