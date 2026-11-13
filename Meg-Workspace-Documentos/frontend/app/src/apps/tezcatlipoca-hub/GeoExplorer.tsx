/**
 * Tezcatlipoca terrestrial workspace — open NASA context, observed OSINT layers.
 * This is NOT Street View, a surveyed terrain, or a real-time satellite camera.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import type { FeatureCollection, Feature } from 'geojson';
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url';
import 'maplibre-gl/dist/maplibre-gl.css';
import { CalendarDays, Crosshair, Database, Eye, EyeOff, Globe2, Save, Satellite, ScanSearch } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';
import { abrirModulo } from '@/lib/navigation';
import type { ContextoGeoTez } from '@/lib/megalodon-client';

maplibregl.setWorkerUrl(maplibreWorkerUrl);

type LayerId = 'earthquakes' | 'aircraft' | 'ships';
type Center = { lon: number; lat: number };
type SourceState = { status?: string; last_success?: string | null; coverage?: string; age_seconds?: number };

const INITIAL: Center = { lon: -99.1332, lat: 19.4326 };
const INITIAL_ZOOM = 7;
const DEFAULT_LAYERS: Record<LayerId, boolean> = { earthquakes: true, aircraft: true, ships: true };
const LAYER_META: { id: LayerId; label: string; color: string }[] = [
  { id: 'earthquakes', label: 'Sismos', color: '#ed886c' },
  { id: 'aircraft', label: 'Aeronaves', color: '#70c7ff' },
  { id: 'ships', label: 'Embarcaciones', color: '#e7c675' },
];

function yesterdayUTC(): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
}

function nasaTiles(day: string): string[] {
  // A regional site survey requires higher resolution, licensed imagery.
  return [`https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/MODIS_Terra_CorrectedReflectance_TrueColor/default/${day}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg`];
}

function safeDate(value: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const d = new Date(value + 'T00:00:00Z');
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === value && value <= yesterdayUTC() ? value : null;
}

function collection(ctx: ContextoGeoTez | null, enabled: Record<LayerId, boolean>): FeatureCollection {
  const features: Feature[] = [];
  if (!ctx) return { type: 'FeatureCollection', features };
  if (enabled.earthquakes) for (const q of ctx.earthquakes) {
    if (!Number.isFinite(q.lat) || !Number.isFinite(q.lon)) continue;
    features.push({ type: 'Feature', properties: {
      kind: 'earthquakes', title: q.place || q.id, observed: q.time ?? '',
      details: `Magnitud ${q.magnitude}`, provider: q.source,
    }, geometry: { type: 'Point', coordinates: [q.lon, q.lat] } });
  }
  if (enabled.aircraft) for (const a of ctx.aircraft) {
    if (!Number.isFinite(a.lat) || !Number.isFinite(a.lon)) continue;
    features.push({ type: 'Feature', properties: {
      kind: 'aircraft', title: a.callsign || a.hex || 'Aeronave',
      observed: a.timestamp ?? '', details: a.hex, provider: a.source,
    }, geometry: { type: 'Point', coordinates: [a.lon, a.lat] } });
  }
  if (enabled.ships) for (const s of ctx.ships) {
    if (!Number.isFinite(s.lat) || !Number.isFinite(s.lon)) continue;
    features.push({ type: 'Feature', properties: {
      kind: 'ships', title: s.name || s.mmsi || 'Embarcación',
      observed: s.timestamp ?? '', details: s.mmsi, provider: s.source,
    }, geometry: { type: 'Point', coordinates: [s.lon, s.lat] } });
  }
  return { type: 'FeatureCollection', features };
}

function statusLabel(state?: SourceState): string {
  if (!state) return 'No consultado';
  if (state.status === 'coverage_limited') return 'Fuera de cobertura de la consulta';
  if (state.status === 'available') return 'Datos recibidos';
  if (state.status === 'stale') return 'Datos desactualizados';
  if (state.status === 'unavailable') return 'Proveedor no disponible';
  if (state.status === 'disabled_by_default') return 'Desactivado por licencia';
  return state.status || 'Sin información';
}

export default function GeoExplorer() {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  // Invalidate responses when the user moves the map or unmounts the view.
  const queryVersion = useRef(0);
  const [ready, setReady] = useState(false);
  const [date, setDate] = useState(yesterdayUTC);
  const [layers, setLayers] = useState(DEFAULT_LAYERS);
  const [context, setContext] = useState<ContextoGeoTez | null>(null);
  const [location, setLocation] = useState<Center>(INITIAL);
  const [inputLat, setInputLat] = useState(String(INITIAL.lat));
  const [inputLon, setInputLon] = useState(String(INITIAL.lon));
  const [querying, setQuerying] = useState(false);
  const [saving, setSaving] = useState(false);
  const [weather, setWeather] = useState<{
    status: string; source: string; temperature_2m_c?: number; wind_10m_ms?: number;
    run_time?: string; valid_time?: string; attribution?: string; reason?: string;
  } | null>(null);
  const [loadingWeather, setLoadingWeather] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [selected, setSelected] = useState<{ title: string; provider: string; observed: string } | null>(null);
  const [dirty, setDirty] = useState(true);

  useEffect(() => {
    if (!container.current || mapRef.current) return;
    const style: maplibregl.StyleSpecification = {
      version: 8,
      sources: {
        nasa: { type: 'raster', tiles: nasaTiles(date), tileSize: 256, maxzoom: 9, attribution: 'NASA EOSDIS GIBS · MODIS Terra' },
        observations: { type: 'geojson', data: { type: 'FeatureCollection', features: [] } },
      },
      layers: [
        { id: 'nasa', type: 'raster', source: 'nasa' },
        { id: 'quakes', type: 'circle', source: 'observations', filter: ['==', ['get', 'kind'], 'earthquakes'], paint: { 'circle-radius': 6, 'circle-color': '#ed886c', 'circle-stroke-width': 1.2, 'circle-stroke-color': '#fff' } },
        { id: 'planes', type: 'circle', source: 'observations', filter: ['==', ['get', 'kind'], 'aircraft'], paint: { 'circle-radius': 5, 'circle-color': '#70c7ff', 'circle-stroke-width': 1.2, 'circle-stroke-color': '#08131e' } },
        { id: 'vessels', type: 'circle', source: 'observations', filter: ['==', ['get', 'kind'], 'ships'], paint: { 'circle-radius': 5, 'circle-color': '#e7c675', 'circle-stroke-width': 1.2, 'circle-stroke-color': '#08131e' } },
      ],
    };
    const map = new maplibregl.Map({
      container: container.current, style, center: [INITIAL.lon, INITIAL.lat],
      zoom: INITIAL_ZOOM, attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl(), 'top-right');
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');
    map.on('load', () => setReady(true));
    map.on('moveend', () => { queryVersion.current += 1; setDirty(true); setQuerying(false); });
    map.on('click', e => {
      const hit = map.queryRenderedFeatures(e.point, { layers: ['quakes', 'planes', 'vessels'] });
      if (hit.length) {
        const props = hit[0].properties;
        setSelected({ title: String(props?.title || 'Observación'), provider: String(props?.provider || 'Desconocido'), observed: String(props?.observed || 'Sin fecha') });
      } else {
        setSelected(null);
        const next = { lat: e.lngLat.lat, lon: e.lngLat.lng };
        setLocation(next);
        setWeather(null);
        setInputLat(next.lat.toFixed(5));
        setInputLon(next.lon.toFixed(5));
      }
    });
    mapRef.current = map;
    return () => { queryVersion.current += 1; map.remove(); mapRef.current = null; };
    // Create only once; subsequent state updates use the existing map.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!ready) return;
    (mapRef.current?.getSource('nasa') as maplibregl.RasterTileSource | undefined)?.setTiles(nasaTiles(date));
  }, [date, ready]);

  useEffect(() => {
    if (!ready) return;
    (mapRef.current?.getSource('observations') as maplibregl.GeoJSONSource | undefined)?.setData(collection(context, layers));
  }, [context, layers, ready]);

  const explore = useCallback(() => {
    const lat = Number(inputLat), lon = Number(inputLon);
    if (inputLat.trim() === '' || inputLon.trim() === '' || !Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) {
      setError('Introduce latitud (-90 a 90) y longitud (-180 a 180).');
      return;
    }
    const point = { lat, lon };
    setLocation(point);
    setWeather(null);
    setError('');
    setSelected(null);
    mapRef.current?.flyTo({ center: [lon, lat], zoom: Math.max(9, mapRef.current.getZoom()), essential: true });
    setDirty(true);
  }, [inputLat, inputLon]);

  const refresh = useCallback(async () => {
    const map = mapRef.current;
    if (!map) return;
    const bounds = map.getBounds();
    if (bounds.getWest() < -180 || bounds.getEast() > 180) {
      setError('Acerca el mapa a una región sin cruzar el meridiano ±180°.');
      return;
    }
    const version = ++queryVersion.current;
    setQuerying(true); setError(''); setMessage('');
    try {
      const result = await megalodonClient.tezcatlipoca.geoContext({
        latMin: bounds.getSouth(), latMax: bounds.getNorth(),
        lonMin: bounds.getWest(), lonMax: bounds.getEast(),
        limit: 250,
      });
      if (version !== queryVersion.current) return;
      const currentBounds = map.getBounds();
      if (Math.abs(currentBounds.getSouth() - bounds.getSouth()) > 0.00001
          || Math.abs(currentBounds.getNorth() - bounds.getNorth()) > 0.00001
          || Math.abs(currentBounds.getWest() - bounds.getWest()) > 0.00001
          || Math.abs(currentBounds.getEast() - bounds.getEast()) > 0.00001) {
        setDirty(true);
        setError('La región cambió durante la consulta; vuelve a actualizar antes de guardar.');
        return;
      }
      setContext(result);
      setDirty(false);
      setMessage('Capas consultadas. Los resultados reflejan el momento de la consulta, no un flujo continuo.');
    } catch (e) {
      if (version !== queryVersion.current) return;
      setContext(null); setDirty(true);
      setError(e instanceof Error ? e.message : 'No se pudo consultar la región');
    } finally {
      if (version === queryVersion.current) setQuerying(false);
    }
  }, []);

  const loadWeather = useCallback(async () => {
    setLoadingWeather(true); setWeather(null); setError('');
    try {
      setWeather(await megalodonClient.tezcatlipoca.globalForecast(location.lat, location.lon));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo consultar el pronóstico global');
    } finally {
      setLoadingWeather(false);
    }
  }, [location]);

  const save = useCallback(async () => {
    const map = mapRef.current;
    const b = map?.getBounds();
    const recorded = context?.bbox;
    const matches = !!b && !!recorded
      && Math.abs(recorded[0] - b.getSouth()) < 0.00001
      && Math.abs(recorded[1] - b.getWest()) < 0.00001
      && Math.abs(recorded[2] - b.getNorth()) < 0.00001
      && Math.abs(recorded[3] - b.getEast()) < 0.00001;
    if (!map || !context || dirty || !matches) {
      setError('Actualiza la región antes de guardar: la vista cambió o no tiene resultados.');
      return;
    }
    setSaving(true); setError('');
    try {
      const center = map.getCenter();
      const viewportBounds = map.getBounds();
      const entry = await megalodonClient.tezcatlipoca.saveSnapshot({
        name: `Tezcatlipoca · ${new Date().toISOString().slice(0, 16).replace('T', ' ')} UTC`,
        description: 'Vista geoespacial contextual. No equivale a levantamiento topográfico ni a evidencia aprobada.',
        layers: LAYER_META.filter(l => layers[l.id]).map(l => l.id),
        viewport: {
          crs: 'EPSG:4326', center: { lon: center.lng, lat: center.lat },
          zoom: map.getZoom(), bbox: [viewportBounds.getWest(), viewportBounds.getSouth(), viewportBounds.getEast(), viewportBounds.getNorth()],
          selected_site: location, imagery: { provider: 'NASA EOSDIS GIBS', product: 'MODIS Terra TrueColor', day: date, resolution: 'context_only' },
          source_status: context.sources, context_observed_at: context.timestamp,
          counts: { aircraft: context.aircraft.length, ships: context.ships.length, earthquakes: context.earthquakes.length },
          evidence_status: 'unverified_context_only',
        },
      });
      setMessage(`Vista #${entry.id} guardada en Tezcatlipoca. Vinculación al expediente Workspace pendiente de implementar.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo guardar la vista');
    } finally {
      setSaving(false);
    }
  }, [context, date, dirty, layers, location]);

  const sources = context?.sources as Record<string, SourceState> | undefined;
  return (
    <div className="flex h-full min-h-[580px] flex-col gap-3 overflow-auto lg:flex-row">
      <div className="relative min-h-[430px] flex-1 overflow-hidden rounded-xl border" style={{ borderColor: 'var(--border-subtle)', background: '#08121b' }}>
        <div ref={container} className="absolute inset-0" aria-label="Mapa de contexto geoespacial Tezcatlipoca" />
        <div className="absolute left-3 top-3 z-10 rounded-lg border bg-[#090f19]/90 p-3 text-xs text-slate-100 backdrop-blur" style={{ borderColor: '#24344a' }}>
          <div className="mb-2 flex items-center gap-1.5 font-semibold"><Satellite size={14}/> NASA · Terra / imagen diaria</div>
          <label className="flex items-center gap-2 text-[11px] text-slate-300">
            <CalendarDays size={13}/> Fecha de imagen
            <input type="date" max={yesterdayUTC()} value={date}
              onChange={e => { const value = safeDate(e.target.value); if (value) setDate(value); }}
              className="rounded bg-slate-900 px-1.5 py-1 text-white" />
          </label>
          <p className="mt-2 max-w-[230px] text-[10px] leading-4 text-slate-400">
            Contexto satelital de baja resolución, NO Street View ni imagen en vivo.
          </p>
        </div>
        {selected && (
          <div className="absolute bottom-12 left-3 z-10 max-w-[270px] rounded-lg border border-slate-600 bg-[#080e17]/95 p-3 text-xs text-white">
            <strong>{selected.title}</strong>
            <p className="mt-1">Fuente: {selected.provider}</p>
            <p className="text-slate-400">Observado: {selected.observed}</p>
          </div>
        )}
        <div className="absolute bottom-2 left-3 z-10 rounded bg-[#0a1019]/90 px-2 py-1 text-[10px] text-slate-300">
          EPSG:4326 · {location.lat.toFixed(5)}, {location.lon.toFixed(5)}
        </div>
      </div>
      <aside className="w-full shrink-0 space-y-3 rounded-xl border p-4 lg:w-[316px]" style={{ borderColor: 'var(--border-subtle)', background: 'var(--surface)' }}>
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold"><Globe2 size={17}/> Explorador terrestre</h2>
          <p className="mt-1 text-[11px]" style={{ color: 'var(--text-muted)' }}>Selecciona una región, consulta las fuentes y guarda el estado verificable.</p>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <label className="text-[11px]">Latitud<input aria-label="Latitud de destino" type="number" step="any" value={inputLat} onChange={e => setInputLat(e.target.value)} className="mt-1 w-full rounded-md border p-2 text-xs" style={{ background: 'var(--surface-elevated)', borderColor: 'var(--border-subtle)' }}/></label>
          <label className="text-[11px]">Longitud<input aria-label="Longitud de destino" type="number" step="any" value={inputLon} onChange={e => setInputLon(e.target.value)} className="mt-1 w-full rounded-md border p-2 text-xs" style={{ background: 'var(--surface-elevated)', borderColor: 'var(--border-subtle)' }}/></label>
        </div>
        <button onClick={explore} className="flex w-full items-center justify-center gap-2 rounded-md border px-3 py-2 text-xs" style={{ borderColor: 'var(--border-subtle)' }}><Crosshair size={14}/> Ir a coordenadas</button>
        <div className="space-y-2 border-t pt-3" style={{ borderColor: 'var(--border-subtle)' }}>
          <p className="flex items-center gap-1.5 text-xs font-medium"><ScanSearch size={15}/> Capas observadas</p>
          {LAYER_META.map(l => <button key={l.id} onClick={() => setLayers(s => ({ ...s, [l.id]: !s[l.id] }))}
            className="flex w-full items-center justify-between rounded px-2 py-1.5 text-xs" aria-pressed={layers[l.id]}
            style={{ background: 'var(--surface-elevated)' }}>
            <span className="flex items-center gap-2"><span className="h-2 w-2 rounded-full" style={{ background: l.color }}/>{l.label}</span>
            {layers[l.id] ? <Eye size={13}/> : <EyeOff size={13}/>}
          </button>)}
          <button onClick={() => void refresh()} disabled={!ready || querying} className="flex w-full items-center justify-center gap-2 rounded-md px-3 py-2 text-xs font-semibold disabled:opacity-50"
            style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}><Database size={14}/>{querying ? 'Consultando…' : dirty ? 'Consultar esta región' : 'Volver a consultar'}</button>
        </div>
        {context && (
          <div className="space-y-1 rounded-lg p-2 text-[11px]" style={{ background: 'var(--surface-elevated)' }}>
            <p className="font-medium">Consulta · {new Date(context.timestamp).toLocaleString('es-MX')}</p>
            <p>{context.earthquakes.length} sismos · {context.aircraft.length} aeronaves · {context.ships.length} barcos</p>
            <p>ADSB.lol: {statusLabel(sources?.adsb_lol)}</p>
            <p>AIS: {statusLabel(sources?.ais)}</p>
            <p>USGS: {statusLabel(sources?.usgs)}</p>
            {dirty && <p className="text-amber-300">Mapa desplazado: los resultados pertenecen a la región anterior.</p>}
          </div>
        )}
        <div className="space-y-2 border-t pt-3 text-xs" style={{ borderColor: 'var(--border-subtle)' }}>
          <p className="font-semibold">Meteorología mundial · ECMWF IFS</p>
          <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>Pronóstico por rejilla; requiere datos GRIB abiertos procesados en infraestructura propia.</p>
          <button onClick={() => void loadWeather()} disabled={loadingWeather} className="w-full rounded-md border px-3 py-2 disabled:opacity-50" style={{ borderColor: 'var(--border-subtle)' }}>
            {loadingWeather ? 'Consultando…' : 'Consultar pronóstico de la ubicación'}
          </button>
          {weather && <div role="status" className="rounded-md p-2" style={{ background: 'var(--surface-elevated)' }}>
            <p>Estado: {weather.status}</p>
            {weather.status === 'available'
              ? <><p>Temperatura 2 m: {weather.temperature_2m_c} °C</p><p>Viento 10 m: {weather.wind_10m_ms} m/s</p><p>Válido: {weather.valid_time}</p><p>{weather.attribution}</p></>
              : <p>{weather.reason || 'Datos locales no disponibles para esta ubicación.'}</p>}
          </div>}
        </div>
        {error && <p role="alert" className="rounded-md bg-red-950/40 p-2 text-xs text-red-300">{error}</p>}
        {message && <p role="status" className="text-xs" style={{ color: 'var(--text-secondary)' }}>{message}</p>}
        <button onClick={() => void save()} disabled={!context || dirty || saving}
          className="flex w-full items-center justify-center gap-2 rounded-md border px-3 py-2 text-xs disabled:opacity-50"
          style={{ borderColor: 'var(--border-subtle)' }}><Save size={14}/>{saving ? 'Guardando…' : 'Guardar vista en Tezcatlipoca'}</button>
        <button onClick={() => abrirModulo('rastreo-orbital')} className="w-full rounded-md border px-3 py-2 text-xs" style={{ borderColor: 'var(--border-subtle)' }}>
          Ver motor orbital 3D
        </button>
        <p className="text-[10px] leading-4" style={{ color: 'var(--text-muted)' }}>
          Las posiciones están sujetas a disponibilidad, actualización y licencias. Las capturas guardadas no son por sí mismas levantamientos ni evidencia aprobada en Workspace.
        </p>
      </aside>
    </div>
  );
}
