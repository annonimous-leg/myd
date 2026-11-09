/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { useCallback, useEffect, useState } from 'react';
import { Plus, Loader2, AlertCircle, Gavel, X, Save } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';
import {
  TIPOS_SANCION_COMPLIANCE,
  type Sancion, type SancionInput,
} from '@/lib/megalodon-client';

function inputStyle(): React.CSSProperties {
  return { background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-primary)' };
}

function tipoColor(tipo: string): string {
  switch (tipo) {
    case 'INHABILITACION': return 'var(--danger)';
    case 'DESTITUCION': return 'var(--danger)';
    case 'MULTA': return 'var(--amber)';
    default: return 'var(--info)';
  }
}

function fmtFecha(iso?: string): string {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleDateString('es-MX'); } catch { return iso; }
}

function fmtMonto(n?: number): string {
  if (n === undefined || n === null) return '—';
  return n.toLocaleString('es-MX', { style: 'currency', currency: 'MXN', maximumFractionDigits: 0 });
}

const VACIA: SancionInput = {
  proveedor_id: '', tipo: TIPOS_SANCION_COMPLIANCE[0], motivo: '',
  monto_multa: undefined, expediente_sancionador: '', hechos: '',
  audiencia_fecha: '', resolucion: '', vigencia_inicio: '', vigencia_fin: '',
  expediente_id: '', licitacion_id: '',
};

export default function SancionesPanel() {
  const [items, setItems] = useState<Sancion[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [filtroProveedor, setFiltroProveedor] = useState('');
  const [filtroTipo, setFiltroTipo] = useState('');

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<SancionInput>(VACIA);
  const [guardando, setGuardando] = useState(false);

  const cargar = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const res = await megalodonClient.compliance.sanciones.listar({
        proveedor_id: filtroProveedor.trim() || undefined,
        tipo: filtroTipo || undefined,
        limit: 200,
      });
      setItems(res.items); setTotal(res.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudieron cargar las sanciones');
    } finally {
      setLoading(false);
    }
  }, [filtroProveedor, filtroTipo]);

  useEffect(() => { void cargar(); }, [cargar]);

  const abrirNueva = () => { setForm({ ...VACIA, proveedor_id: filtroProveedor }); setShowForm(true); };

  const guardar = async () => {
    if (!form.proveedor_id.trim() || !form.motivo.trim()) return;
    setGuardando(true); setError('');
    try {
      const payload: SancionInput = {
        proveedor_id: form.proveedor_id.trim(),
        tipo: form.tipo,
        motivo: form.motivo.trim(),
        monto_multa: form.monto_multa || undefined,
        expediente_sancionador: form.expediente_sancionador?.trim() || undefined,
        hechos: form.hechos?.trim() || undefined,
        audiencia_fecha: form.audiencia_fecha || undefined,
        resolucion: form.resolucion?.trim() || undefined,
        vigencia_inicio: form.vigencia_inicio || undefined,
        vigencia_fin: form.vigencia_fin || undefined,
        expediente_id: form.expediente_id?.trim() || undefined,
        licitacion_id: form.licitacion_id?.trim() || undefined,
      };
      await megalodonClient.compliance.sanciones.crear(payload);
      setShowForm(false);
      await cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo registrar la sanción');
    } finally {
      setGuardando(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-3 py-2 flex-wrap" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        <input
          value={filtroProveedor}
          onChange={(e) => setFiltroProveedor(e.target.value)}
          placeholder="Filtrar por proveedor_id"
          className="h-8 rounded px-2 text-xs outline-hidden w-48"
          style={inputStyle()}
        />
        <select value={filtroTipo} onChange={(e) => setFiltroTipo(e.target.value)} className="h-8 rounded px-2 text-xs outline-hidden" style={inputStyle()}>
          <option value="">Todos los tipos</option>
          {TIPOS_SANCION_COMPLIANCE.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{total} sanción{total !== 1 ? 'es' : ''}</span>
        <div className="flex-1" />
        <button onClick={abrirNueva} className="flex items-center gap-1.5 h-8 px-3 rounded text-xs font-medium" style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}>
          <Plus size={13} /> Nueva sanción
        </button>
      </div>

      {error && <div className="flex items-center gap-2 px-3 py-2 text-xs" style={{ color: 'var(--danger)' }}><AlertCircle size={13} />{error}</div>}

      <div className="flex-1 overflow-auto">
        {loading ? (
          <div className="flex items-center justify-center h-full gap-2 text-sm" style={{ color: 'var(--text-muted)' }}>
            <Loader2 size={16} className="animate-spin" /> Cargando...
          </div>
        ) : items.length === 0 ? (
          <div className="flex items-center justify-center h-full text-sm" style={{ color: 'var(--text-muted)' }}>
            Sin sanciones registradas.
          </div>
        ) : (
          <div className="divide-y" style={{ borderColor: 'var(--border-subtle)' }}>
            {items.map((s) => (
              <div key={s.id} className="flex items-start gap-3 px-3 py-2.5" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                <Gavel size={15} className="mt-0.5 shrink-0" style={{ color: tipoColor(s.tipo) }} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">Proveedor {s.proveedor_id}</p>
                  <p className="text-[11px] truncate" style={{ color: 'var(--text-muted)' }}>{s.motivo}</p>
                  <p className="text-[10px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
                    {s.vigencia_inicio ? `Vigente ${fmtFecha(s.vigencia_inicio)} – ${fmtFecha(s.vigencia_fin)}` : `Registrada ${fmtFecha(s.created_at)}`}
                  </p>
                </div>
                <div className="text-right shrink-0">
                  <span
                    className="text-[10px] font-medium px-1.5 py-0.5 rounded"
                    style={{ color: tipoColor(s.tipo), background: `${tipoColor(s.tipo)}22`, border: `1px solid ${tipoColor(s.tipo)}44` }}
                  >
                    {s.tipo}
                  </span>
                  {s.monto_multa !== undefined && s.monto_multa !== null && (
                    <p className="text-xs font-mono mt-1" style={{ color: 'var(--text-secondary)' }}>{fmtMonto(s.monto_multa)}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {showForm && (
        <div className="fixed inset-0 flex items-center justify-center z-50" style={{ background: 'rgba(0,0,0,0.6)' }} onClick={() => setShowForm(false)}>
          <div onClick={(e) => e.stopPropagation()} className="w-[460px] max-h-[85vh] overflow-auto rounded-lg p-4 space-y-3" style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-active)' }}>
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">Nueva sanción</h3>
              <button onClick={() => setShowForm(false)} style={{ color: 'var(--text-muted)' }}><X size={14} /></button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Proveedor ID</label>
                <input value={form.proveedor_id} onChange={(e) => setForm({ ...form, proveedor_id: e.target.value })} className="w-full h-8 rounded px-2 text-xs outline-hidden font-mono" style={inputStyle()} />
              </div>
              <div>
                <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Tipo</label>
                <select value={form.tipo} onChange={(e) => setForm({ ...form, tipo: e.target.value as SancionInput['tipo'] })} className="w-full h-8 rounded px-2 text-xs outline-hidden" style={inputStyle()}>
                  {TIPOS_SANCION_COMPLIANCE.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
            </div>
            <div>
              <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Motivo</label>
              <textarea value={form.motivo} onChange={(e) => setForm({ ...form, motivo: e.target.value })} rows={2} className="w-full rounded px-2 py-1.5 text-xs outline-hidden resize-none" style={inputStyle()} />
            </div>
            <div>
              <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Hechos (opcional)</label>
              <textarea value={form.hechos} onChange={(e) => setForm({ ...form, hechos: e.target.value })} rows={2} className="w-full rounded px-2 py-1.5 text-xs outline-hidden resize-none" style={inputStyle()} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Monto de multa (opcional)</label>
                <input type="number" min={0} value={form.monto_multa ?? ''} onChange={(e) => setForm({ ...form, monto_multa: e.target.value ? Number(e.target.value) : undefined })} className="w-full h-8 rounded px-2 text-xs outline-hidden" style={inputStyle()} />
              </div>
              <div>
                <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Expediente sancionador (opcional)</label>
                <input value={form.expediente_sancionador} onChange={(e) => setForm({ ...form, expediente_sancionador: e.target.value })} className="w-full h-8 rounded px-2 text-xs outline-hidden font-mono" style={inputStyle()} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Fecha de audiencia (opcional)</label>
                <input type="date" value={form.audiencia_fecha} onChange={(e) => setForm({ ...form, audiencia_fecha: e.target.value })} className="w-full h-8 rounded px-2 text-xs outline-hidden" style={inputStyle()} />
              </div>
              <div />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Vigencia inicio (opcional)</label>
                <input type="date" value={form.vigencia_inicio} onChange={(e) => setForm({ ...form, vigencia_inicio: e.target.value })} className="w-full h-8 rounded px-2 text-xs outline-hidden" style={inputStyle()} />
              </div>
              <div>
                <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Vigencia fin (opcional)</label>
                <input type="date" value={form.vigencia_fin} onChange={(e) => setForm({ ...form, vigencia_fin: e.target.value })} className="w-full h-8 rounded px-2 text-xs outline-hidden" style={inputStyle()} />
              </div>
            </div>
            <div>
              <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Resolución (opcional)</label>
              <textarea value={form.resolucion} onChange={(e) => setForm({ ...form, resolucion: e.target.value })} rows={2} className="w-full rounded px-2 py-1.5 text-xs outline-hidden resize-none" style={inputStyle()} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Expediente relacionado (opcional)</label>
                <input value={form.expediente_id} onChange={(e) => setForm({ ...form, expediente_id: e.target.value })} className="w-full h-8 rounded px-2 text-xs outline-hidden font-mono" style={inputStyle()} />
              </div>
              <div>
                <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Licitación relacionada (opcional)</label>
                <input value={form.licitacion_id} onChange={(e) => setForm({ ...form, licitacion_id: e.target.value })} className="w-full h-8 rounded px-2 text-xs outline-hidden font-mono" style={inputStyle()} />
              </div>
            </div>
            <button
              onClick={guardar}
              disabled={guardando || !form.proveedor_id.trim() || !form.motivo.trim()}
              className="w-full h-9 rounded text-sm font-semibold flex items-center justify-center gap-2 disabled:opacity-50"
              style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}
            >
              {guardando ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
              Registrar sanción
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
