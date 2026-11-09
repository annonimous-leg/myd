/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

/**
 * Panel "Tezcatlipoca Feeds" — mismos datos reales que ya consultaba el
 * index.tsx viejo (megalodonClient.tezcatlipoca.geoContext), con la
 * presentación visual del mockup: badges de estado por fuente + contadores
 * en vivo. geoContext() sigue tipado `any` en el cliente (pendiente); aquí
 * se consume de forma defensiva con optional chaining.
 */
import { useCallback, useEffect, useState } from 'react';
import { Satellite, Plane, Ship, Activity, RefreshCw, Loader2, Radio } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';
import type { ContextoGeoTez } from '@/lib/megalodon-client';

interface BBox { latMin: string; latMax: string; lonMin: string; lonMax: string }

function estadoColor(status?: string): string {
  return status === 'available' || status === 'online' || status === 'cache' ? 'var(--success)' : 'var(--text-muted)';
}

export default function TezcatlipocaFeedPanel({ bbox }: { bbox?: BBox }) {
  const [contexto, setContexto] = useState<ContextoGeoTez | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState('');
  const [ultimaActualizacion, setUltimaActualizacion] = useState<Date | null>(null);

  const cargar = useCallback(async () => {
    setCargando(true); setError('');
    try {
      const hasBbox = bbox && Object.values(bbox).every((v) => v.trim() !== '');
      const context = await megalodonClient.tezcatlipoca.geoContext(hasBbox ? {
        latMin: Number(bbox!.latMin), latMax: Number(bbox!.latMax),
        lonMin: Number(bbox!.lonMin), lonMax: Number(bbox!.lonMax),
      } : undefined);
      setContexto(context);
      setUltimaActualizacion(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Tezcatlipoca no respondió');
    } finally {
      setCargando(false);
    }
  }, [bbox]);

  useEffect(() => { void cargar(); }, [cargar]);
  // Refresco automático cada 2 min mientras el panel esté montado — es el
  // elemento que justifica llamarlo "feed" y no una simple consulta.
  useEffect(() => {
    const id = setInterval(() => void cargar(), 120_000);
    return () => clearInterval(id);
  }, [cargar]);

  const fuentes = Object.entries(contexto?.sources ?? {});
  const conectadas = fuentes.filter(([, i]) => estadoColor(i?.status) === 'var(--success)').length;

  return (
    <div className="rounded-lg overflow-hidden" style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)' }}>
      <div className="flex items-center justify-between px-3 py-2" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        <span className="flex items-center gap-1.5 text-xs font-semibold" style={{ color: 'var(--accent-purple)' }}>
          <Satellite size={13} /> TEZCATLIPOCA
        </span>
        <button onClick={() => void cargar()} disabled={cargando} className="text-[10px] flex items-center gap-1" style={{ color: 'var(--text-muted)' }}>
          {cargando ? <Loader2 size={10} className="animate-spin" /> : <RefreshCw size={10} />}
        </button>
      </div>

      {error ? (
        <p className="px-3 py-2 text-[11px]" style={{ color: 'var(--danger)' }}>{error}</p>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-1.5 p-2">
            <div className="rounded p-1.5 text-center" style={{ background: 'var(--surface)' }}>
              <Plane size={12} className="mx-auto mb-0.5" style={{ color: 'var(--accent-cyan)' }} />
              <div className="text-sm font-mono" style={{ color: 'var(--text-primary)' }}>{contexto?.aircraft?.length ?? '—'}</div>
              <div className="text-[9px]" style={{ color: 'var(--text-muted)' }}>aeronaves</div>
            </div>
            <div className="rounded p-1.5 text-center" style={{ background: 'var(--surface)' }}>
              <Ship size={12} className="mx-auto mb-0.5" style={{ color: 'var(--accent-cyan)' }} />
              <div className="text-sm font-mono" style={{ color: 'var(--text-primary)' }}>{contexto?.ships?.length ?? '—'}</div>
              <div className="text-[9px]" style={{ color: 'var(--text-muted)' }}>barcos</div>
            </div>
            <div className="rounded p-1.5 text-center" style={{ background: 'var(--surface)' }}>
              <Activity size={12} className="mx-auto mb-0.5" style={{ color: 'var(--amber)' }} />
              <div className="text-sm font-mono" style={{ color: 'var(--text-primary)' }}>{contexto?.earthquakes?.length ?? '—'}</div>
              <div className="text-[9px]" style={{ color: 'var(--text-muted)' }}>sismos</div>
            </div>
          </div>

          <div className="px-2 pb-2 space-y-1">
            {fuentes.map(([nombre, info]) => (
              <div key={nombre} className="flex items-center justify-between px-1.5 py-1 rounded text-[10px]" style={{ background: 'var(--surface)' }}>
                <span className="flex items-center gap-1.5" style={{ color: 'var(--text-secondary)' }}>
                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: estadoColor(info?.status), boxShadow: estadoColor(info?.status) === 'var(--success)' ? `0 0 4px var(--success)` : 'none' }} />
                  {nombre}
                </span>
                <span style={{ color: estadoColor(info?.status) }}>{String(info?.status ?? '—')}</span>
              </div>
            ))}
            {fuentes.length === 0 && !cargando && <p className="text-[10px] px-1.5" style={{ color: 'var(--text-muted)' }}>Sin fuentes reportadas.</p>}
          </div>

          <div className="flex items-center justify-between px-3 py-1.5 text-[9px]" style={{ borderTop: '1px solid var(--border-subtle)', color: 'var(--text-muted)' }}>
            <span className="flex items-center gap-1">
              <Radio size={9} style={{ color: conectadas > 0 ? 'var(--success)' : 'var(--text-muted)' }} />
              {conectadas}/{fuentes.length || 0} conectadas
            </span>
            {ultimaActualizacion && <span>{ultimaActualizacion.toLocaleTimeString('es-MX')}</span>}
          </div>
        </>
      )}
    </div>
  );
}
