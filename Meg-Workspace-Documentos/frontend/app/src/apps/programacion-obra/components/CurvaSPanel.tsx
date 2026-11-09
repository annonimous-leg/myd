/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { useCallback, useEffect, useState } from 'react';
import { TrendingUp, Loader2, AlertCircle, RefreshCw } from 'lucide-react';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from 'recharts';
import { megalodonClient } from '@/lib/api-client';
import type { PuntoCurvaS } from '@/lib/megalodon-client';

function fmtFechaCorta(iso: string): string {
  try { return new Date(iso).toLocaleDateString('es-MX', { day: '2-digit', month: 'short' }); } catch { return iso; }
}
function money(n: number): string {
  return n.toLocaleString('es-MX', { style: 'currency', currency: 'MXN', maximumFractionDigits: 0, notation: 'compact' });
}

export default function CurvaSPanel({ expedienteId, programaId }: { expedienteId: string; programaId: string }) {
  const [puntos, setPuntos] = useState<PuntoCurvaS[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const cargar = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const r = await megalodonClient.programacion.curvaS(expedienteId, programaId);
      setPuntos(r || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo cargar la curva S.');
    } finally {
      setLoading(false);
    }
  }, [expedienteId, programaId]);

  useEffect(() => { void cargar(); }, [cargar]);

  const datos = puntos.map((p) => ({ ...p, fechaCorta: fmtFechaCorta(p.fecha) }));

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: '1px solid #2A2A3E' }}>
        <span className="text-xs" style={{ color: '#8A8578' }}>{puntos.length} punto{puntos.length !== 1 ? 's' : ''} de control</span>
        <button
          onClick={() => void cargar()}
          disabled={loading}
          className="flex items-center gap-1.5 h-7 px-2.5 rounded-md text-[11px] font-medium disabled:opacity-50"
          style={{ background: '#1C1C28', border: '1px solid #2A2A3E', color: '#E8E4DC' }}
        >
          {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />} Actualizar
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 px-4 py-2 text-xs" style={{ color: '#B84A4A' }}>
          <AlertCircle className="w-3.5 h-3.5 shrink-0" /> {error}
        </div>
      )}

      <div className="flex-1 overflow-auto p-4">
        {loading && puntos.length === 0 ? (
          <div className="h-full flex items-center justify-center gap-2 text-sm" style={{ color: '#8A8578' }}>
            <Loader2 className="w-4 h-4 animate-spin" /> Cargando...
          </div>
        ) : datos.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center gap-2 text-sm text-center" style={{ color: '#8A8578' }}>
            <TrendingUp className="w-7 h-7 opacity-40" />
            Sin datos de curva S todavía. Corre "Calcular CPM" en la pestaña Gantt primero: la curva S se genera a partir de ese cálculo.
          </div>
        ) : (
          <div className="max-w-4xl mx-auto space-y-6">
            <div>
              <p className="text-xs font-semibold mb-2" style={{ color: '#8A8578' }}>Avance físico acumulado (%)</p>
              <div className="rounded-lg p-3" style={{ background: '#12121A', border: '1px solid #2A2A3E', height: 260 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={datos} margin={{ top: 5, right: 12, left: -12, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#2A2A3E" />
                    <XAxis dataKey="fechaCorta" tick={{ fill: '#8A8578', fontSize: 11 }} />
                    <YAxis tick={{ fill: '#8A8578', fontSize: 11 }} domain={[0, 100]} unit="%" />
                    <Tooltip contentStyle={{ background: '#12121A', border: '1px solid #2A2A3E', borderRadius: 8, fontSize: 12 }} labelStyle={{ color: '#E8E4DC' }} />
                    <Legend wrapperStyle={{ fontSize: 11, color: '#8A8578' }} />
                    <Line type="monotone" dataKey="avance_plan_pct" name="Plan" stroke="#8A8578" strokeWidth={2} strokeDasharray="4 3" dot={false} />
                    <Line type="monotone" dataKey="avance_real_pct" name="Real" stroke="#C9A84C" strokeWidth={2.5} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div>
              <p className="text-xs font-semibold mb-2" style={{ color: '#8A8578' }}>Costo acumulado</p>
              <div className="rounded-lg p-3" style={{ background: '#12121A', border: '1px solid #2A2A3E', height: 260 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={datos} margin={{ top: 5, right: 12, left: -6, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#2A2A3E" />
                    <XAxis dataKey="fechaCorta" tick={{ fill: '#8A8578', fontSize: 11 }} />
                    <YAxis tick={{ fill: '#8A8578', fontSize: 11 }} tickFormatter={(v) => money(Number(v))} />
                    <Tooltip contentStyle={{ background: '#12121A', border: '1px solid #2A2A3E', borderRadius: 8, fontSize: 12 }} labelStyle={{ color: '#E8E4DC' }} formatter={(v: number) => money(Number(v))} />
                    <Legend wrapperStyle={{ fontSize: 11, color: '#8A8578' }} />
                    <Line type="monotone" dataKey="costo_plan" name="Plan" stroke="#8A8578" strokeWidth={2} strokeDasharray="4 3" dot={false} />
                    <Line type="monotone" dataKey="costo_real" name="Real" stroke="#5A8AB8" strokeWidth={2.5} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
