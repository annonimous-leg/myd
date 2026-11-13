import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { Activity, Database, Globe2, Layers3, RefreshCw, Satellite, Search, ShieldAlert } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';
import { abrirModulo } from '@/lib/navigation';
import type { ContextoGeoTez } from '@/lib/megalodon-client';
import { observationsFromContext, providerStatus } from './intelligence-data';
import type { ProviderInfo } from './intelligence-data';
import IntelligenceCenter from './IntelligenceCenter';

// Do not load MapLibre, its worker, or the NASA basemap on the corporate landing screen.
// The orbital Three.js module is an entirely separate lazy app in CommandCenter.
const GeoExplorer = lazy(() => import('./GeoExplorer'));

type Tab = 'overview' | 'territory' | 'geo' | 'osint' | 'cyber' | 'sar' | 'telemetry';
const TABS = [
  { id: 'overview' as const, label: 'Centro', Icon: Layers3 },
  { id: 'territory' as const, label: 'Tierra', Icon: Globe2 },
  { id: 'geo' as const, label: 'Datos', Icon: Database },
  { id: 'osint' as const, label: 'OSINT', Icon: Search },
  { id: 'cyber' as const, label: 'Cyber', Icon: ShieldAlert },
  { id: 'sar' as const, label: 'SAR', Icon: Satellite },
  { id: 'telemetry' as const, label: 'Telemetría', Icon: Activity },
];

function short(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'No informado';
  if (typeof value === 'string') return value.length > 200 ? value.slice(0, 197) + '…' : value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) return String(value.length) + ' registros';
  return 'Objeto de datos';
}

function DataInspector({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (Array.isArray(value)) {
    if (value.length === 0) return <p className="text-xs" style={{ color: 'var(--text-muted)' }}>No hay registros recibidos.</p>;
    return <div className="space-y-2">
      {value.slice(0, 15).map((item, index) => (
        <div className="rounded-md border p-2 text-xs" key={index} style={{ borderColor: 'var(--border-subtle)' }}>
          {depth < 2 && item !== null && typeof item === 'object' ? <DataInspector value={item} depth={depth + 1}/> : short(item)}
        </div>
      ))}
      {value.length > 15 && <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Mostrando 15 de {value.length} registros.</p>}
    </div>;
  }
  if (value !== null && typeof value === 'object') {
    const fields = Object.entries(value as Record<string, unknown>);
    return <div className="space-y-2">
      {fields.slice(0, 40).map(([key, item]) => (
        <div className="grid gap-1 border-b pb-2 sm:grid-cols-[minmax(125px,0.35fr)_1fr]" key={key} style={{ borderColor: 'var(--border-subtle)' }}>
          <span className="text-xs font-medium">{key.replace(/_/g, ' ')}</span>
          <div className="min-w-0 break-words text-xs" style={{ color: 'var(--text-secondary)' }}>
            {depth < 2 && item !== null && typeof item === 'object' ? <DataInspector value={item} depth={depth + 1}/> : short(item)}
          </div>
        </div>
      ))}
      {fields.length > 40 && <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Respuesta truncada a 40 campos.</p>}
    </div>;
  }
  return <p className="text-xs">{short(value)}</p>;
}

export default function TezcatlipocaHub() {
  const [tab, setTab] = useState<Tab>('overview');
  const [data, setData] = useState<unknown>(null);
  const [query, setQuery] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [receivedAt, setReceivedAt] = useState<string | null>(null);
  const requestId = useRef(0);

  const load = useCallback(async () => {
    if (tab === 'overview' || tab === 'territory') return;
    if (tab === 'osint' && !query.trim()) return;
    const id = ++requestId.current;
    setBusy(true);
    setError('');
    setData(null);
    setReceivedAt(null);
    try {
      let result: unknown;
      if (tab === 'geo') result = await megalodonClient.tezcatlipoca.geoContext();
      else if (tab === 'osint') result = await megalodonClient.tezcatlipoca.osintLookup(query.trim());
      else if (tab === 'cyber') result = await megalodonClient.tezcatlipoca.cyberCisaStats();
      else if (tab === 'sar') result = await megalodonClient.tezcatlipoca.sarScenes();
      else result = await megalodonClient.tezcatlipoca.telemetry();
      if (id !== requestId.current) return;
      setData(result);
      setReceivedAt(new Date().toISOString());
    } catch (cause) {
      if (id !== requestId.current) return;
      const message = cause instanceof Error ? cause.message : 'La consulta no pudo completarse';
      setError(/403|Forbidden|Required role/i.test(message) ? 'Tu rol no tiene permiso para consultar este módulo.' : message);
    } finally {
      if (id === requestId.current) setBusy(false);
    }
  }, [tab, query]);

  useEffect(() => {
    requestId.current += 1;
    setData(null);
    setReceivedAt(null);
    setBusy(false);
    setError('');
    if (tab !== 'overview' && tab !== 'territory' && tab !== 'osint') void load();
    return () => { requestId.current += 1; };
  }, [tab, load]);

  const response = data !== null && typeof data === 'object' ? data as Record<string, unknown> : null;
  const geo = tab === 'geo' && response ? data as ContextoGeoTez : null;
  const observations = observationsFromContext(geo);
  const scenes = tab === 'sar' && response && Array.isArray(response.scenes) ? response.scenes as Record<string, unknown>[] : [];
  const activeLayers = tab === 'telemetry' && response && Array.isArray(response.active_layers) ? response.active_layers as unknown[] : [];

  return (
    <div className="h-full w-full overflow-y-auto p-4 md:p-5" style={{ background: 'var(--void)', color: 'var(--text-primary)' }}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Tezcatlipoca · Hub Operacional</h1>
          <p className="mt-1 text-xs" style={{ color: 'var(--text-muted)' }}>Inteligencia geoespacial verificable · identidad y permisos de MEGALODON</p>
        </div>
        {tab !== 'overview' && tab !== 'territory' && (
          <button onClick={() => void load()} type="button" disabled={busy || (tab === 'osint' && !query.trim())}
            className="flex items-center gap-2 rounded-md px-3 py-2 text-xs disabled:opacity-50"
            style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}>
            <RefreshCw size={13} className={busy ? 'animate-spin' : ''}/>{busy ? 'Consultando…' : 'Actualizar consulta'}
          </button>
        )}
      </div>
      <nav aria-label="Secciones de Tezcatlipoca" className="mb-4 grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-7">
        {TABS.map(({id,label,Icon}) => (
          <button key={id} type="button" onClick={() => setTab(id)} aria-current={tab === id ? 'page' : undefined}
            className="rounded-lg border p-3 text-left text-xs"
            style={{ background: tab === id ? 'var(--surface-elevated)' : 'var(--surface)', borderColor: tab === id ? 'var(--accent-gold-dim)' : 'var(--border-subtle)' }}>
            <Icon size={15} style={{ color: 'var(--accent-gold)' }}/><span className="mt-2 block">{label}</span>
          </button>
        ))}
      </nav>
      {tab === 'overview' && <IntelligenceCenter onOpenMap={() => setTab('territory')} onOpenOrbit={() => abrirModulo('rastreo-orbital')}/>}
      {tab === 'territory' && <Suspense fallback={<p className="p-5 text-xs" role="status">Cargando mapa terrestre 2D…</p>}><GeoExplorer/></Suspense>}
      {tab === 'osint' && (
        <form onSubmit={event => { event.preventDefault(); void load(); }} className="mb-4 flex flex-wrap gap-2">
          <label className="sr-only" htmlFor="tez-osint-target">Entidad, IP, dominio o CVE</label>
          <input id="tez-osint-target" value={query} onChange={event => setQuery(event.target.value)}
            placeholder="IP, dominio, CVE o entidad" className="min-w-[220px] flex-1 rounded-md border px-3 py-2 text-xs"
            style={{ background: 'var(--surface)', borderColor: 'var(--border-subtle)' }}/>
          <button type="submit" disabled={busy || !query.trim()} className="rounded-md border px-4 py-2 text-xs disabled:opacity-50" style={{ borderColor: 'var(--border-subtle)' }}>Consultar</button>
        </form>
      )}
      {error && <p role="alert" className="mb-4 rounded-md border p-3 text-xs" style={{ color: 'var(--danger)', borderColor: 'var(--border-subtle)' }}>{error}</p>}
      {tab !== 'overview' && tab !== 'territory' && (
        <section className="rounded-xl border p-4" style={{ background: 'var(--surface)', borderColor: 'var(--border-subtle)' }}>
          <div className="mb-4 flex flex-wrap justify-between gap-2">
            <h2 className="text-sm font-semibold">{TABS.find(t => t.id === tab)?.label} · resultados</h2>
            {receivedAt && <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>Respuesta recibida: {new Date(receivedAt).toLocaleString('es-MX')}</span>}
          </div>
          {busy ? <p role="status" className="text-xs">Consultando el backend…</p>
            : data === null ? <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{tab === 'osint' ? 'Introduce un objetivo para consultar. No se ejecutan búsquedas automáticamente.' : 'Sin resultados consultados.'}</p>
              : tab === 'geo' && geo ? (
                <div className="space-y-4">
                  <div className="grid gap-2 sm:grid-cols-3">
                    {([
                      ['Sismos', 'earthquake'], ['Aeronaves', 'aircraft'], ['Barcos', 'ship'],
                    ] as const).map(([label,kind]) => (
                      <div key={kind} className="rounded-md border p-3 text-xs" style={{ borderColor: 'var(--border-subtle)' }}>
                        <strong>{label}</strong><p className="mt-1 text-xl">{observations.filter(row => row.kind === kind).length}</p>
                      </div>
                    ))}
                  </div>
                  <div className="grid gap-2 sm:grid-cols-3">
                    {([
                      ['USGS', geo.sources.usgs], ['ADSB.lol', geo.sources.adsb_lol], ['AIS', geo.sources.ais],
                    ] as const).map(([label,info]) => <p key={label} className="rounded-md border p-2 text-xs" style={{ borderColor: 'var(--border-subtle)' }}>
                      {label}: {providerStatus(info as ProviderInfo | undefined, true)}
                    </p>)}
                  </div>
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Consulta de cobertura global del endpoint existente: un proveedor con cobertura regional puede no aportar datos. Para análisis de una zona utiliza Centro o Tierra.</p>
                </div>
              ) : tab === 'sar' ? (
                <div className="space-y-2">
                  {scenes.length === 0 ? <p className="text-xs" style={{ color: 'var(--text-muted)' }}>No hay escenas recibidas o la fuente requiere configuración. No equivale a una imagen SAR procesada.</p>
                    : scenes.slice(0, 50).map((scene, i) => (
                      <div key={String(scene.id ?? i)} className="grid gap-2 rounded-md border p-3 text-xs sm:grid-cols-4" style={{ borderColor: 'var(--border-subtle)' }}>
                        <span>{short(scene.id)}</span><span>{short(scene.platform)}</span><span>{short(scene.date)}</span><span>{short(scene.provider)}</span>
                      </div>
                    ))}
                </div>
              ) : tab === 'telemetry' && response ? (
                <div className="space-y-3 text-xs">
                  <p>Motor: <strong>{short(response.status)}</strong> · Entradas en caché: <strong>{short(response.sources)}</strong></p>
                  <p style={{ color: 'var(--text-muted)' }}>Un motor iniciado o una clave en caché no certifica que cada fuente esté operativa o actualizada.</p>
                  <div className="flex flex-wrap gap-2">{activeLayers.map((layer,i) => <span key={i} className="rounded-md border px-2 py-1" style={{ borderColor: 'var(--border-subtle)' }}>{short(layer)}</span>)}</div>
                </div>
              ) : tab === 'cyber' || tab === 'osint' ? (
                <DataInspector value={data}/>
              ) : <DataInspector value={data}/>}
        </section>
      )}
    </div>
  );
}
