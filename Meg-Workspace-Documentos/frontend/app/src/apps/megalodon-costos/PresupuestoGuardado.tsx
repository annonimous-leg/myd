import { useState } from 'react';
import { megalodonClient } from '@/lib/api-client';
import type { Presupuesto } from '@/lib/megalodon-client';
import { formatMXN } from './engines/montecarlo';

const button = 'rounded border border-zinc-700 px-3 py-2 text-xs disabled:opacity-40';

/** Edits are domain commands; existing APU are never flattened into manual prices. */
export function PresupuestoGuardado({ presupuesto: p, onChange, onClose, onReload }: {
  presupuesto: Presupuesto; onChange: (p: Presupuesto) => void;
  onClose: () => void; onReload: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [motivo, setMotivo] = useState('');
  const [cantidades, setCantidades] = useState<Record<string, string>>({});
  const [comparacion, setComparacion] = useState('');
  const editable = !['VALIDADO', 'APROBADO'].includes(p.estado);
  const revision = p.metadatos?.revision;
  const origen = revision && typeof revision === 'object' && 'presupuesto_origen_id' in revision
    ? String(revision.presupuesto_origen_id) : null;
  const run = async (command: () => Promise<void>) => {
    setBusy(true); setError('');
    try { await command(); }
    catch (e) { setError(e instanceof Error ? e.message : 'No se pudo guardar el cambio.'); }
    finally { setBusy(false); }
  };
  const apply = (command: () => Promise<Presupuesto>) => run(async () => {
    const saved = await command(); onChange(saved); setCantidades({}); setComparacion('');
  });
  const state = (next: Presupuesto['estado']) => apply(() =>
    megalodonClient.presupuestos.cambiarEstado(p.expediente_id, p.id, next));

  return <section className="h-full overflow-auto space-y-4 p-4 text-zinc-200">
    <header className="flex flex-wrap items-center gap-3">
      <button className={button} disabled={busy} onClick={onClose}>Volver a presupuestos</button>
      <h2 className="font-semibold">{p.nombre}</h2><span>{p.estado}</span>
      <button className={button} disabled={busy} onClick={() => void run(onReload)}>Recargar guardado</button>
    </header>
    <p className="text-xs text-zinc-400">{p.identificador}</p>
    {!editable && <p className="text-amber-200 text-sm">Esta versión está protegida. Crea una revisión para cambiar cantidades o precios.</p>}
    {error && <p role="alert" className="text-red-300">{error}</p>}
    <div className="overflow-x-auto"><table className="w-full text-sm">
      <thead><tr className="text-left"><th>Concepto y análisis</th><th>Unidad</th><th>Cantidad</th><th>P. unitario</th><th>Importe</th><th>Acciones</th></tr></thead>
      <tbody>{p.partidas.map((partida) => {
        const medida = !!p.metadatos?.bim_cobertura || !!partida.metadatos?.topografia;
        const cantidad = cantidades[partida.id] ?? String(partida.cantidad);
        const valid = Number.isFinite(Number(cantidad)) && Number(cantidad) > 0;
        return <tr key={partida.id} className="border-t border-zinc-800 align-top">
          <td className="p-2 max-w-sm">{partida.numero}. {partida.descripcion}
            {!!partida.conceptos.length && <details className="mt-2 text-xs text-zinc-400"><summary>Ver conceptos e insumos</summary>
              {partida.conceptos.map((c) => <div key={c.id} className="py-2">
                <p>{c.clave} · {c.descripcion} · {c.cantidad} {c.unidad}</p>
                <ul>{c.insumos.map((i) => <li key={i.id}>{i.clave} · {i.descripcion}: {i.cantidad} {i.unidad} × {formatMXN(i.precio_unitario)}</li>)}</ul>
              </div>)}
            </details>}
            {partida.metadatos?.catalogo_asignado && <p className="text-xs text-zinc-400">Fuente: {partida.metadatos.catalogo_asignado.fuente}</p>}
            {medida && <p className="text-xs text-amber-200">Cantidad vinculada a su medición de origen.</p>}
          </td>
          <td className="p-2">{partida.unidad}</td>
          <td className="p-2"><input aria-label={`Cantidad partida ${partida.numero}`} type="number" step="0.0001" min="0.0001"
            disabled={busy || !editable || medida} value={cantidad} className="w-24 rounded bg-zinc-900 p-2"
            onChange={(e) => setCantidades({ ...cantidades, [partida.id]: e.target.value })} /></td>
          <td className="p-2">{formatMXN(partida.precio_unitario)}</td><td className="p-2">{formatMXN(partida.importe)}</td>
          <td className="p-2 space-x-2">
            <button className={button} disabled={busy || !editable || medida || !valid || cantidad === String(partida.cantidad)}
              onClick={() => void apply(() => megalodonClient.presupuestos.actualizarCantidad(p.expediente_id, p.id, partida.id, Number(cantidad)))}>Guardar cantidad</button>
            <button className={button} disabled={busy || !editable || medida}
              onClick={() => void apply(() => megalodonClient.presupuestos.eliminarPartida(p.expediente_id, p.id, partida.id))}>Quitar partida</button>
          </td>
        </tr>;
      })}</tbody>
    </table></div>
    <p>Directo: {formatMXN(p.monto_directo)} · Indirectos: {formatMXN(p.monto_indirecto)} · Utilidad: {formatMXN(p.monto_utilidad)} · Riesgo: {formatMXN(p.monto_riesgo || 0)} · Impuesto: {formatMXN(p.monto_impuesto)}</p>
    <p className="font-semibold">Total guardado: {formatMXN(p.monto_total)}</p>
    <div className="flex flex-wrap gap-2">
      <button className={button} disabled={busy || !editable} onClick={() => void apply(() => megalodonClient.presupuestos.recalcular(p.expediente_id, p.id))}>Recalcular</button>
      <button className={button} disabled={busy || p.estado !== 'CALCULADO'} onClick={() => void state('VALIDADO')}>Validar</button>
      <button className={button} disabled={busy || p.estado !== 'VALIDADO'} onClick={() => void state('APROBADO')}>Aprobar</button>
    </div>
    <div className="flex flex-wrap gap-2">
      <input aria-label="Motivo de revisión" value={motivo} maxLength={1000} disabled={busy} placeholder="Motivo de la nueva revisión"
        onChange={(e) => setMotivo(e.target.value)} className="rounded bg-zinc-900 p-2 text-sm min-w-64" />
      <button className={button} disabled={busy || !motivo.trim()}
        onClick={() => void apply(() => megalodonClient.presupuestos.crearRevision(p.expediente_id, p.id, motivo.trim()))}>Crear revisión independiente</button>
      {origen && <button className={button} disabled={busy} onClick={() => void run(async () => {
        const r = await megalodonClient.presupuestos.validarSobrecostos(p.expediente_id, p.id, origen);
        setComparacion(`Base: ${formatMXN(r.presupuesto_base)} · Diferencia: ${formatMXN(r.sobrecosto)} (${(r.factor_sobrecosto * 100).toFixed(2)}%) · ${r.dentro_tolerancia ? 'Dentro de tolerancia' : 'Fuera de tolerancia'}`);
      })}>Comparar con versión de origen</button>}
    </div>
    {comparacion && <p role="status" className="text-sm">{comparacion}</p>}
  </section>;
}
