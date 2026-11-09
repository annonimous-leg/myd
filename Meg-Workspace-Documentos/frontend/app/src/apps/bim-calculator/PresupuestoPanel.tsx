import { useEffect, useState } from 'react';
import { megalodonClient } from '@/lib/api-client';
import type { Presupuesto } from '@/lib/megalodon-client';
import { useAuthStore } from '@/stores/useAuthStore';
import { permisosBim } from '@/lib/bim-permissions';
import CatalogoPartidaPicker from './CatalogoPartidaPicker';

const money = (value: number) => new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN' }).format(value);
const buttonClass = 'px-3 py-2 rounded-md text-xs border border-(--border-subtle) disabled:opacity-40 disabled:cursor-not-allowed';

export default function PresupuestoPanel({ expedienteId, nuevoId }: { expedienteId: string; nuevoId: string }) {
  const [items, setItems] = useState<Presupuesto[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const role = useAuthStore(s => s.user?.role);
  const { canWrite, canApprove } = permisosBim(role);
  useEffect(() => {
    let active = true;
    setError('');
    megalodonClient.presupuestos.list(expedienteId).then(list => {
      if (!active) return;
      setItems(list);
      setSelectedId(previous => nuevoId || (list.some(p => p.id === previous) ? previous : list[0]?.id || ''));
    }).catch(e => { if (active) setError(e instanceof Error ? e.message : 'No se pudieron cargar los presupuestos'); });
    return () => { active = false; };
  }, [expedienteId, nuevoId]);
  const budget = items.find(p => p.id === selectedId);
  const coverage = budget?.metadatos?.bim_cobertura;
  const topografia = budget?.metadatos?.topografia_cobertura;
  const pending = budget?.partidas.filter(p => !(p.cantidad > 0 && p.precio_unitario > 0 && p.importe > 0)) || [];
  const topografiaSinEvidencia = !!budget && (!!topografia || budget.partidas.some(p => p.metadatos?.topografia != null)) && !budget.metadatos?.topografia_evidencia;
  const complete = !topografiaSinEvidencia && coverage?.completa !== false && topografia?.completa !== false && !!budget?.partidas.length && pending.length === 0 && budget.monto_total > 0;
  async function change(state: 'CALCULADO' | 'VALIDADO' | 'APROBADO') {
    if (!budget || busy) return;
    setBusy(true); setError('');
    try {
      const result = await megalodonClient.presupuestos.cambiarEstado(expedienteId, budget.id, state);
      setItems(previous => previous.map(p => p.id === result.id ? result : p));
    } catch (e) { setError(e instanceof Error ? e.message : 'No se pudo cambiar el estado'); }
    finally { setBusy(false); }
  }
  async function download(format: 'excel' | 'pdf') {
    if (!budget || busy) return;
    setBusy(true); setError('');
    try {
      const blob = await (format === 'excel' ? megalodonClient.presupuestos.exportExcel(expedienteId, budget.id)
        : megalodonClient.presupuestos.exportPdf(expedienteId, budget.id));
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url; link.download = `${budget.identificador}.${format === 'excel' ? 'xlsx' : 'pdf'}`;
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setError(e instanceof Error ? e.message : 'No se pudo descargar el archivo'); }
    finally { setBusy(false); }
  }
  return <section className="mt-4 pt-3 border-t border-(--border-subtle) space-y-3" aria-label="Revisión del presupuesto">
    <h3 className="font-semibold text-sm">Revisar y entregar presupuesto</h3>
    {error && <p role="alert" className="text-xs text-(--danger)">{error}</p>}
    {!items.length ? <p className="text-xs text-(--text-muted)">Genera el presupuesto arriba para revisar partidas y descargarlo aquí.</p> : <>
      <label className="block text-xs">Presupuesto del expediente
        <select aria-label="Presupuesto del expediente" value={selectedId} onChange={e => setSelectedId(e.target.value)}
          className="w-full mt-1 p-2 rounded bg-(--surface-elevated)">
          {items.map(p => <option key={p.id} value={p.id}>{p.identificador} · {p.nombre}</option>)}
        </select>
      </label>
      {budget && <>
        <div className="flex justify-between text-sm"><span role="status">Estado: {budget.estado}</span><strong>{money(budget.monto_total)}</strong></div>
        {coverage && <p role="status" className="text-xs">{coverage.completa ? 'Mediciones completas' : 'Presupuesto PARCIAL'}: {coverage.elementos_medidos} de {coverage.elementos_totales} elementos medidos. {coverage.capturas.length} capturas con referencia.</p>}
        {topografia && <p role="status" className="text-xs">{topografia.completa ? 'Cobertura topográfica completa' : 'Presupuesto PARCIAL: cobertura topográfica pendiente'}. Área común: {topografia.area_comun_m2.toLocaleString('es-MX')} m². Pendiente: {topografia.area_existente_pendiente_m2.toLocaleString('es-MX')} m² en terreno y {topografia.area_proyecto_pendiente_m2.toLocaleString('es-MX')} m² en proyecto.</p>}
        {topografiaSinEvidencia && <p role="alert" className="text-xs text-(--danger)">Falta la evidencia del terreno. Genera una nueva versión antes de aprobar o exportar.</p>}
        {!!coverage?.capturas.length && <details className="text-xs space-y-2">
          <summary className="cursor-pointer">Ver fuentes de las cantidades capturadas</summary>
          {coverage.capturas.map(capture => <div key={capture.elemento_id} className="p-2 rounded bg-(--surface-elevated) break-words">
            <p>{capture.cantidad} {capture.unidad} · {capture.referencia}</p>
            <p className="text-(--text-muted) break-all">Elemento: {capture.elemento_id}</p>
            <p className="text-(--text-muted) break-all">Usuario: {capture.usuario_id} · {new Date(capture.capturado_en).toLocaleString('es-MX')}</p>
          </div>)}
        </details>}
        {!complete && <p className="text-xs text-(--warning)">Lo medido ya está costeado cuando tiene precio. {coverage && <>Quedan {coverage.elementos_pendientes.length} elementos sin medición. </>}{pending.length} partida(s) requieren cantidad o precio. Completa la cobertura y asigna los conceptos correspondientes. La aprobación está bloqueada.</p>}
        <div className="overflow-x-auto"><table className="w-full text-xs"><caption className="sr-only">Partidas del presupuesto</caption>
          <thead><tr><th className="text-left p-1">Concepto</th><th>Cantidad</th><th>Unidad</th><th>Precio</th><th>Importe</th></tr></thead>
          <tbody>{budget.partidas.map(p => <tr key={p.id} className="border-t border-(--border-subtle)">
            <td className="p-2">{p.descripcion}
              {p.metadatos?.catalogo_asignado && <p className="mt-1 text-(--text-muted)">{p.metadatos.catalogo_asignado.descripcion} · {p.metadatos.catalogo_asignado.fuente} · {p.metadatos.catalogo_asignado.vigencia_inicio || 'Vigencia sin registrar'}</p>}
              {p.metadatos?.topografia != null && canWrite && !['VALIDADO', 'APROBADO'].includes(budget.estado) &&
                <CatalogoPartidaPicker key={p.id} expedienteId={expedienteId} presupuestoId={budget.id} partida={p}
                  onSaved={result => setItems(previous => previous.map(item => item.id === result.id ? result : item))} />}
            </td><td>{p.cantidad}</td><td>{p.unidad}</td>
            <td>{p.precio_unitario > 0 ? money(p.precio_unitario) : 'Pendiente'}</td><td>{money(p.importe)}</td>
          </tr>)}</tbody></table></div>
        <div className="flex flex-wrap gap-2">
          {['BORRADOR', 'RECHAZADO'].includes(budget.estado) && <button className={buttonClass} disabled={busy || !canWrite || !complete} onClick={() => change('CALCULADO')}>Confirmar cálculo</button>}
          {budget.estado === 'CALCULADO' && <button className={buttonClass} disabled={busy || !canWrite || !complete} onClick={() => change('VALIDADO')}>Validar presupuesto</button>}
          {budget.estado === 'VALIDADO' && <button className={buttonClass} disabled={busy || !canApprove || !complete} onClick={() => change('APROBADO')}>Aprobar presupuesto</button>}
          <button className={buttonClass} disabled={busy} onClick={() => download('excel')}>Descargar Excel</button>
          <button className={buttonClass} disabled={busy} onClick={() => download('pdf')}>Descargar PDF</button>
        </div>
        {!canWrite && <p className="text-xs text-(--text-muted)">Tu cuenta permite consultar y descargar.</p>}
        {budget.estado === 'VALIDADO' && !canApprove && <p className="text-xs text-(--text-muted)">Un revisor o administrador debe aprobar esta versión.</p>}
      </>}
    </>}
  </section>;
}
