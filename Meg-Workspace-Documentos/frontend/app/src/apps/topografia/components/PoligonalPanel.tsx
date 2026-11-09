/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */
import { useEffect, useState } from 'react';
import { Plus, Trash2, Loader2, AlertCircle, CheckCircle2, XCircle, Hexagon } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';
import type { ResultadoCierrePoligonal, Levantamiento, PuntoTopografico } from '@/lib/megalodon-client';

function inputCls(): React.CSSProperties {
  return { background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-primary)' };
}

type Vertice = { puntoId?: string; x: string; y: string };

export default function PoligonalPanel({ levantamiento }: { levantamiento: Levantamiento | null }) {
  const [puntosDisponibles, setPuntosDisponibles] = useState<PuntoTopografico[]>([]);
  const [vertices, setVertices] = useState<Vertice[]>([{ x: '', y: '' }, { x: '', y: '' }, { x: '', y: '' }]);
  const [calculando, setCalculando] = useState(false);
  const [error, setError] = useState('');
  const [resultado, setResultado] = useState<ResultadoCierrePoligonal | null>(null);

  useEffect(() => {
    if (!levantamiento) { setPuntosDisponibles([]); return; }
    megalodonClient.topografia.listarPuntos(levantamiento.id).then(setPuntosDisponibles).catch(() => setPuntosDisponibles([]));
  }, [levantamiento]);

  const elegirPunto = (i: number, puntoId: string) => {
    const p = puntosDisponibles.find((pt) => pt.id === puntoId);
    setVertices((prev) => prev.map((v, idx) => (idx === i ? { puntoId, x: p ? String(p.x) : v.x, y: p ? String(p.y) : v.y } : v)));
  };
  const setManual = (i: number, eje: 0 | 1, valor: string) => {
    setVertices((prev) => prev.map((v, idx) => (idx === i ? { puntoId: undefined, x: eje === 0 ? valor : v.x, y: eje === 1 ? valor : v.y } : v)));
  };

  const validos = vertices.filter((v) => v.x.trim() !== '' && v.y.trim() !== '');

  const calcular = async () => {
    if (validos.length < 3) return;
    setCalculando(true); setError(''); setResultado(null);
    try {
      const puntos: [number, number][] = validos.map((v) => [Number(v.x), Number(v.y)]);
      const r = await megalodonClient.topografia.cierrePoligonal(puntos);
      setResultado(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo calcular el cierre poligonal');
    } finally {
      setCalculando(false);
    }
  };

  return (
    <div className="h-full overflow-auto p-4">
      <div className="max-w-xl mx-auto space-y-4">
        <div className="flex items-center gap-2">
          <Hexagon size={16} style={{ color: 'var(--accent-gold)' }} />
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            {puntosDisponibles.length > 0 ? 'Elige los vértices de la poligonal por punto real, en orden (o captura X/Y a mano).' : 'Captura los vértices de la poligonal (X/Y en el CRS local del levantamiento) en orden.'}
          </p>
        </div>

        <div className="space-y-1.5">
          {vertices.map((v, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className="w-6 text-[11px] text-right" style={{ color: 'var(--text-muted)' }}>{i + 1}</span>
              {puntosDisponibles.length > 0 && (
                <select value={v.puntoId || ''} onChange={(e) => e.target.value && elegirPunto(i, e.target.value)} className="h-8 rounded px-2 text-xs outline-hidden" style={inputCls()}>
                  <option value="">— punto —</option>
                  {puntosDisponibles.map((p) => <option key={p.id} value={p.id}>{p.identificador}</option>)}
                </select>
              )}
              <input value={v.x} onChange={(e) => setManual(i, 0, e.target.value)} type="number" placeholder="Este (X)" className="flex-1 h-8 rounded px-2 text-xs outline-hidden font-mono" style={inputCls()} />
              <input value={v.y} onChange={(e) => setManual(i, 1, e.target.value)} type="number" placeholder="Norte (Y)" className="flex-1 h-8 rounded px-2 text-xs outline-hidden font-mono" style={inputCls()} />
              <button onClick={() => setVertices((prev) => prev.filter((_, idx) => idx !== i))} disabled={vertices.length <= 3} className="text-xs disabled:opacity-30" style={{ color: 'var(--danger)' }}><Trash2 size={13} /></button>
            </div>
          ))}
        </div>

        <div className="flex gap-2">
          <button onClick={() => setVertices((prev) => [...prev, { x: '', y: '' }])} className="flex items-center gap-1.5 h-8 px-3 rounded text-xs" style={{ border: '1px solid var(--border-active)', color: 'var(--text-secondary)' }}>
            <Plus size={13} /> Agregar vértice
          </button>
          <button
            onClick={() => void calcular()}
            disabled={calculando || validos.length < 3}
            className="flex-1 h-8 rounded text-xs font-semibold flex items-center justify-center gap-1.5 disabled:opacity-40"
            style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}
          >
            {calculando ? <Loader2 size={13} className="animate-spin" /> : null} Calcular cierre ({validos.length} vértices)
          </button>
        </div>

        {error && <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--danger)' }}><AlertCircle size={13} />{error}</div>}

        {resultado && (
          <div
            className="rounded-lg p-4 space-y-2"
            style={{ background: 'var(--surface-elevated)', border: `1px solid ${resultado.dentro_tolerancia ? 'var(--success)' : 'var(--danger)'}44` }}
          >
            <div className="flex items-center gap-2">
              {resultado.dentro_tolerancia
                ? <CheckCircle2 size={16} style={{ color: 'var(--success)' }} />
                : <XCircle size={16} style={{ color: 'var(--danger)' }} />}
              <span className="text-sm font-semibold" style={{ color: resultado.dentro_tolerancia ? 'var(--success)' : 'var(--danger)' }}>
                {resultado.dentro_tolerancia ? 'Dentro de tolerancia' : 'Fuera de tolerancia'}
              </span>
            </div>
            <div className="grid grid-cols-3 gap-3 text-xs pt-1">
              <div><p style={{ color: 'var(--text-muted)' }}>Error de cierre</p><p className="font-mono" style={{ color: 'var(--text-primary)' }}>{resultado.error_cierre_m.toFixed(4)} m</p></div>
              <div><p style={{ color: 'var(--text-muted)' }}>Perímetro</p><p className="font-mono" style={{ color: 'var(--text-primary)' }}>{resultado.perimetro_m.toFixed(2)} m</p></div>
              <div><p style={{ color: 'var(--text-muted)' }}>Precisión</p><p className="font-mono" style={{ color: 'var(--text-primary)' }}>{resultado.precision_relativa}</p></div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
