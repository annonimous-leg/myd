/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { useState } from 'react';
import { Search, Loader2, AlertCircle, CheckCircle2, XCircle, ShieldCheck } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';
import { useExpedienteStore } from '@/stores/useExpedienteStore';
import type { EvaluacionComplianceResultado } from '@/lib/megalodon-client';

function inputStyle(): React.CSSProperties {
  return { background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-primary)' };
}

function scoreColor(score: number): string {
  if (score >= 80) return 'var(--success)';
  if (score >= 50) return 'var(--amber)';
  return 'var(--danger)';
}

export default function EvaluarPanel() {
  const expedienteActivoId = useExpedienteStore((s) => s.expedienteActivoId);
  const [expedienteId, setExpedienteId] = useState(expedienteActivoId || '');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [resultado, setResultado] = useState<EvaluacionComplianceResultado | null>(null);

  const evaluar = async () => {
    if (!expedienteId.trim()) return;
    setLoading(true); setError(''); setResultado(null);
    try {
      const res = await megalodonClient.compliance.evaluar(expedienteId.trim());
      setResultado(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo evaluar el expediente');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-3 py-2 flex-wrap" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        <input
          value={expedienteId}
          onChange={(e) => setExpedienteId(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && evaluar()}
          placeholder="ID del expediente a evaluar"
          className="h-8 rounded px-2 text-xs outline-hidden w-64 font-mono"
          style={inputStyle()}
        />
        <button
          onClick={evaluar}
          disabled={loading || !expedienteId.trim()}
          className="flex items-center gap-1.5 h-8 px-3 rounded text-xs font-medium disabled:opacity-50"
          style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}
        >
          {loading ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />}
          Evaluar
        </button>
      </div>

      {error && <div className="flex items-center gap-2 px-3 py-2 text-xs" style={{ color: 'var(--danger)' }}><AlertCircle size={13} />{error}</div>}

      <div className="flex-1 overflow-auto p-4">
        {!resultado && !loading && (
          <div className="flex flex-col items-center justify-center h-full gap-2 text-sm text-center" style={{ color: 'var(--text-muted)' }}>
            <ShieldCheck size={28} />
            Escribe un expediente_id y evalúa su cumplimiento contra todas las reglas activas.
          </div>
        )}

        {resultado && (
          <div className="space-y-4 max-w-2xl mx-auto">
            <div className="flex items-center gap-4 rounded-lg p-4" style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)' }}>
              <div
                className="flex items-center justify-center w-20 h-20 rounded-full text-2xl font-bold shrink-0"
                style={{ color: scoreColor(resultado.score), background: `${scoreColor(resultado.score)}18`, border: `2px solid ${scoreColor(resultado.score)}` }}
              >
                {Math.round(resultado.score)}
              </div>
              <div>
                <p className="text-sm font-semibold">Score de cumplimiento</p>
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Expediente {resultado.expediente_id}</p>
                <div className="flex gap-3 mt-2 text-xs">
                  <span style={{ color: 'var(--text-secondary)' }}>{resultado.total_reglas} regla{resultado.total_reglas !== 1 ? 's' : ''} evaluada{resultado.total_reglas !== 1 ? 's' : ''}</span>
                  <span style={{ color: 'var(--success)' }}>{resultado.cumplidas} cumplida{resultado.cumplidas !== 1 ? 's' : ''}</span>
                  <span style={{ color: 'var(--danger)' }}>{resultado.incumplidas} incumplida{resultado.incumplidas !== 1 ? 's' : ''}</span>
                </div>
              </div>
            </div>

            {resultado.detalle_incumplidas.length > 0 && (
              <div>
                <p className="text-xs font-semibold mb-2" style={{ color: 'var(--danger)' }}>Reglas incumplidas</p>
                <div className="space-y-1.5">
                  {resultado.detalle_incumplidas.map((r) => (
                    <div key={r.regla_id} className="flex items-start gap-2 rounded p-2" style={{ background: 'var(--surface-elevated)', border: '1px solid var(--danger)33' }}>
                      <XCircle size={14} className="mt-0.5 shrink-0" style={{ color: 'var(--danger)' }} />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium">{r.nombre}</p>
                        <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>{r.motivo}</p>
                      </div>
                      {r.obligatorio && (
                        <span className="text-[10px] font-medium px-1.5 py-0.5 rounded shrink-0" style={{ color: 'var(--danger)', background: 'var(--danger)22', border: '1px solid var(--danger)44' }}>
                          Obligatorio
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {resultado.detalle_cumplidas.length > 0 && (
              <div>
                <p className="text-xs font-semibold mb-2" style={{ color: 'var(--success)' }}>Reglas cumplidas</p>
                <div className="space-y-1.5">
                  {resultado.detalle_cumplidas.map((r) => (
                    <div key={r.regla_id} className="flex items-center gap-2 rounded p-2" style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)' }}>
                      <CheckCircle2 size={14} className="shrink-0" style={{ color: 'var(--success)' }} />
                      <p className="text-xs">{r.nombre}</p>
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
