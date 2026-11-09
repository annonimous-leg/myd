/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { useCallback, useEffect, useState } from 'react';
import { GitBranch, Loader2, AlertCircle, RefreshCw, ArrowRight } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';
import type { RutaCriticaInfo, Actividad } from '@/lib/megalodon-client';

function fmtFecha(iso?: string | null): string {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleDateString('es-MX', { day: '2-digit', month: 'short', year: 'numeric' }); } catch { return iso; }
}

export default function RutaCriticaPanel({ expedienteId, programaId, actividades }: { expedienteId: string; programaId: string; actividades: Actividad[] }) {
  const [info, setInfo] = useState<RutaCriticaInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const cargar = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const r = await megalodonClient.programacion.rutaCritica(expedienteId, programaId);
      setInfo(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo cargar la ruta crítica.');
    } finally {
      setLoading(false);
    }
  }, [expedienteId, programaId]);

  useEffect(() => { void cargar(); }, [cargar]);

  // La ruta crítica del motor CPM referencia actividades por 'identificador'
  // (el mismo campo que usan predecesoras/actualizarActividad en toda esta
  // app), no por el UUID '.id'.
  const porIdentificador = new Map(actividades.map((a) => [a.identificador, a]));
  const cadena = (info?.actividades || []).map(
    (identificador) => porIdentificador.get(identificador) || ({ id: identificador, identificador, nombre: identificador, duracion: 0, holgura_total: 0 } as Partial<Actividad> & { id: string; identificador: string }),
  );

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: '1px solid #2A2A3E' }}>
        <span className="text-xs" style={{ color: '#8A8578' }}>{cadena.length} actividad{cadena.length !== 1 ? 'es' : ''} en la ruta crítica</span>
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
        {loading && !info ? (
          <div className="h-full flex items-center justify-center gap-2 text-sm" style={{ color: '#8A8578' }}>
            <Loader2 className="w-4 h-4 animate-spin" /> Cargando...
          </div>
        ) : !info || cadena.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center gap-2 text-sm text-center" style={{ color: '#8A8578' }}>
            <GitBranch className="w-7 h-7 opacity-40" />
            Sin ruta crítica todavía. Corre "Calcular CPM" en la pestaña Gantt primero.
          </div>
        ) : (
          <div className="max-w-3xl mx-auto space-y-5">
            <div className="grid grid-cols-3 gap-3">
              <div className="rounded-lg p-3" style={{ background: '#12121A', border: '1px solid #2A2A3E' }}>
                <div className="text-[11px]" style={{ color: '#8A8578' }}>Duración total</div>
                <div className="text-lg font-semibold mt-1" style={{ color: '#E8E4DC' }}>{info.duracion} días</div>
              </div>
              <div className="rounded-lg p-3" style={{ background: '#12121A', border: '1px solid #2A2A3E' }}>
                <div className="text-[11px]" style={{ color: '#8A8578' }}>Inicio</div>
                <div className="text-sm font-semibold mt-1" style={{ color: '#E8E4DC' }}>{fmtFecha(info.fecha_inicio)}</div>
              </div>
              <div className="rounded-lg p-3" style={{ background: '#12121A', border: '1px solid #2A2A3E' }}>
                <div className="text-[11px]" style={{ color: '#8A8578' }}>Fin</div>
                <div className="text-sm font-semibold mt-1" style={{ color: '#E8E4DC' }}>{fmtFecha(info.fecha_fin)}</div>
              </div>
            </div>

            <div>
              <p className="text-xs font-semibold mb-2" style={{ color: '#8A8578' }}>Secuencia crítica (holgura = 0)</p>
              <div className="space-y-1.5">
                {cadena.map((a, i) => (
                  <div key={a.identificador + i} className="flex items-center gap-3 rounded-lg px-3 py-2.5" style={{ background: '#12121A', border: '1px solid #B84A4A33' }}>
                    <span className="flex items-center justify-center w-6 h-6 rounded-full text-[10px] font-bold shrink-0" style={{ background: '#B84A4A22', color: '#B84A4A', border: '1px solid #B84A4A44' }}>
                      {i + 1}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm truncate" style={{ color: '#E8E4DC' }}>{a.nombre}</p>
                    </div>
                    <span className="text-xs shrink-0" style={{ color: '#8A8578' }}>{a.duracion ?? 0}d</span>
                    {i < cadena.length - 1 && <ArrowRight className="w-3.5 h-3.5 shrink-0" style={{ color: '#2A2A3E' }} />}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
