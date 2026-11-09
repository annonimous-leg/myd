/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { useState } from 'react';
import { Sigma, Loader2, AlertCircle, Play, Target } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';
import type { ResultadoPERT } from '@/lib/megalodon-client';

function fmtDias(n: number): string {
  return `${n.toLocaleString('es-MX', { maximumFractionDigits: 1 })} días`;
}
function fmtFecha(iso?: string | null): string {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleDateString('es-MX'); } catch { return iso; }
}
function probColor(p: number): string {
  if (p >= 0.7) return '#5A9E6F';
  if (p >= 0.4) return '#D4953A';
  return '#B84A4A';
}

export default function PertPanel({ expedienteId, programaId }: { expedienteId: string; programaId: string }) {
  const [fechaObjetivo, setFechaObjetivo] = useState('');
  const [resultado, setResultado] = useState<ResultadoPERT | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const calcular = async () => {
    setLoading(true); setError('');
    try {
      const r = await megalodonClient.programacion.calcularPERT(expedienteId, programaId, fechaObjetivo || undefined);
      setResultado(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo calcular el PERT. Verifica que el programa tenga estimaciones optimista/probable/pesimista cargadas.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-2 px-4 py-3 flex-wrap" style={{ borderBottom: '1px solid #2A2A3E' }}>
        <div className="flex items-center gap-1.5 text-xs" style={{ color: '#8A8578' }}>
          <Target className="w-3.5 h-3.5" /> Fecha objetivo (opcional)
        </div>
        <input
          type="date"
          value={fechaObjetivo}
          onChange={(e) => setFechaObjetivo(e.target.value)}
          className="h-8 rounded-md px-2 text-xs outline-hidden"
          style={{ background: '#12121A', border: '1px solid #2A2A3E', color: '#E8E4DC' }}
        />
        <button
          onClick={() => void calcular()}
          disabled={loading}
          className="flex items-center gap-1.5 h-8 px-3 rounded-md text-xs font-semibold disabled:opacity-50"
          style={{ background: '#C9A84C', color: '#030305' }}
        >
          {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
          Calcular PERT
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 px-4 py-2 text-xs" style={{ color: '#B84A4A' }}>
          <AlertCircle className="w-3.5 h-3.5 shrink-0" /> {error}
        </div>
      )}

      <div className="flex-1 overflow-auto p-4">
        {!resultado && !loading && (
          <div className="h-full flex flex-col items-center justify-center gap-2 text-sm text-center" style={{ color: '#8A8578' }}>
            <Sigma className="w-7 h-7 opacity-40" />
            Calcula la duración esperada del programa usando las tres estimaciones (optimista/probable/pesimista) de cada actividad.
          </div>
        )}

        {resultado && (
          <div className="max-w-2xl mx-auto space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              <div className="rounded-lg p-3" style={{ background: '#12121A', border: '1px solid #2A2A3E' }}>
                <div className="text-[11px]" style={{ color: '#8A8578' }}>Duración esperada</div>
                <div className="text-lg font-semibold mt-1" style={{ color: '#E8E4DC' }}>{fmtDias(resultado.duracion_esperada)}</div>
              </div>
              <div className="rounded-lg p-3" style={{ background: '#12121A', border: '1px solid #2A2A3E' }}>
                <div className="text-[11px]" style={{ color: '#8A8578' }}>Desviación estándar</div>
                <div className="text-lg font-semibold mt-1" style={{ color: '#E8E4DC' }}>± {fmtDias(resultado.desviacion_estandar)}</div>
              </div>
              <div className="rounded-lg p-3" style={{ background: '#12121A', border: '1px solid #2A2A3E' }}>
                <div className="text-[11px]" style={{ color: '#8A8578' }}>Varianza total</div>
                <div className="text-lg font-semibold mt-1" style={{ color: '#E8E4DC' }}>{resultado.varianza_total.toLocaleString('es-MX', { maximumFractionDigits: 2 })}</div>
              </div>
            </div>

            {resultado.fecha_probable_terminacion && (
              <div className="rounded-lg p-3 text-sm" style={{ background: '#12121A', border: '1px solid #2A2A3E', color: '#E8E4DC' }}>
                Fecha probable de terminación: <b>{fmtFecha(resultado.fecha_probable_terminacion)}</b>
              </div>
            )}

            {fechaObjetivo && (
              <div
                className="flex items-center gap-4 rounded-lg p-4"
                style={{ background: '#12121A', border: `1px solid ${probColor(resultado.probabilidad_terminar_a_tiempo)}44` }}
              >
                <div
                  className="flex items-center justify-center w-16 h-16 rounded-full text-lg font-bold shrink-0"
                  style={{ color: probColor(resultado.probabilidad_terminar_a_tiempo), background: `${probColor(resultado.probabilidad_terminar_a_tiempo)}18`, border: `2px solid ${probColor(resultado.probabilidad_terminar_a_tiempo)}` }}
                >
                  {Math.round(resultado.probabilidad_terminar_a_tiempo * 100)}%
                </div>
                <div>
                  <p className="text-sm font-medium" style={{ color: '#E8E4DC' }}>Probabilidad de terminar a tiempo</p>
                  <p className="text-xs" style={{ color: '#8A8578' }}>Contra la fecha objetivo del {fmtFecha(fechaObjetivo)}</p>
                </div>
              </div>
            )}

            {resultado.percentiles && Object.keys(resultado.percentiles).length > 0 && (
              <div>
                <p className="text-xs font-semibold mb-2" style={{ color: '#8A8578' }}>Percentiles de duración</p>
                <div className="grid grid-cols-3 gap-2">
                  {Object.entries(resultado.percentiles).map(([k, v]) => (
                    <div key={k} className="rounded-lg p-2.5 text-center" style={{ background: '#12121A', border: '1px solid #2A2A3E' }}>
                      <div className="text-[10px]" style={{ color: '#8A8578' }}>{k}</div>
                      <div className="text-sm font-semibold mt-0.5" style={{ color: '#E8E4DC' }}>{fmtDias(v)}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
