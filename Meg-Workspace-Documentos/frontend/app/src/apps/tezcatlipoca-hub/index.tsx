import { useEffect, useMemo, useState } from 'react';
import { Globe2, Search, ShieldAlert, Satellite, RefreshCw, Activity } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';

type Tab = 'geo' | 'osint' | 'cyber' | 'sar' | 'telemetry';

export default function TezcatlipocaHub() {
  const [tab, setTab] = useState<Tab>('geo');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [data, setData] = useState<any>(null);
  const [query, setQuery] = useState('');

  const load = async () => {
    setLoading(true); setError('');
    try {
      if (tab === 'geo') setData(await megalodonClient.tezcatlipoca.geoContext());
      else if (tab === 'telemetry') setData(await megalodonClient.tezcatlipoca.telemetry());
      else if (tab === 'cyber') setData(await megalodonClient.tezcatlipoca.cyberCisaStats());
      else if (tab === 'sar') setData(await megalodonClient.tezcatlipoca.sarScenes());
      else if (tab === 'osint' && query.trim()) setData(await megalodonClient.tezcatlipoca.osintLookup(query.trim()));
      else if (tab === 'osint') setData({ notice: 'Escribe una entidad, IP, dominio o CVE para consultar.' });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo consultar Tezcatlipoca');
      setData(null);
    } finally { setLoading(false); }
  };

  useEffect(() => { void load(); }, [tab]);

  const cards = useMemo(() => {
    if (tab === 'geo') return [
      ['Aeronaves', data?.aircraft?.length ?? 0],
      ['Embarcaciones', data?.ships?.length ?? 0],
      ['Sismos', data?.earthquakes?.length ?? 0],
    ];
    if (tab === 'telemetry') return [
      ['Estado', data?.status ?? '—'],
      ['Fuentes', data?.sources ?? 0],
      ['Capas', data?.active_layers?.length ?? 0],
    ];
    return [['Respuesta', Array.isArray(data) ? data.length : data ? 1 : 0], ['Estado', data ? 'OK' : '—'], ['Actualización', data?.timestamp ?? '—']];
  }, [tab, data]);

  return (
    <div className="w-full h-full overflow-y-auto p-5" style={{ background: 'var(--void)', color: 'var(--text-primary)' }}>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-lg font-semibold">Tezcatlipoca · Hub Operacional</h1>
          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Geo, OSINT, Cyber, SAR y telemetría desde el mismo contexto de identidad Megalodon.</p>
        </div>
        <button onClick={load} disabled={loading} className="rounded-md px-3 py-2 text-xs flex items-center gap-2" style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}><RefreshCw size={13} className={loading ? 'animate-spin' : ''}/> Actualizar</button>
      </div>
      <div className="grid grid-cols-5 gap-2 mb-4">
        {([
          ['geo','Geo',Globe2],['osint','OSINT',Search],['cyber','Cyber',ShieldAlert],['sar','SAR',Satellite],['telemetry','Telemetría',Activity]
        ] as const).map(([id,label,Icon]) => (
          <button key={id} onClick={() => setTab(id)} className="rounded-lg p-3 text-left border" style={{ background: tab === id ? 'var(--surface-elevated)' : 'var(--surface)', borderColor: tab === id ? 'var(--accent-gold-dim)' : 'var(--border-subtle)' }}><Icon size={15} style={{ color: 'var(--accent-gold)' }}/><div className="text-xs mt-2">{label}</div></button>
        ))}
      </div>
      {tab === 'osint' && <div className="flex gap-2 mb-4"><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="IP, dominio, CVE o entidad" className="flex-1 rounded-md px-3 py-2 text-xs" style={{ background: 'var(--surface)', border: '1px solid var(--border-subtle)', color: 'var(--text-primary)' }}/><button onClick={load} className="rounded-md px-4 text-xs" style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}>Consultar</button></div>}
      {error && <div className="mb-4 rounded-md p-3 text-xs" style={{ background: 'var(--surface)', color: 'var(--danger)' }}>{error}</div>}
      <div className="grid grid-cols-3 gap-3 mb-4">{cards.map(([label,value]) => <div key={String(label)} className="rounded-lg p-4 border" style={{ background: 'var(--surface)', borderColor: 'var(--border-subtle)' }}><div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{label}</div><div className="text-xl font-semibold mt-1 break-all">{String(value)}</div></div>)}</div>
      <pre className="rounded-lg p-4 text-[11px] overflow-auto min-h-[320px]" style={{ background: '#07080c', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)' }}>{JSON.stringify(data, null, 2)}</pre>
    </div>
  );
}
