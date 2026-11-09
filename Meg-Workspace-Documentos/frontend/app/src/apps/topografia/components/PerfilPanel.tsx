/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */
import { useEffect, useState } from 'react';
import { Loader2, AlertCircle, Play, TrendingUp } from 'lucide-react';
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts';
import { megalodonClient } from '@/lib/api-client';
import type { SuperficieTIN, PuntoPerfil, Levantamiento, PuntoTopografico } from '@/lib/megalodon-client';

function inputCls(): React.CSSProperties {
  return { background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-primary)' };
}

export default function PerfilPanel({ superficies, levantamiento }: { superficies: SuperficieTIN[]; levantamiento: Levantamiento | null }) {
  const [superficieId, setSuperficieId] = useState('');
  const [puntos, setPuntosLevantamiento] = useState<PuntoTopografico[]>([]);
  const [puntoInicioId, setPuntoInicioId] = useState('');
  const [puntoFinId, setPuntoFinId] = useState('');
  const [manual, setManual] = useState(false);
  const [eje, setEje] = useState({ x1: '', y1: '', x2: '', y2: '' });
  const [intervalo, setIntervalo] = useState('5');
  const [perfil, setPerfil] = useState<PuntoPerfil[] | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!levantamiento) { setPuntosLevantamiento([]); return; }
    megalodonClient.topografia.listarPuntos(levantamiento.id).then(setPuntosLevantamiento).catch(() => setPuntosLevantamiento([]));
  }, [levantamiento]);

  const puntoInicio = puntos.find((p) => p.id === puntoInicioId);
  const puntoFin = puntos.find((p) => p.id === puntoFinId);
  const ejeFinal: [number, number][] | null = manual
    ? (eje.x1 && eje.y1 && eje.x2 && eje.y2 ? [[Number(eje.x1), Number(eje.y1)], [Number(eje.x2), Number(eje.y2)]] : null)
    : (puntoInicio && puntoFin ? [[puntoInicio.x, puntoInicio.y], [puntoFin.x, puntoFin.y]] : null);

  const listo = superficieId && ejeFinal;

  const generar = async () => {
    if (!listo || !ejeFinal) return;
    setCargando(true); setError(''); setPerfil(null);
    try {
      const r = await megalodonClient.topografia.generarPerfil(superficieId, ejeFinal, Number(intervalo) || 5);
      setPerfil(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo generar el perfil');
    } finally {
      setCargando(false);
    }
  };

  const pendienteMax = perfil && perfil.length > 1
    ? Math.max(...perfil.slice(1).map((p, i) => Math.abs((p.elevacion - perfil[i].elevacion) / Math.max(0.01, p.cadenamiento - perfil[i].cadenamiento)) * 100))
    : null;

  return (
    <div className="h-full overflow-auto p-4">
      <div className="max-w-3xl mx-auto space-y-4">
        <div className="flex items-center gap-2 flex-wrap">
          <select value={superficieId} onChange={(e) => setSuperficieId(e.target.value)} className="h-8 rounded px-2 text-xs outline-hidden" style={inputCls()}>
            <option value="">Superficie</option>
            {superficies.map((s) => <option key={s.id} value={s.id}>{s.nombre}</option>)}
          </select>

          {!manual && puntos.length >= 2 ? (
            <>
              <select value={puntoInicioId} onChange={(e) => setPuntoInicioId(e.target.value)} className="h-8 rounded px-2 text-xs outline-hidden" style={inputCls()}>
                <option value="">Punto inicio</option>
                {puntos.map((p) => <option key={p.id} value={p.id}>{p.identificador}{p.etiqueta ? ` · ${p.etiqueta}` : ''}</option>)}
              </select>
              <span style={{ color: 'var(--text-muted)' }}>→</span>
              <select value={puntoFinId} onChange={(e) => setPuntoFinId(e.target.value)} className="h-8 rounded px-2 text-xs outline-hidden" style={inputCls()}>
                <option value="">Punto fin</option>
                {puntos.map((p) => <option key={p.id} value={p.id}>{p.identificador}{p.etiqueta ? ` · ${p.etiqueta}` : ''}</option>)}
              </select>
            </>
          ) : (
            <>
              <input value={eje.x1} onChange={(e) => setEje({ ...eje, x1: e.target.value })} type="number" placeholder="X inicio" className="w-24 h-8 rounded px-2 text-xs outline-hidden font-mono" style={inputCls()} />
              <input value={eje.y1} onChange={(e) => setEje({ ...eje, y1: e.target.value })} type="number" placeholder="Y inicio" className="w-24 h-8 rounded px-2 text-xs outline-hidden font-mono" style={inputCls()} />
              <span style={{ color: 'var(--text-muted)' }}>→</span>
              <input value={eje.x2} onChange={(e) => setEje({ ...eje, x2: e.target.value })} type="number" placeholder="X fin" className="w-24 h-8 rounded px-2 text-xs outline-hidden font-mono" style={inputCls()} />
              <input value={eje.y2} onChange={(e) => setEje({ ...eje, y2: e.target.value })} type="number" placeholder="Y fin" className="w-24 h-8 rounded px-2 text-xs outline-hidden font-mono" style={inputCls()} />
            </>
          )}
          {puntos.length >= 2 && (
            <button onClick={() => setManual((m) => !m)} className="text-[10px] underline" style={{ color: 'var(--text-muted)' }}>
              {manual ? 'usar puntos del levantamiento' : 'coordenadas manuales'}
            </button>
          )}
          <input value={intervalo} onChange={(e) => setIntervalo(e.target.value)} type="number" placeholder="Δ muestreo (m)" className="w-28 h-8 rounded px-2 text-xs outline-hidden font-mono" style={inputCls()} />
          <button onClick={() => void generar()} disabled={!listo || cargando} className="flex items-center gap-1.5 h-8 px-3 rounded text-xs font-semibold disabled:opacity-40" style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}>
            {cargando ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />} Generar
          </button>
        </div>

        {error && <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--danger)' }}><AlertCircle size={13} />{error}</div>}

        {!perfil && !cargando && (
          <div className="flex flex-col items-center justify-center gap-2 text-sm text-center py-12" style={{ color: 'var(--text-muted)' }}>
            <TrendingUp className="w-7 h-7 opacity-40" />
            {puntos.length >= 2 ? 'Elige dos puntos reales del levantamiento (o coordenadas manuales) para trazar el perfil.' : 'Define dos puntos (X/Y locales) sobre la superficie para trazar el perfil longitudinal real.'}
          </div>
        )}

        {perfil && perfil.length > 0 && (
          <>
            <div className="grid grid-cols-3 gap-3">
              <div className="rounded-lg p-3" style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)' }}>
                <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>Longitud</p>
                <p className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>{perfil[perfil.length - 1].cadenamiento.toFixed(1)} m</p>
              </div>
              <div className="rounded-lg p-3" style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)' }}>
                <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>Elevación mín–máx</p>
                <p className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>{Math.min(...perfil.map((p) => p.elevacion)).toFixed(2)}–{Math.max(...perfil.map((p) => p.elevacion)).toFixed(2)} m</p>
              </div>
              <div className="rounded-lg p-3" style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)' }}>
                <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>Pendiente máx.</p>
                <p className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>{pendienteMax !== null ? `${pendienteMax.toFixed(1)}%` : '—'}</p>
              </div>
            </div>

            <div className="rounded-lg p-3" style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)', height: 280 }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={perfil} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
                  <defs>
                    <linearGradient id="perfilFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--accent-gold)" stopOpacity={0.35} />
                      <stop offset="100%" stopColor="var(--accent-gold)" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                  <XAxis dataKey="cadenamiento" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} unit="m" />
                  <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} domain={['dataMin - 1', 'dataMax + 1']} unit="m" />
                  <Tooltip contentStyle={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)', borderRadius: 8, fontSize: 12 }} labelFormatter={(v) => `Cadenamiento ${v} m`} formatter={(v: number) => [`${v.toFixed(2)} m`, 'Elevación']} />
                  <Area type="monotone" dataKey="elevacion" stroke="var(--accent-gold)" strokeWidth={2} fill="url(#perfilFill)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
