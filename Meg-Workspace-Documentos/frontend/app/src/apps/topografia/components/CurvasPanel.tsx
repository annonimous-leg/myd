/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */
import { useState } from 'react';
import { Loader2, AlertCircle, Play, Waves } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';
import type { SuperficieTIN } from '@/lib/megalodon-client';

function inputCls(): React.CSSProperties {
  return { background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-primary)' };
}

export default function CurvasPanel({ superficies }: { superficies: SuperficieTIN[] }) {
  const [superficieId, setSuperficieId] = useState('');
  const [intervalo, setIntervalo] = useState('1');
  const [curvas, setCurvas] = useState<Record<string, [number, number][][]> | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState('');

  const generar = async () => {
    if (!superficieId) return;
    setCargando(true); setError(''); setCurvas(null);
    try {
      const r = await megalodonClient.topografia.curvasNivel(superficieId, Number(intervalo) || 1);
      setCurvas(r.curvas);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo generar las curvas de nivel');
    } finally {
      setCargando(false);
    }
  };

  const entradas = curvas ? Object.entries(curvas) : [];
  const todasLasLineas = entradas.flatMap(([elev, lineas]) => lineas.map((l) => ({ elev: Number(elev), l })));
  const xs = todasLasLineas.flatMap((e) => e.l.map((p) => p[0]));
  const ys = todasLasLineas.flatMap((e) => e.l.map((p) => p[1]));
  const minX = Math.min(...xs, 0), maxX = Math.max(...xs, 1);
  const minY = Math.min(...ys, 0), maxY = Math.max(...ys, 1);
  const pad = Math.max(maxX - minX, maxY - minY) * 0.05 || 1;
  const elevMin = Math.min(...entradas.map(([e]) => Number(e)), 0);
  const elevMax = Math.max(...entradas.map(([e]) => Number(e)), 1);

  return (
    <div className="h-full flex">
      <div className="w-64 shrink-0 p-3 space-y-3 overflow-y-auto" style={{ borderRight: '1px solid var(--border-subtle)', background: 'var(--surface)' }}>
        <select value={superficieId} onChange={(e) => setSuperficieId(e.target.value)} className="w-full h-8 rounded px-2 text-xs outline-hidden" style={inputCls()}>
          <option value="">Superficie</option>
          {superficies.map((s) => <option key={s.id} value={s.id}>{s.nombre}</option>)}
        </select>
        <div>
          <label className="text-[11px]" style={{ color: 'var(--text-muted)' }}>Equidistancia (m)</label>
          <input value={intervalo} onChange={(e) => setIntervalo(e.target.value)} type="number" step="0.5" min="0.1" className="w-full h-8 rounded px-2 text-xs outline-hidden font-mono" style={inputCls()} />
        </div>
        <button onClick={() => void generar()} disabled={!superficieId || cargando} className="w-full flex items-center justify-center gap-1.5 h-8 rounded text-xs font-semibold disabled:opacity-40" style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}>
          {cargando ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />} Generar curvas
        </button>
        {error && <div className="flex items-start gap-1.5 text-[11px]" style={{ color: 'var(--danger)' }}><AlertCircle size={12} className="mt-0.5" />{error}</div>}
        {curvas && (
          <div className="text-[11px] space-y-1 pt-2" style={{ borderTop: '1px solid var(--border-subtle)', color: 'var(--text-muted)' }}>
            <p>{entradas.length} niveles · {todasLasLineas.length} polilíneas</p>
            <p>{elevMin.toFixed(1)}–{elevMax.toFixed(1)} m</p>
          </div>
        )}
      </div>

      <div className="flex-1 relative" style={{ background: '#05050a' }}>
        {!curvas ? (
          <div className="h-full flex flex-col items-center justify-center gap-2 text-sm text-center" style={{ color: 'var(--text-muted)' }}>
            <Waves className="w-8 h-8 opacity-40" /> Selecciona una superficie y genera las curvas de nivel reales.
          </div>
        ) : (
          <svg viewBox={`${minX - pad} ${minY - pad} ${maxX - minX + pad * 2} ${maxY - minY + pad * 2}`} className="w-full h-full" preserveAspectRatio="xMidYMid meet">
            <g transform={`scale(1,-1) translate(0, ${-(minY + maxY)})`}>
              {todasLasLineas.map(({ elev, l }, i) => {
                const t = (elev - elevMin) / Math.max(0.01, elevMax - elevMin);
                const maestra = i % 5 === 0;
                const color = `hsl(${40 + t * 60}, ${maestra ? 70 : 45}%, ${maestra ? 55 : 40}%)`;
                return (
                  <polyline
                    key={i}
                    points={l.map((p) => p.join(',')).join(' ')}
                    fill="none"
                    stroke={color}
                    strokeWidth={(maestra ? 1.6 : 0.7) * (pad / 20 || 1)}
                    vectorEffect="non-scaling-stroke"
                  />
                );
              })}
            </g>
          </svg>
        )}
      </div>
    </div>
  );
}
