import { useEffect, useMemo, useRef, useState } from 'react';
import { Activity, AlertCircle, Database, ExternalLink, Globe2, Layers3, MapPinned, Plane, Search, Ship } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';
import type { ContextoGeoTez } from '@/lib/megalodon-client';
import { observationsFromContext, providerStatus, regionalBounds } from './intelligence-data';
import type { ObservationKind, ProviderInfo, RegionalBounds } from './intelligence-data';

type KindFilter = 'all' | ObservationKind;
interface Props { onOpenMap: () => void; onOpenOrbit: () => void; }

const GROUPS = [
  { title: 'Aeronáutica', entries: ['Vuelos civiles', 'Vuelos militares'] },
  { title: 'Marítima', entries: ['Buques AIS', 'Actividad pesquera'] },
  { title: 'Espacial', entries: ['Satélites'] },
  { title: 'Geología y ambiente', entries: ['Sismos', 'Volcanes', 'Incendios', 'Meteorología', 'Calidad del aire'] },
  { title: 'Contexto global', entries: ['Conflictos', 'Cortes de internet'] },
  { title: 'Infraestructura', entries: ['Cámaras públicas', 'Infraestructura', 'Centrales eléctricas', 'Torres móviles', 'Tráfico ferroviario'] },
  { title: 'Terreno y topografía', entries: ['Topografía / DEM'] },
  { title: 'Señales y conectividad', entries: ['Dispositivos IoT', 'Radio / SIGINT', 'Interferencias GNSS'] },
] as const;

function dateLabel(value: string | null | undefined) {
  if (!value) return 'Sin fecha registrada';
  const time = new Date(value).getTime();
  return Number.isFinite(time) ? new Date(time).toLocaleString('es-MX', { dateStyle: 'medium', timeStyle: 'short' }) : 'Fecha inválida';
}

function isActiveLayer(name: string) {
  return name === 'Vuelos civiles' || name === 'Buques AIS' || name === 'Sismos';
}

export default function IntelligenceCenter({ onOpenMap, onOpenOrbit }: Props) {
  const [lat, setLat] = useState('19.4326');
  const [lon, setLon] = useState('-99.1332');
  const [radiusKm, setRadiusKm] = useState(100);
  const [context, setContext] = useState<ContextoGeoTez | null>(null);
  const [bounds, setBounds] = useState<RegionalBounds | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState<KindFilter>('all');
  const [catalogQuery, setCatalogQuery] = useState('');
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const requestId = useRef(0);

  useEffect(() => () => { requestId.current += 1; }, []);

  const queryRegion = async () => {
    let region: RegionalBounds;
    try {
      region = regionalBounds(lat, lon, radiusKm);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Coordenadas no válidas');
      return;
    }
    const request = ++requestId.current;
    setBusy(true);
    setError('');
    setContext(null);
    setBounds(null);
    setSelectedId(null);
    try {
      const result = await megalodonClient.tezcatlipoca.geoContext({
        latMin: region.latMin, latMax: region.latMax,
        lonMin: region.lonMin, lonMax: region.lonMax, limit: 200,
      });
      if (request !== requestId.current) return;
      setContext(result);
      setBounds(region);
    } catch (cause) {
      if (request !== requestId.current) return;
      setError(cause instanceof Error ? cause.message : 'No fue posible consultar esta región');
    } finally {
      if (request === requestId.current) setBusy(false);
    }
  };

  const observations = useMemo(() => observationsFromContext(context), [context]);
  const filtered = useMemo(() => observations.filter(item => filter === 'all' || item.kind === filter), [observations, filter]);
  const selected = filtered.find(item => item.id === selectedId) ?? null;
  const count = (kind: ObservationKind) => context ? observations.filter(item => item.kind === kind).length.toLocaleString('es-MX') : '—';
  const sources: Array<{ name: string; info: ProviderInfo | undefined; kind: ObservationKind }> = [
    { name: 'USGS · sismos', info: context?.sources.usgs as ProviderInfo | undefined, kind: 'earthquake' },
    { name: 'ADSB.lol · aeronaves', info: context?.sources.adsb_lol as ProviderInfo | undefined, kind: 'aircraft' },
    { name: 'AIS · embarcaciones', info: context?.sources.ais as ProviderInfo | undefined, kind: 'ship' },
  ];
  const colors: Record<ObservationKind, string> = {
    earthquake: 'var(--amber)', aircraft: 'var(--accent-cyan)', ship: 'var(--accent-gold)',
  };

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-3">
        {([
          { kind: 'earthquake' as const, title: 'Sismos', source: 'USGS', Icon: Activity },
          { kind: 'aircraft' as const, title: 'Aeronaves', source: 'ADSB.lol', Icon: Plane },
          { kind: 'ship' as const, title: 'Embarcaciones', source: 'AIS', Icon: Ship },
        ]).map(({kind, title, source, Icon}) => (
          <div key={kind} className="rounded-lg border p-4" style={{ background: 'var(--surface)', borderColor: 'var(--border-subtle)' }}>
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium">{title}</span>
              <Icon size={17} style={{ color: colors[kind] }}/>
            </div>
            <p className="my-2 text-2xl font-semibold" aria-label={title + ': ' + count(kind)}>{count(kind)}</p>
            <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>{source} · {providerStatus(sources.find(row => row.kind === kind)?.info, context !== null)}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(300px,0.65fr)]">
        <section className="rounded-xl border p-4 space-y-4" style={{ background: 'var(--surface)', borderColor: 'var(--border-subtle)' }} aria-label="Consulta territorial">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-sm font-semibold">Inteligencia territorial</h2>
              <p className="mt-1 text-xs" style={{ color: 'var(--text-muted)' }}>Región delimitada · observaciones reales · consulta bajo demanda</p>
            </div>
            <button type="button" onClick={onOpenMap} className="flex items-center gap-1 rounded-md border px-3 py-2 text-xs" style={{ borderColor: 'var(--border-subtle)' }}>
              <MapPinned size={14}/> Abrir mapa 2D
            </button>
          </div>

          <form className="grid gap-2 sm:grid-cols-[1fr_1fr_auto_auto] sm:items-end" onSubmit={event => { event.preventDefault(); void queryRegion(); }}>
            <label className="text-[11px]">Latitud
              <input className="mt-1 w-full rounded-md border p-2 text-xs" style={{ background: 'var(--surface-elevated)', borderColor: 'var(--border-subtle)' }}
                value={lat} onChange={event => setLat(event.target.value)} inputMode="decimal" aria-label="Latitud del centro"/>
            </label>
            <label className="text-[11px]">Longitud
              <input className="mt-1 w-full rounded-md border p-2 text-xs" style={{ background: 'var(--surface-elevated)', borderColor: 'var(--border-subtle)' }}
                value={lon} onChange={event => setLon(event.target.value)} inputMode="decimal" aria-label="Longitud del centro"/>
            </label>
            <label className="text-[11px]">Radio
              <select value={radiusKm} onChange={event => setRadiusKm(Number(event.target.value))}
                className="mt-1 w-full rounded-md border p-2 text-xs" style={{ background: 'var(--surface-elevated)', borderColor: 'var(--border-subtle)' }}>
                <option value={20}>20 km</option><option value={50}>50 km</option><option value={100}>100 km</option><option value={200}>200 km</option>
              </select>
            </label>
            <button type="submit" disabled={busy} className="rounded-md px-3 py-2 text-xs font-medium disabled:opacity-50" style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}>
              {busy ? 'Consultando…' : 'Consultar región'}
            </button>
          </form>
          <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
            Centro inicial: Ciudad de México (solo referencia; no es tu ubicación). No se envían peticiones hasta que consultes.
          </p>
          {error && <p role="alert" className="rounded-md border p-2 text-xs" style={{ color: 'var(--danger)', borderColor: 'var(--border-subtle)' }}><AlertCircle size={12} className="mr-1 inline"/>{error}</p>}
          {context && bounds && (
            <div className="rounded-md p-3 text-xs" style={{ background: 'var(--surface-elevated)' }}>
              <strong>Consulta recibida: {dateLabel(context.timestamp)}</strong>
              <p className="mt-1" style={{ color: 'var(--text-muted)' }}>EPSG:4326 · límites {bounds.latMin.toFixed(3)}, {bounds.lonMin.toFixed(3)} a {bounds.latMax.toFixed(3)}, {bounds.lonMax.toFixed(3)}. Una consulta no significa seguimiento en directo.</p>
            </div>
          )}
          <div className="flex flex-wrap gap-2" aria-label="Filtrar observaciones">
            {([
              ['all', 'Todas'], ['earthquake', 'Sismos'], ['aircraft', 'Aeronaves'], ['ship', 'Embarcaciones'],
            ] as const).map(([id,label]) => (
              <button key={id} type="button" onClick={() => { setFilter(id); setSelectedId(null); }} aria-pressed={filter === id}
                className="rounded-md border px-2.5 py-1.5 text-xs"
                style={{ background: filter === id ? 'var(--surface-elevated)' : 'transparent', borderColor: filter === id ? 'var(--accent-gold-dim)' : 'var(--border-subtle)' }}>
                {label}
              </button>
            ))}
          </div>

          {!context ? (
            <div className="rounded-md border border-dashed p-6 text-center text-xs" style={{ color: 'var(--text-muted)', borderColor: 'var(--border-subtle)' }}>
              {busy ? 'Consultando observaciones y estado de proveedores…' : 'Sin consulta regional. Selecciona un centro y pulsa «Consultar región».'}
            </div>
          ) : filtered.length === 0 ? (
            <div className="rounded-md border border-dashed p-6 text-center text-xs" style={{ color: 'var(--text-muted)', borderColor: 'var(--border-subtle)' }}>
              No se recibieron observaciones válidas de este tipo dentro de la región. Revisa el estado de las fuentes; no implica ausencia de eventos.
            </div>
          ) : (
            <div className="max-h-80 overflow-auto rounded-md border" style={{ borderColor: 'var(--border-subtle)' }}>
              <table className="w-full text-left text-xs">
                <thead style={{ background: 'var(--surface-elevated)', color: 'var(--text-muted)' }}>
                  <tr><th className="p-2">Observación</th><th className="p-2">Fuente</th><th className="p-2">Fecha observada</th></tr>
                </thead>
                <tbody>
                  {filtered.slice(0, 40).map((item, i) => (
                    <tr key={item.id + '-' + i} className="border-t" style={{ borderColor: 'var(--border-subtle)' }}>
                      <td className="p-2">
                        <button type="button" className="text-left underline-offset-2 hover:underline" onClick={() => setSelectedId(item.id)}>{item.title}</button>
                        <span className="block text-[10px]" style={{ color: 'var(--text-muted)' }}>{item.detail}</span>
                      </td>
                      <td className="p-2">{item.source}</td><td className="p-2">{dateLabel(item.observedAt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {filtered.length > 40 && <p className="p-2 text-[11px]" style={{ color: 'var(--text-muted)' }}>Mostrando 40 de {filtered.length} registros. Reduce la región para revisar el resto.</p>}
            </div>
          )}
          {selected && (
            <div className="rounded-md border p-3 text-xs" style={{ borderColor: 'var(--border-subtle)' }}>
              <div className="flex justify-between gap-2"><strong>{selected.title}</strong><button type="button" onClick={() => setSelectedId(null)} aria-label="Cerrar detalle">Cerrar</button></div>
              <p className="mt-1">{selected.detail}</p>
              <p>Coordenadas: {selected.lat.toFixed(5)}, {selected.lon.toFixed(5)} · Fuente: {selected.source}</p>
              <p>Observado: {dateLabel(selected.observedAt)}</p>
            </div>
          )}
        </section>

        <aside className="space-y-4">
          <section className="rounded-xl border p-4 space-y-3" style={{ background: 'var(--surface)', borderColor: 'var(--border-subtle)' }}>
            <div className="flex items-center gap-2"><Database size={15} style={{ color: 'var(--accent-gold)' }}/><h2 className="text-sm font-semibold">Procedencia y estado</h2></div>
            {sources.map(source => (
              <div key={source.name} className="border-t pt-2 text-xs" style={{ borderColor: 'var(--border-subtle)' }}>
                <div className="flex justify-between gap-2"><strong>{source.name}</strong><span className="text-right" style={{ color: 'var(--text-muted)' }}>{providerStatus(source.info, context !== null)}</span></div>
                {context && source.info && <>
                  {source.info.coverage && <p className="mt-1" style={{ color: 'var(--text-muted)' }}>Cobertura: {source.info.coverage}</p>}
                  {source.info.last_observation && <p style={{ color: 'var(--text-muted)' }}>Última observación: {dateLabel(source.info.last_observation)}</p>}
                  {source.info.last_success && <p style={{ color: 'var(--text-muted)' }}>Última recepción: {dateLabel(source.info.last_success)}</p>}
                  {source.info.license && <p style={{ color: 'var(--text-muted)' }}>Licencia indicada: {source.info.license}</p>}
                </>}
              </div>
            ))}
            <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>Estado del proveedor, hora de observación y hora de consulta son conceptos distintos. No hay datos simulados.</p>
          </section>
          <section className="rounded-xl border p-4 space-y-2" style={{ background: 'var(--surface)', borderColor: 'var(--border-subtle)' }}>
            <h2 className="text-sm font-semibold">Exploración especializada</h2>
            <button type="button" onClick={onOpenMap} className="flex w-full items-center justify-between rounded-md border p-2.5 text-xs" style={{ borderColor: 'var(--border-subtle)' }}>
              <span className="flex items-center gap-2"><Globe2 size={14}/> Mapa terrestre NASA · 2D</span><ExternalLink size={13}/>
            </button>
            <button type="button" onClick={onOpenOrbit} className="flex w-full items-center justify-between rounded-md border p-2.5 text-xs" style={{ borderColor: 'var(--border-subtle)' }}>
              <span className="flex items-center gap-2"><Activity size={14}/> Rastreo orbital 3D</span><ExternalLink size={13}/>
            </button>
            <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>El motor orbital no se carga en esta pantalla. Las vistas geográficas no son levantamientos ni evidencia contractual aprobada.</p>
          </section>
        </aside>
      </div>

      <section className="rounded-xl border p-4 space-y-3" style={{ background: 'var(--surface)', borderColor: 'var(--border-subtle)' }}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2"><Layers3 size={16}/><h2 className="text-sm font-semibold">Catálogo multidominio de la carátula</h2></div>
          <button type="button" className="rounded-md border px-3 py-1.5 text-xs" style={{ borderColor: 'var(--border-subtle)' }}
            onClick={() => setCatalogOpen(v => !v)} aria-expanded={catalogOpen}>
            {catalogOpen ? 'Ocultar catálogo' : 'Ver 21 capacidades declaradas'}
          </button>
        </div>
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Se recupera la clasificación del ZIP; únicamente sismos, vuelos civiles y AIS están conectados a esta vista. Las demás requieren integración y verificación propia: no se anuncian como activas.</p>
        {catalogOpen && <>
          <label className="flex items-center gap-2 rounded-md border p-2" style={{ borderColor: 'var(--border-subtle)' }}>
            <Search size={14}/><input value={catalogQuery} onChange={event => setCatalogQuery(event.target.value)}
              placeholder="Buscar capacidad" aria-label="Buscar capacidades" className="min-w-0 flex-1 bg-transparent text-xs outline-none"/>
          </label>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {GROUPS.map(group => {
              const matching = group.entries.filter(name => name.toLowerCase().includes(catalogQuery.toLowerCase()));
              if (matching.length === 0) return null;
              return <div key={group.title} className="rounded-lg border p-3" style={{ borderColor: 'var(--border-subtle)' }}>
                <h3 className="mb-2 text-xs font-semibold">{group.title}</h3>
                {matching.map(name => <div key={name} className="flex justify-between gap-2 py-1 text-[11px]">
                  <span>{name}</span>
                  <span className="text-right" style={{ color: 'var(--text-muted)' }}>{isActiveLayer(name) ? 'Conector geo' : 'No conectado aquí'}</span>
                </div>)}
              </div>;
            })}
          </div>
        </>}
      </section>
    </div>
  );
}
