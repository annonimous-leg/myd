import { useEffect, useState } from 'react';
import { BookOpen, Clock, FileText, Upload, ShieldCheck, AlertCircle } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';
import BasesPanel from './BasesPanel';

export default function ConvocatoriaPanel({ expedienteId }: { expedienteId: string }) {
  const [tenders, setTenders] = useState<any[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [sourceRole, setSourceRole] = useState('CONVOCATORIA');
  const [candidates, setCandidates] = useState<Record<string, any[]>>({});

  const refresh = async () => {
    try {
      const rows = await megalodonClient.procurement.list({ expediente_id: expedienteId });
      setTenders(rows);
      const next: Record<string, any[]> = {};
      for (const tender of rows) { try { next[tender.id] = await megalodonClient.procurement.requirementCandidates(tender.id); } catch { next[tender.id] = []; } }
      setCandidates(next);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  useEffect(() => { void refresh(); }, [expedienteId]);

  const ingest = async (id: string) => {
    if (!files.length) return;
    setBusy(true); setError('');
    try {
      await megalodonClient.procurement.ingest(id, files, sourceRole);
      setFiles([]);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5 max-w-6xl mx-auto">
      <BasesPanel expedienteId={expedienteId} />
      <div className="flex items-center gap-3">
        <BookOpen className="w-5 h-5 text-emerald-400" />
        <div>
          <h2 className="text-xl font-bold text-zinc-100">Convocatoria y fuentes</h2>
          <p className="text-sm text-zinc-500 mt-1">La convocatoria se ingresa como evidencia versionada; la publicación oficial corresponde al portal de la entidad convocante.</p>
        </div>
      </div>

      {!tenders.length ? (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-6 text-sm text-zinc-400">
          <AlertCircle className="w-8 h-8 text-zinc-600 mb-3" />
          Para procesar fuentes y requisitos extraídos, vincula el expediente en Automatización. Las bases y criterios de esta licitación se gestionan arriba.
        </div>
      ) : tenders.map((tender) => (
        <section key={tender.id} className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5 space-y-4">
          <div className="grid md:grid-cols-4 gap-3">
            <Metric label="Identificador" value={tender.identifier} icon={<FileText className="w-4 h-4" />} />
            <Metric label="Estado" value={tender.state} icon={<ShieldCheck className="w-4 h-4" />} />
            <Metric label="Revisión" value={String(tender.revision ?? tender.current_revision ?? 1)} icon={<Clock className="w-4 h-4" />} />
            <Metric label="Jurisdicción" value={tender.jurisdiction_code || 'Pendiente'} icon={<BookOpen className="w-4 h-4" />} />
          </div>
          <div className="border-t border-zinc-800 pt-4 space-y-3">
            <div className="text-sm font-semibold text-zinc-200">Ingresar convocatoria y fuentes oficiales</div>
            <select value={sourceRole} onChange={e => setSourceRole(e.target.value)} className="rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm">
              <option value="CONVOCATORIA">Convocatoria / bases</option>
              <option value="JUNTA_ACLARACIONES">Acta / resultados de junta de aclaraciones</option>
              <option value="MODIFICACION">Modificación / circular / addendum</option>
              <option value="ANEXO">Anexo oficial</option>
            </select>
            <input type="file" multiple onChange={e => setFiles(Array.from(e.target.files || []))} className="w-full text-sm" />
            <button disabled={busy || !files.length} onClick={() => void ingest(tender.id)} className="flex items-center gap-2 px-3 py-2 rounded-lg border border-zinc-700 hover:bg-zinc-800 disabled:opacity-40 text-sm">
              <Upload className="w-4 h-4" /> Ingresar fuentes verificadas
            </button>
          </div>
          {(candidates[tender.id] || []).length > 0 && (
            <div className="border-t border-zinc-800 pt-4 space-y-3">
              <div className="text-sm font-semibold text-zinc-200">Requisitos extraídos — revisión humana obligatoria</div>
              <div className="space-y-2">
                {(candidates[tender.id] || []).filter((c: any) => c.status !== 'CONFIRMED').map((c: any) => (
                  <label key={c.code} className="flex items-start gap-3 rounded-lg border border-zinc-800 p-3 text-sm">
                    <input type="checkbox" defaultChecked={false} data-requirement-code={c.code} className="mt-1" />
                    <span className="flex-1"><b>{c.code}</b> — {c.description}<span className="block text-xs text-zinc-500 mt-1">Fuente: {c.source_role || 'fuente oficial'} · línea {c.source_reference?.line_start || 'N/D'} · la obligatoriedad debe ser confirmada por el usuario</span><select data-mandatory-code={c.code} defaultValue="" className="mt-2 rounded bg-zinc-950 border border-zinc-800 px-2 py-1 text-xs"><option value="">Obligatoriedad: confirmar</option><option value="true">Sí, obligatorio</option><option value="false">No, no obligatorio</option></select></span>
                  </label>
                ))}
              </div>
              <button type="button" disabled={busy} onClick={async (ev) => {
                const root = (ev.currentTarget.parentElement);
                const selected = Array.from(root?.querySelectorAll<HTMLInputElement>('input[data-requirement-code]:checked') || []).map(input => { const code = input.dataset.requirementCode!; const row = (candidates[tender.id] || []).find((x: any) => x.code === code); const select = root?.querySelector<HTMLSelectElement>(`select[data-mandatory-code="${CSS.escape(code)}"]`); if (!row || !select?.value) return null; return { ...row, mandatory: select.value === 'true' }; }).filter(Boolean);
                if (!selected.length) return;
                try { setBusy(true); await megalodonClient.procurement.confirmRequirementCandidates(tender.id, selected); await refresh(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
              }} className="px-3 py-2 rounded-lg border border-emerald-700/50 text-emerald-300 text-sm disabled:opacity-40">Confirmar seleccionados</button>
            </div>
          )}
        </section>
      ))}

      {error && <div className="rounded-lg border border-red-800 bg-red-950/30 p-3 text-sm text-red-300">{error}</div>}
    </div>
  );
}

function Metric({ label, value, icon }: { label: string; value: string; icon: React.ReactNode }) {
  return <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4"><div className="flex items-center gap-2 text-xs text-zinc-500">{icon}{label}</div><div className="mt-1 text-sm font-semibold text-zinc-200 truncate">{value}</div></div>;
}
