/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { useState } from 'react';
import { Gauge, Loader2, AlertCircle, Play, CalendarClock } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';
import type { ResultadoEVM } from '@/lib/megalodon-client';

function money(n: number): string {
  return n.toLocaleString('es-MX', { style: 'currency', currency: 'MXN', maximumFractionDigits: 0 });
}
function idx(n: number): string {
  return n.toLocaleString('es-MX', { maximumFractionDigits: 2 });
}

const CRONOGRAMA_TONE: Record<string, string> = {
  ADELANTADO: '#5A9E6F', A_TIEMPO: '#5A8AB8', ATRASADO: '#B84A4A',
};
const COSTO_TONE: Record<string, string> = {
  BAJO_PRESUPUESTO: '#5A9E6F', A_PRESUPUESTO: '#5A8AB8', SOBRE_PRESUPUESTO: '#B84A4A',
};

function Metric({ label, value, tone, hint }: { label: string; value: string; tone?: string; hint?: string }) {
  return (
    <div className="rounded-lg p-3" style={{ background: '#12121A', border: '1px solid #2A2A3E' }}>
      <div className="text-[11px]" style={{ color: '#8A8578' }}>{label}{hint && <span className="opacity-60"> · {hint}</span>}</div>
      <div className="text-base font-semibold mt-1" style={{ color: tone || '#E8E4DC' }}>{value}</div>
    </div>
  );
}

export default function EvmPanel({ expedienteId, programaId }: { expedienteId: string; programaId: string }) {
  const [fechaCorte, setFechaCorte] = useState('');
  const [resultado, setResultado] = useState<ResultadoEVM | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const calcular = async () => {
    setLoading(true); setError('');
    try {
      const r = await megalodonClient.programacion.calcularEVM(expedienteId, programaId, fechaCorte || undefined);
      setResultado(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo calcular el EVM. Verifica que las actividades tengan costo presupuestado y avance registrados.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-2 px-4 py-3 flex-wrap" style={{ borderBottom: '1px solid #2A2A3E' }}>
        <div className="flex items-center gap-1.5 text-xs" style={{ color: '#8A8578' }}>
          <CalendarClock className="w-3.5 h-3.5" /> Fecha de corte (opcional, hoy por defecto)
        </div>
        <input
          type="date"
          value={fechaCorte}
          onChange={(e) => setFechaCorte(e.target.value)}
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
          Calcular EVM
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
            <Gauge className="w-7 h-7 opacity-40" />
            Calcula el valor ganado del programa: costo/avance planeado vs. real a la fecha de corte.
          </div>
        )}

        {resultado && (
          <div className="max-w-3xl mx-auto space-y-4">
            <div className="flex items-center gap-3 flex-wrap">
              <span
                className="text-xs font-medium px-2.5 py-1 rounded-full"
                style={{ color: CRONOGRAMA_TONE[resultado.interpretacion.cronograma], background: `${CRONOGRAMA_TONE[resultado.interpretacion.cronograma]}18`, border: `1px solid ${CRONOGRAMA_TONE[resultado.interpretacion.cronograma]}44` }}
              >
                Cronograma: {resultado.interpretacion.cronograma.replace(/_/g, ' ')}
              </span>
              <span
                className="text-xs font-medium px-2.5 py-1 rounded-full"
                style={{ color: COSTO_TONE[resultado.interpretacion.costo], background: `${COSTO_TONE[resultado.interpretacion.costo]}18`, border: `1px solid ${COSTO_TONE[resultado.interpretacion.costo]}44` }}
              >
                Costo: {resultado.interpretacion.costo.replace(/_/g, ' ')}
              </span>
            </div>

            <div>
              <p className="text-xs font-semibold mb-2" style={{ color: '#8A8578' }}>Valores base</p>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <Metric label="PV" hint="Valor planeado" value={money(resultado.pv)} />
                <Metric label="EV" hint="Valor ganado" value={money(resultado.ev)} />
                <Metric label="AC" hint="Costo real" value={money(resultado.ac)} />
              </div>
            </div>

            <div>
              <p className="text-xs font-semibold mb-2" style={{ color: '#8A8578' }}>Variaciones</p>
              <div className="grid grid-cols-2 gap-3">
                <Metric label="SV" hint="Variación de cronograma" value={money(resultado.sv)} tone={resultado.sv >= 0 ? '#5A9E6F' : '#B84A4A'} />
                <Metric label="CV" hint="Variación de costo" value={money(resultado.cv)} tone={resultado.cv >= 0 ? '#5A9E6F' : '#B84A4A'} />
              </div>
            </div>

            <div>
              <p className="text-xs font-semibold mb-2" style={{ color: '#8A8578' }}>Índices de desempeño</p>
              <div className="grid grid-cols-3 gap-3">
                <Metric label="SPI" value={idx(resultado.spi)} tone={resultado.spi >= 1 ? '#5A9E6F' : '#B84A4A'} />
                <Metric label="CPI" value={idx(resultado.cpi)} tone={resultado.cpi >= 1 ? '#5A9E6F' : '#B84A4A'} />
                <Metric label="TCPI" value={idx(resultado.tcpi)} />
              </div>
            </div>

            <div>
              <p className="text-xs font-semibold mb-2" style={{ color: '#8A8578' }}>Proyección a término</p>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <Metric label="EAC" hint="Estimado al término" value={money(resultado.eac)} />
                <Metric label="ETC" hint="Estimado por terminar" value={money(resultado.etc)} />
                <Metric label="VAC" hint="Variación al término" value={money(resultado.vac)} tone={resultado.vac >= 0 ? '#5A9E6F' : '#B84A4A'} />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
