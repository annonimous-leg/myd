import { useEffect, useState } from 'react';
import { megalodonClient } from '@/lib/api-client';
import type { ActualizacionPrecioSnapshot, ObservacionIndice, SolicitudActualizacionPrecio, VinculoIndice } from '@/lib/megalodon-client';
import { InventarioCatalogosPanel } from './InventarioCatalogosPanel';

export function MaterialIndexadoPicker({ onSelect }: {
  onSelect: (snapshot: ActualizacionPrecioSnapshot, solicitud: SolicitudActualizacionPrecio, cantidad: number) => void;
}) {
  const [vinculos, setVinculos] = useState<VinculoIndice[]>([]);
  const [skip, setSkip] = useState(0);
  const [vinculoId, setVinculoId] = useState('');
  const [observaciones, setObservaciones] = useState<ObservacionIndice[]>([]);
  const [baseId, setBaseId] = useState('');
  const [destinoId, setDestinoId] = useState('');
  const [cantidad, setCantidad] = useState(1);
  const [cargando, setCargando] = useState(false);
  const [calculando, setCalculando] = useState(false);
  const [error, setError] = useState('');
  const [snapshot, setSnapshot] = useState<ActualizacionPrecioSnapshot | null>(null);
  const [fechaCorte, setFechaCorte] = useState(() => {
    const hoy = new Date();
    return `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, '0')}-${String(hoy.getDate()).padStart(2, '0')}`;
  });
  const [variacion, setVariacion] = useState<string | null>(null);
  const vinculo = vinculos.find(v => v.id === vinculoId);

  useEffect(() => {
    let cancelado = false;
    setCargando(true); setError(''); setVinculoId(''); setVinculos([]);
    void megalodonClient.indicesCostos.vinculos(skip).then(items => {
      if (!cancelado) setVinculos(items);
    }).catch(e => { if (!cancelado) setError(e instanceof Error ? e.message : 'No se pudieron consultar correspondencias.'); })
      .finally(() => { if (!cancelado) setCargando(false); });
    return () => { cancelado = true; };
  }, [skip]);

  useEffect(() => {
    let cancelado = false;
    setObservaciones([]); setBaseId(''); setDestinoId(''); setSnapshot(null); setVariacion(null);
    if (!vinculo) return;
    setCargando(true); setError('');
    void (async () => {
      const items: ObservacionIndice[] = [];
      for (let offset = 0; !cancelado; offset += 500) {
        const page = await megalodonClient.indicesCostos.observaciones(vinculo.serie_id, offset);
        items.push(...page);
        if (page.length < 500) break;
      }
      if (!cancelado) setObservaciones(items);
    })().catch(e => { if (!cancelado) setError(e instanceof Error ? e.message : 'No se pudieron consultar niveles.'); })
      .finally(() => { if (!cancelado) setCargando(false); });
    return () => { cancelado = true; };
  }, [vinculo]);

  const solicitud = { vinculo_id: vinculoId, observacion_base_id: baseId, observacion_destino_id: destinoId };
  const calcular = async () => {
    setCalculando(true); setError(''); setSnapshot(null); setVariacion(null);
    try { setSnapshot(await megalodonClient.indicesCostos.calcular(solicitud)); }
    catch (e) { setError(e instanceof Error ? e.message : 'No se pudo confirmar el precio.'); }
    finally { setCalculando(false); }
  };
  const ultimaPublicacion = async () => {
    setCalculando(true); setError(''); setSnapshot(null); setVariacion(null);
    try {
      const result = await megalodonClient.indicesCostos.seleccionarPublicacion(vinculoId, fechaCorte);
      setObservaciones(items => [...new Map([...items, result.snapshot.base, result.snapshot.destino].map(o => [o.id, o])).values()]);
      setBaseId(result.solicitud.observacion_base_id); setDestinoId(result.solicitud.observacion_destino_id);
      setSnapshot(result.snapshot); setVariacion(result.variacion_porcentaje);
    } catch (e) { setError(e instanceof Error ? e.message : 'No se pudo seleccionar la publicación.'); }
    finally { setCalculando(false); }
  };
  const clase = 'bg-[#12121A] border border-[#2A2A3E] rounded p-2 text-xs text-[#E8E4DC]';
  const etiqueta = (o: ObservacionIndice) => `${o.mes.slice(0, 7)} · nivel ${o.valor} · publicado ${o.publicado_el} · captura ${o.revision_captura} · ${o.id.slice(0, 8)}`;

  return <div className="p-3 space-y-3 border-b border-[#2A2A3E] text-xs text-[#E8E4DC]">
    <InventarioCatalogosPanel />
    <p>Estimación por material, usando una correspondencia revisada y niveles publicados. Los precios del catálogo se conservan.</p>
    {error && <p role="alert" className="text-[#F08080]">{error}</p>}
    {cargando && <p role="status">Consultando evidencia…</p>}
    {!cargando && !error && vinculos.length === 0 && <p>No hay correspondencias activas en esta página. Se requiere revisar y registrar los materiales antes de actualizarlos.</p>}
    <div className="flex gap-2 items-center">
      <button disabled={skip === 0 || cargando || calculando} onClick={() => setSkip(s => Math.max(0, s - 50))}>Anterior</button>
      <span>Página {skip / 50 + 1}</span>
      <button disabled={vinculos.length < 50 || cargando || calculando} onClick={() => setSkip(s => s + 50)}>Siguiente</button>
    </div>
    <label className="block">Material revisado
      <select aria-label="Material revisado" className={`${clase} block w-full`} value={vinculoId} disabled={calculando}
        onChange={e => { setVinculoId(e.target.value); setSnapshot(null); }}>
        <option value="">Selecciona un material</option>
        {vinculos.map(v => <option key={v.id} value={v.id}>{v.insumo_original.clave} · {v.insumo_original.descripcion} · base {v.mes_base.slice(0, 7)}</option>)}
      </select>
    </label>
    {vinculo && <>
      <p>{vinculo.fundamento}</p>
      <label className="block">Publicaciones disponibles hasta
        <input aria-label="Fecha de corte de publicaciones" type="date" className={`${clase} ml-2`} value={fechaCorte} disabled={calculando}
          onChange={e => { setFechaCorte(e.target.value); setSnapshot(null); setVariacion(null); }} />
      </label>
      <button className={clase} disabled={!fechaCorte || cargando || calculando} onClick={() => void ultimaPublicacion()}>Usar última publicación disponible</button>
      <p>Se calcula hasta el último mes publicado de esta serie. Consulta las ediciones abajo para elegir una publicación específica.</p>
      <div className="grid grid-cols-2 gap-2">
        <label>Edición del nivel base<select aria-label="Edición del nivel base" className={`${clase} block w-full`} value={baseId} disabled={cargando || calculando}
          onChange={e => { setBaseId(e.target.value); setSnapshot(null); }}>
          <option value="">Selecciona una edición</option>
          {observaciones.filter(o => o.mes === vinculo.mes_base).map(o => <option key={o.id} value={o.id}>{etiqueta(o)}</option>)}
        </select></label>
        <label>Edición del nivel destino<select aria-label="Edición del nivel destino" className={`${clase} block w-full`} value={destinoId} disabled={cargando || calculando}
          onChange={e => { setDestinoId(e.target.value); setSnapshot(null); }}>
          <option value="">Selecciona una edición</option>
          {observaciones.filter(o => o.mes >= vinculo.mes_base).map(o => <option key={o.id} value={o.id}>{etiqueta(o)}</option>)}
        </select></label>
      </div>
      <button className={clase} disabled={!baseId || !destinoId || cargando || calculando} onClick={() => void calcular()}>{calculando ? 'Calculando…' : 'Confirmar precio estimado'}</button>
    </>}
    {snapshot && <div className="space-y-2">
      <p>Original: ${snapshot.precio_original} MXN · Estimado: ${snapshot.precio_actualizado} MXN/{snapshot.vinculo.insumo_original.unidad} sin IVA.</p>
      <p>{snapshot.serie.nombre} · {snapshot.serie.region} · {snapshot.base.mes.slice(0, 7)} → {snapshot.destino.mes.slice(0, 7)}</p>
      {variacion !== null && <p>Variación observada: {variacion}% · corte {fechaCorte}.</p>}
      <p>Publicación destino: {snapshot.destino.publicado_el}.</p>
      <a className="underline" href={snapshot.destino.evidencia.url} target="_blank" rel="noopener noreferrer">Consultar fuente de la publicación</a>
      <label>Cantidad <input aria-label="Cantidad de material" className={clase} type="number" min="0.0001" step="0.0001" value={cantidad} onChange={e => setCantidad(Number(e.target.value))} /></label>
      <button className={clase} disabled={!Number.isFinite(cantidad) || cantidad <= 0 || calculando} onClick={() => onSelect(snapshot, solicitud, cantidad)}>Añadir material al presupuesto</button>
    </div>}
  </div>;
}
