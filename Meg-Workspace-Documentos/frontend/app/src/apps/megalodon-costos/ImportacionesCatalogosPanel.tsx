import { useEffect, useState } from 'react';
import { megalodonClient } from '@/lib/api-client';
import type { CatalogoImportacionOut, CatalogoRegistroOut } from '@/lib/megalodon-client';
import { useAuthStore } from '@/stores/useAuthStore';
import { permisosBim } from '@/lib/bim-permissions';

const className = 'block w-full rounded border border-[#2A2A3E] bg-[#12121A] p-2';
const message = (e: unknown) => e instanceof Error ? e.message : 'No se pudo completar la operación';
const reasons: Record<string, string> = {
  PDF_ORIGINAL_NO_COTEJADO: 'Falta cotejar el PDF original', INCIDENCIA_O_COMPONENTE_PENDIENTE: 'Hay una incidencia o componente pendiente',
  REVISION_PENDIENTE: 'Requiere revisión de la extracción', IVA_NO_DOCUMENTADO: 'Falta documentar el tratamiento de IVA',
  UNIDAD_NO_INTERPRETABLE: 'La unidad requiere cotejo', DESGLOSE_NO_CIERRA: 'El desglose no reproduce el precio publicado',
  ARITMETICA_COMPONENTE_NO_REPRODUCIBLE: 'Un componente no reproduce el importe de la fuente',
  TIPO_AMBIGUO_REQUIERE_REVISION: 'Hay que distinguir si es insumo o concepto', NO_USAR_PARA_COSTEAR: 'Referencia sin precio habilitado',
};
const pendingPageSize = 200;
// CI-only fixtures must never be presented as commercial research. Preserve
// authentic source labels, originals and catalog identities for all other IDs.
const sourceDisplayName = (id: string, original: string | undefined, commercial: string | undefined) =>
  id === 'SYNTHETIC' && (!original || original === 'Synthetic test source')
    ? `Prueba aislada de CI${original ? ' · ' + original : ''}`
    : (commercial || original || id);
const recordTypes: Record<string, string> = {
  partida_catalogo: 'Concepto o insumo', modelo_parametrico: 'Modelo paramétrico',
  factor_geografico: 'Factor geográfico', componente_partida: 'Componente de concepto',
  componente_modelo: 'Componente de modelo', desglose_modelo: 'Desglose de modelo',
};

async function loadRecords(batchId: string, table: string, state: string) {
  const items: CatalogoRegistroOut[] = [];
  let total = 0;
  do {
    const page = await megalodonClient.catalogoImportaciones.registros(batchId, table, state, items.length, 500);
    total = page.total;
    if (!page.items.length && items.length < total) throw new Error('No se pudo completar la consulta del catálogo');
    items.push(...page.items);
  } while (items.length < total);
  return items;
}

function Edition({batch, canWrite}: {batch: CatalogoImportacionOut; canWrite: boolean}) {
  const [models, setModels] = useState<CatalogoRegistroOut[]>([]);
  const [factors, setFactors] = useState<CatalogoRegistroOut[]>([]);
  const [pending, setPending] = useState<{total: number; items: CatalogoRegistroOut[]}>({total: 0, items: []});
  const [skip, setSkip] = useState(0);
  const [pendingLoading, setPendingLoading] = useState(false);
  const [pendingError, setPendingError] = useState('');
  const [pendingReload, setPendingReload] = useState(0);
  const [modelId, setModelId] = useState('');
  const [factorId, setFactorId] = useState('');
  const [quantity, setQuantity] = useState('');
  const [adjustment, setAdjustment] = useState('1');
  const [reference, setReference] = useState('');
  const [result, setResult] = useState<{id: string; monto: string} | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    setError('');
    void Promise.all([
      loadRecords(batch.id, 'modelo_parametrico', 'PARAMETRICO'),
      loadRecords(batch.id, 'factor_geografico', 'FACTOR'),
    ]).then(([m, f]) => { if (active) { setModels(m); setFactors(f); } })
      .catch(e => { if (active) setError(message(e)); });
    return () => { active = false; };
  }, [batch.id]);
  useEffect(() => {
    let active = true;
    setPendingLoading(true);
    setPendingError('');
    setPending({total: 0, items: []});
    void megalodonClient.catalogoImportaciones.registros(batch.id, '*', 'CUARENTENA', skip, pendingPageSize)
      .then(data => { if (active) setPending(data); })
      .catch(e => { if (active) setPendingError(message(e)); })
      .finally(() => { if (active) setPendingLoading(false); });
    return () => { active = false; };
  }, [batch.id, skip, pendingReload]);
  const model = models.find(m => m.id === modelId);
  const scope = model ? (JSON.parse(model.original.aplicabilidad || '{}') as {fic_especialidad?: string}).fic_especialidad : undefined;
  const compatibleFactors = factors.filter(f => !scope || (f.fuente_id === model?.fuente_id &&
    (JSON.parse(f.original.instrucciones || '{}') as {fic_especialidad?: string}).fic_especialidad === scope));
  async function estimate() {
    setBusy(true); setResult(null); setError('');
    try { setResult(await megalodonClient.catalogoImportaciones.estimar({modelo_registro_id: modelId,
      factor_registro_id: factorId, cantidad: quantity, ajuste_proyecto: adjustment, justificacion: reference})); }
    catch (e) { setError(message(e)); } finally { setBusy(false); }
  }
  return <div className="mt-3 space-y-3">
    <p>{batch.resumen.estados.COTIZABLE || 0} conceptos habilitados · {batch.resumen.estados.INSUMO || 0} insumos · {batch.resumen.estados.PARAMETRICO || 0} modelos paramétricos habilitados.</p>
    <details><summary>Revisiones pendientes ({batch.resumen.estados.CUARENTENA || 0} registros)</summary>
      <p className="my-2">Los registros pendientes conservan su precio y evidencia. No se ofrecen como conceptos aprobables.</p>
      {pendingLoading && <p role="status">Cargando revisiones pendientes…</p>}
      {pendingError && <p role="alert">{pendingError} <button onClick={() => setPendingReload(n => n + 1)}>Reintentar consulta</button></p>}
      {!pendingLoading && !pendingError && !pending.total && <p>No hay registros pendientes en esta consulta.</p>}
      <ul className="max-h-60 overflow-auto space-y-2">{pending.items.map(r => <li key={r.id}>
        <strong>{r.original.codigo || r.entidad_id}</strong> · {recordTypes[r.tabla] || r.tabla}<br />
        {r.original.descripcion || r.original.nombre || r.original.localidad_base || r.original.titulo}<br />
        {r.motivos.map(m => reasons[m] || m).join(' · ')}
        <details><summary>Ver datos de la fuente</summary>
          <p>{sourceDisplayName(r.fuente_id, undefined, batch.resumen.fuentes_visibles?.[r.fuente_id])} · Identidad de fuente {r.fuente_id} · Página: {r.original.pagina_inicio || r.original.pagina_pdf || 'Sin página indicada'}</p>
          <p>Valor publicado: {r.original.costo || r.original.costo_por_unidad || r.original.valor || 'Sin valor identificado'} · Unidad: {r.original.unidad || r.original.unidad_medida_base || 'Sin unidad identificada'}</p>
          <pre className="whitespace-pre-wrap break-all">{JSON.stringify(r.original, null, 2)}</pre>
        </details>
      </li>)}</ul>
      <button disabled={pendingLoading || !!pendingError || skip === 0} onClick={() => setSkip(s => Math.max(0, s - pendingPageSize))}>Anteriores</button>
      {!pendingLoading && !pendingError && <span className="mx-3">{pending.total ? skip + 1 : 0}–{Math.min(skip + pendingPageSize, pending.total)} de {pending.total} registros</span>}
      <button disabled={pendingLoading || !!pendingError || skip + pendingPageSize >= pending.total} onClick={() => setSkip(s => s + pendingPageSize)}>Siguientes</button>
    </details>
    {models.length > 0 && <fieldset disabled={!canWrite || busy} className="space-y-2 border rounded p-3">
      <legend>Antepresupuesto paramétrico de la fuente</legend>
      <p>Conserva el precio base, aplica el FIC de la localidad y documenta el ajuste del proyecto. Requiere un análisis específico antes de formar una propuesta contractual.</p>
      <label>Modelo paramétrico<select aria-label="Modelo paramétrico" className={className} value={modelId} onChange={e => { setModelId(e.target.value); setFactorId(''); setResult(null); }}>
        <option value="">Elige el tipo de obra</option>{models.map(m => <option key={m.id} value={m.id}>{m.original.codigo} · {m.original.nombre} · ${m.original.costo_por_unidad}/{m.original.unidad_medida_base}</option>)}
      </select></label>
      <label>Localidad de la obra<select aria-label="Localidad de la obra" className={className} value={factorId} onChange={e => { setFactorId(e.target.value); setResult(null); }}>
        <option value="">Elige la localidad</option>{compatibleFactors.map(f => <option key={f.id} value={f.id}>{f.original.localidad_base} · FIC {f.original.valor}</option>)}
      </select></label>
      <label>Cantidad {model?.original.unidad_medida_base}<input className={className} type="number" step="0.0001" min="0.0001" value={quantity} onChange={e => { setQuantity(e.target.value); setResult(null); }} /></label>
      <label>Factor de ajuste del proyecto<input className={className} type="number" step="0.000001" min="0.000001" max="100" value={adjustment} onChange={e => { setAdjustment(e.target.value); setResult(null); }} /></label>
      <label>Justificación y condiciones del proyecto<textarea className={className} value={reference} onChange={e => { setReference(e.target.value); setResult(null); }} /></label>
      <button className="rounded border p-2 disabled:opacity-40" disabled={busy || !modelId || !factorId || Number(quantity) <= 0 || Number(adjustment) <= 0 || reference.trim().length < 10} onClick={() => void estimate()}>Calcular y guardar antepresupuesto</button>
    </fieldset>}
    {result && <p role="status">Estimación guardada: {Number(result.monto).toLocaleString('es-MX', {style: 'currency', currency: 'MXN'})}. Base original; no incluye actualización por inflación.</p>}
    {scope && <p>FIC de {scope.replaceAll('_', ' ').toLowerCase()}. Conserva el alcance de la fuente, incluidos sus acarreos; no es un índice de inflación.</p>}
    {error && <p role="alert" className="text-[#F08080]">{error}</p>}
  </div>;
}

export function ImportacionesCatalogosPanel({onImported}: {onImported: () => void}) {
  const [batches, setBatches] = useState<CatalogoImportacionOut[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [sources, setSources] = useState<Array<{fuente_id: string; titulo: string; nombre_visible?: string; sha256: string; fecha_vigencia: string; original_cotejado: boolean}>>([]);
  const [chosen, setChosen] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const role = useAuthStore(s => s.user?.role);
  const {canWrite} = permisosBim(role);
  useEffect(() => {
    let active = true;
    void megalodonClient.catalogoImportaciones.listar().then(data => { if (active) setBatches(data.items); })
      .catch(e => { if (active) setError(message(e)); });
    return () => { active = false; };
  }, []);
  async function preview(archivo: File) {
    setFile(archivo); setSources([]); setChosen([]); setBusy(true); setError(''); setNotice('');
    try {
      const data = await megalodonClient.catalogoImportaciones.verificar(archivo);
      setSources(data.fuentes);
      const imported = new Set(batches.flatMap(b => b.fuentes));
      setChosen(data.fuentes.filter(s => s.original_cotejado && !imported.has(s.fuente_id)).map(s => s.fuente_id));
    } catch (e) { setError(message(e)); } finally { setBusy(false); }
  }
  async function save() {
    if (!file) return;
    setBusy(true); setError('');
    try {
      const data = await megalodonClient.catalogoImportaciones.importar(file, chosen);
      setBatches((await megalodonClient.catalogoImportaciones.listar()).items); setSelectedId(data.id);
      setNotice(data.creada ? 'Edición importada. Los pendientes se conservaron para revisión.' : 'Esta edición ya estaba importada; se recuperó sin duplicar registros.');
      setSources([]); setFile(null);
      onImported();
    } catch (e) { setError(message(e)); } finally { setBusy(false); }
  }
  const batch = batches.find(b => b.id === selectedId);
  return <details className="p-3 text-xs border rounded" aria-label="Administrar catálogos reales">
    <summary>Ediciones importadas y revisiones pendientes</summary>
    <p className="my-2">Las ediciones conservan fecha, procedencia y precios originales. Importar una edición no sustituye otra ni actualiza precios automáticamente.</p>
    {canWrite && <label>Importar paquete de catálogo ZIP<input type="file" accept=".zip" disabled={busy} className={className} onChange={e => { const f = e.target.files?.[0]; if (f) void preview(f); }} /></label>}
    {sources.length > 0 && <div className="my-3">
      <p>Elige las fuentes de esta edición. Las que ya tienen una edición importada se dejan sin seleccionar para evitar incorporar versiones antiguas por accidente.</p>
      {sources.map(s => <label key={s.fuente_id} className="block my-2"><input type="checkbox" disabled={busy || !s.original_cotejado} checked={chosen.includes(s.fuente_id)} onChange={e => setChosen(prev => e.target.checked ? [...prev, s.fuente_id] : prev.filter(id => id !== s.fuente_id))} /> {sourceDisplayName(s.fuente_id, s.titulo, s.nombre_visible)} · ID {s.fuente_id} · referencia {s.sha256.slice(0, 8)} {s.original_cotejado ? '' : '· Falta PDF original'}</label>)}
      <button disabled={busy || !chosen.length} onClick={() => void save()} className="rounded border p-2 disabled:opacity-40">Importar fuentes seleccionadas</button>
    </div>}
    {busy && <p role="status">Verificando y guardando la edición…</p>}
    {notice && <p role="status">{notice}</p>}
    <label>Edición para consultar<select aria-label="Edición para consultar" className={className} value={selectedId} onChange={e => setSelectedId(e.target.value)}>
      <option value="">Elige una edición ({batches.length})</option>{batches.map(b => <option key={b.id} value={b.id}>{b.fuentes.map((id, index) => `${sourceDisplayName(id, undefined, b.fuentes_visibles?.[index])} · ${id}`).join(', ')} · edición {b.id.slice(0, 8)} · {b.resumen.proyecciones_costeo} precios habilitados</option>)}
    </select></label>
    {batch && <Edition key={batch.id} batch={batch} canWrite={canWrite} />}
    {error && <p role="alert" className="text-[#F08080]">{error}</p>}
  </details>;
}
