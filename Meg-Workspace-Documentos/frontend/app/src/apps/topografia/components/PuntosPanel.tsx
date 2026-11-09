/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */
import { useEffect, useState } from 'react';
import { Loader2, AlertCircle, MapPin } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';
import type { Levantamiento, PuntoTopografico } from '@/lib/megalodon-client';

export default function PuntosPanel({ levantamiento }: { levantamiento: Levantamiento | null }) {
  const [puntos, setPuntos] = useState<PuntoTopografico[]>([]);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!levantamiento) { setPuntos([]); return; }
    setCargando(true); setError('');
    megalodonClient.topografia.listarPuntos(levantamiento.id)
      .then(setPuntos)
      .catch((e) => setError(e instanceof Error ? e.message : 'No se pudieron cargar los puntos (endpoint nuevo — verifica que ya esté implementado en el backend)'))
      .finally(() => setCargando(false));
  }, [levantamiento]);

  if (!levantamiento) {
    return <div className="h-full flex items-center justify-center text-sm" style={{ color: 'var(--text-muted)' }}>Selecciona un levantamiento en la pestaña Levantamiento.</div>;
  }

  return (
    <div className="h-full overflow-auto p-4">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{levantamiento.nombre} · {puntos.length} punto{puntos.length !== 1 ? 's' : ''} · CRS {levantamiento.crs || `EPSG:${levantamiento.srid}`}</p>
      </div>

      {error && <div className="flex items-center gap-2 text-xs mb-3" style={{ color: 'var(--danger)' }}><AlertCircle size={13} />{error}</div>}

      {cargando ? (
        <div className="flex items-center justify-center h-40 gap-2 text-sm" style={{ color: 'var(--text-muted)' }}><Loader2 size={16} className="animate-spin" /> Cargando…</div>
      ) : puntos.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-40 gap-2 text-sm text-center" style={{ color: 'var(--text-muted)' }}>
          <MapPin className="w-6 h-6 opacity-40" /> Sin puntos todavía. Impórtalos por CSV en la pestaña Levantamiento.
        </div>
      ) : (
        <table className="w-full text-xs">
          <thead>
            <tr style={{ color: 'var(--text-muted)', borderBottom: '1px solid var(--border-subtle)' }}>
              <th className="text-left font-medium py-1.5 pr-3">ID</th>
              <th className="text-left font-medium py-1.5 pr-3">Etiqueta</th>
              <th className="text-right font-medium py-1.5 pr-3">Este (X)</th>
              <th className="text-right font-medium py-1.5 pr-3">Norte (Y)</th>
              <th className="text-right font-medium py-1.5">Elevación (Z)</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {puntos.map((p) => (
              <tr key={p.id} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                <td className="py-1.5 pr-3" style={{ color: 'var(--accent-gold)' }}>{p.identificador}</td>
                <td className="py-1.5 pr-3" style={{ color: 'var(--text-secondary)' }}>{p.etiqueta || '—'}</td>
                <td className="py-1.5 pr-3 text-right" style={{ color: 'var(--text-primary)' }}>{p.x.toFixed(3)}</td>
                <td className="py-1.5 pr-3 text-right" style={{ color: 'var(--text-primary)' }}>{p.y.toFixed(3)}</td>
                <td className="py-1.5 text-right" style={{ color: 'var(--text-primary)' }}>{p.z !== undefined ? p.z.toFixed(3) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
