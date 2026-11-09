import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { megalodonClient } from '@/lib/api-client';

interface EvidenceDocument { id: string; nombre: string; tipo_documental: string; row_version: number }
interface Props {
  expedienteId: string;
  licitacionId: string;
  proposicionId: string;
  onSaved: () => Promise<void>;
  onCancel: () => void;
}

export default function RevisionDocumentalForm({ expedienteId, licitacionId, proposicionId, onSaved, onCancel }: Props) {
  const [documents, setDocuments] = useState<EvidenceDocument[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [signature, setSignature] = useState('');
  const [compliance, setCompliance] = useState('');
  const [opinion, setOpinion] = useState('');
  const [loading, setLoading] = useState(true);
  const [more, setMore] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  async function upload() {
    if (!file) return;
    setUploading(true); setError('');
    try {
      const doc = await megalodonClient.expedientes.subirDocumento(expedienteId, file, 'SOPORTE_REVISION');
      const rows = await megalodonClient.expedientes.listarDocumentos(expedienteId);
      setDocuments(rows); setMore(rows.length === 100);
      setSelected(previous => [...new Set([...previous, doc.id])]); setFile(null);
      if (fileInput.current) fileInput.current.value = '';
    } catch (e) { setError((e as Error).message); } finally { setUploading(false); }
  }

  useEffect(() => {
    let active = true;
    megalodonClient.expedientes.listarDocumentos(expedienteId).then(rows => {
      if (active) { setDocuments(rows); setMore(rows.length === 100); }
    }).catch(e => { if (active) setError((e as Error).message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [expedienteId]);

  async function loadMore() {
    setLoading(true); setError('');
    try {
      const rows = await megalodonClient.expedientes.listarDocumentos(expedienteId, documents.length);
      setDocuments(previous => [...previous, ...rows]); setMore(rows.length === 100);
    } catch (e) { setError((e as Error).message); }
    finally { setLoading(false); }
  }

  async function submit(event: FormEvent) {
    event.preventDefault(); setSaving(true); setError('');
    try {
      await megalodonClient.licitacionesObra.proposiciones.revisarDocumentacion(licitacionId, proposicionId, {
        documentos_soporte: selected, firma_valida: signature === 'si',
        cumplimiento_documental: compliance === 'si', dictamen: opinion.trim(),
      });
      await onSaved();
    } catch (e) { setError((e as Error).message); }
    finally { setSaving(false); }
  }

  const complete = selected.length > 0 && selected.length <= 100 && signature && compliance && opinion.trim().length >= 20;
  return <form onSubmit={submit} className="mt-4 space-y-4 border-t border-zinc-700 pt-4">
    <p className="text-sm text-zinc-400">La revisión de firma y requisitos queda atribuida a tu usuario. Adjunta el soporte de tus conclusiones; la integridad de los archivos se comprobará al guardar.</p>
    <div className="space-y-2">
      <label className="block text-sm text-zinc-300">Adjuntar documento de soporte<input ref={fileInput} type="file" disabled={saving || uploading} onChange={e => setFile(e.target.files?.[0] || null)} className="mt-1 block w-full text-sm" /></label>
      <button type="button" disabled={!file || uploading || saving || selected.length >= 100} onClick={() => void upload()} className="rounded-lg border border-zinc-700 px-3 py-2 text-sm disabled:opacity-40">{uploading ? 'Adjuntando…' : 'Guardar documento de soporte'}</button>
    </div>
    <fieldset disabled={saving} className="space-y-2">
      <legend className="text-sm font-medium text-zinc-200">Documentos que respaldan la revisión ({selected.length}/100)</legend>
      <div className="max-h-48 overflow-auto rounded-lg border border-zinc-700 p-3 space-y-2">
        {documents.map(doc => <label key={doc.id} className="flex gap-2 text-sm text-zinc-300">
          <input type="checkbox" checked={selected.includes(doc.id)} disabled={!selected.includes(doc.id) && selected.length >= 100}
            onChange={e => setSelected(previous => e.target.checked ? [...previous, doc.id] : previous.filter(id => id !== doc.id))} />
          <span>{doc.nombre} <span className="text-zinc-500">· {doc.tipo_documental}</span></span>
        </label>)}
        {!loading && !documents.length && <p className="text-sm text-zinc-400">Carga primero los informes y documentos de soporte en este expediente.</p>}
        {loading && <p role="status" className="text-sm text-zinc-400">Cargando documentos…</p>}
      </div>
      {more && <button type="button" disabled={loading} onClick={() => void loadMore()} className="text-sm text-amber-300 disabled:opacity-40">Cargar más documentos</button>}
    </fieldset>
    <div className="grid gap-4 sm:grid-cols-2">
      <label className="text-sm text-zinc-300">¿La firma está acreditada por el soporte revisado?
        <select required value={signature} disabled={saving} onChange={e => setSignature(e.target.value)} className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-900 p-2">
          <option value="">Selecciona un dictamen</option><option value="si">Sí, acreditada</option><option value="no">No acreditada</option>
        </select>
      </label>
      <label className="text-sm text-zinc-300">¿Cumple los requisitos documentales de las bases?
        <select required value={compliance} disabled={saving} onChange={e => setCompliance(e.target.value)} className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-900 p-2">
          <option value="">Selecciona un dictamen</option><option value="si">Sí, cumple</option><option value="no">No cumple</option>
        </select>
      </label>
    </div>
    <label className="block text-sm text-zinc-300">Dictamen y referencias de la revisión
      <textarea required minLength={20} maxLength={10000} value={opinion} disabled={saving} onChange={e => setOpinion(e.target.value)}
        rows={4} className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-900 p-2" />
    </label>
    {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
    <div className="flex gap-3">
      <button type="submit" disabled={saving || uploading || !complete} className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-zinc-950 disabled:opacity-40">{saving ? 'Guardando revisión…' : 'Registrar revisión'}</button>
      <button type="button" disabled={saving || uploading} onClick={onCancel} className="rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-300">Cancelar</button>
    </div>
  </form>;
}
