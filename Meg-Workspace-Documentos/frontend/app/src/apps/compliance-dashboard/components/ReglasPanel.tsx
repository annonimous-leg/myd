/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { useCallback, useEffect, useState } from 'react';
import { Plus, Loader2, AlertCircle, CheckCircle2, XCircle, Trash2, Pencil, X, Save } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';
import {
  ETAPAS_COMPLIANCE, TIPOS_PROCEDIMIENTO_COMPLIANCE,
  type ReglaCumplimiento, type ReglaCumplimientoInput,
} from '@/lib/megalodon-client';

function inputStyle(): React.CSSProperties {
  return { background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-primary)' };
}

const VACIA: ReglaCumplimientoInput = {
  nombre: '', descripcion: '', tipo_procedimiento: TIPOS_PROCEDIMIENTO_COMPLIANCE[0],
  etapa: ETAPAS_COMPLIANCE[0], obligatorio: true, activa: true, condicion_evaluacion: '',
};

export default function ReglasPanel() {
  const [reglas, setReglas] = useState<ReglaCumplimiento[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [filtroEtapa, setFiltroEtapa] = useState('');
  const [filtroActiva, setFiltroActiva] = useState('');

  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [form, setForm] = useState<ReglaCumplimientoInput>(VACIA);
  const [guardando, setGuardando] = useState(false);

  const cargar = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const res = await megalodonClient.compliance.reglas.listar({
        etapa: filtroEtapa || undefined,
        activa: filtroActiva === '' ? undefined : filtroActiva === 'true',
        limit: 200,
      });
      setReglas(res.items); setTotal(res.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudieron cargar las reglas');
    } finally {
      setLoading(false);
    }
  }, [filtroEtapa, filtroActiva]);

  useEffect(() => { void cargar(); }, [cargar]);

  const abrirNueva = () => { setEditId(null); setForm(VACIA); setShowForm(true); };
  const abrirEditar = (r: ReglaCumplimiento) => {
    setEditId(r.id);
    setForm({
      nombre: r.nombre, descripcion: r.descripcion || '', tipo_procedimiento: r.tipo_procedimiento,
      etapa: r.etapa, obligatorio: r.obligatorio, activa: r.activa, condicion_evaluacion: r.condicion_evaluacion || '',
    });
    setShowForm(true);
  };

  const guardar = async () => {
    if (!form.nombre.trim()) return;
    setGuardando(true); setError('');
    try {
      if (editId) await megalodonClient.compliance.reglas.actualizar(editId, form);
      else await megalodonClient.compliance.reglas.crear(form);
      setShowForm(false);
      await cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo guardar la regla');
    } finally {
      setGuardando(false);
    }
  };

  const eliminar = async (id: string) => {
    try {
      await megalodonClient.compliance.reglas.eliminar(id);
      await cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo eliminar la regla');
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-3 py-2 flex-wrap" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        <select value={filtroEtapa} onChange={(e) => setFiltroEtapa(e.target.value)} className="h-8 rounded px-2 text-xs outline-hidden" style={inputStyle()}>
          <option value="">Todas las etapas</option>
          {ETAPAS_COMPLIANCE.map((e) => <option key={e} value={e}>{e}</option>)}
        </select>
        <select value={filtroActiva} onChange={(e) => setFiltroActiva(e.target.value)} className="h-8 rounded px-2 text-xs outline-hidden" style={inputStyle()}>
          <option value="">Activas e inactivas</option>
          <option value="true">Sólo activas</option>
          <option value="false">Sólo inactivas</option>
        </select>
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{total} regla{total !== 1 ? 's' : ''}</span>
        <div className="flex-1" />
        <button onClick={abrirNueva} className="flex items-center gap-1.5 h-8 px-3 rounded text-xs font-medium" style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}>
          <Plus size={13} /> Nueva regla
        </button>
      </div>

      {error && <div className="flex items-center gap-2 px-3 py-2 text-xs" style={{ color: 'var(--danger)' }}><AlertCircle size={13} />{error}</div>}

      <div className="flex-1 overflow-auto">
        {loading ? (
          <div className="flex items-center justify-center h-full gap-2 text-sm" style={{ color: 'var(--text-muted)' }}>
            <Loader2 size={16} className="animate-spin" /> Cargando...
          </div>
        ) : reglas.length === 0 ? (
          <div className="flex items-center justify-center h-full text-sm" style={{ color: 'var(--text-muted)' }}>
            Sin reglas de cumplimiento registradas.
          </div>
        ) : (
          <div className="divide-y" style={{ borderColor: 'var(--border-subtle)' }}>
            {reglas.map((r) => (
              <div key={r.id} className="flex items-center gap-3 px-3 py-2.5" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                {r.activa ? <CheckCircle2 size={15} style={{ color: 'var(--success)' }} /> : <XCircle size={15} style={{ color: 'var(--text-muted)' }} />}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{r.nombre}</p>
                  <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>{r.tipo_procedimiento} · {r.etapa}</p>
                </div>
                {r.obligatorio && (
                  <span className="text-[10px] font-medium px-1.5 py-0.5 rounded" style={{ color: 'var(--danger)', background: 'var(--danger)22', border: '1px solid var(--danger)44' }}>
                    Obligatorio
                  </span>
                )}
                <button onClick={() => abrirEditar(r)} className="p-1.5 rounded hover:opacity-80" style={{ color: 'var(--text-muted)' }}><Pencil size={13} /></button>
                <button onClick={() => eliminar(r.id)} className="p-1.5 rounded hover:opacity-80" style={{ color: 'var(--danger)' }}><Trash2 size={13} /></button>
              </div>
            ))}
          </div>
        )}
      </div>

      {showForm && (
        <div className="fixed inset-0 flex items-center justify-center z-50" style={{ background: 'rgba(0,0,0,0.6)' }} onClick={() => setShowForm(false)}>
          <div onClick={(e) => e.stopPropagation()} className="w-[420px] rounded-lg p-4 space-y-3" style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-active)' }}>
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">{editId ? 'Editar regla' : 'Nueva regla de cumplimiento'}</h3>
              <button onClick={() => setShowForm(false)} style={{ color: 'var(--text-muted)' }}><X size={14} /></button>
            </div>
            <div>
              <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Nombre</label>
              <input value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} className="w-full h-8 rounded px-2 text-xs outline-hidden" style={inputStyle()} />
            </div>
            <div>
              <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Descripción</label>
              <textarea value={form.descripcion} onChange={(e) => setForm({ ...form, descripcion: e.target.value })} rows={2} className="w-full rounded px-2 py-1.5 text-xs outline-hidden resize-none" style={inputStyle()} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Tipo de procedimiento</label>
                <select value={form.tipo_procedimiento} onChange={(e) => setForm({ ...form, tipo_procedimiento: e.target.value })} className="w-full h-8 rounded px-2 text-xs outline-hidden" style={inputStyle()}>
                  {TIPOS_PROCEDIMIENTO_COMPLIANCE.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Etapa</label>
                <select value={form.etapa} onChange={(e) => setForm({ ...form, etapa: e.target.value })} className="w-full h-8 rounded px-2 text-xs outline-hidden" style={inputStyle()}>
                  {ETAPAS_COMPLIANCE.map((et) => <option key={et} value={et}>{et}</option>)}
                </select>
              </div>
            </div>
            <div>
              <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Condición de evaluación (opcional)</label>
              <input value={form.condicion_evaluacion} onChange={(e) => setForm({ ...form, condicion_evaluacion: e.target.value })} placeholder="p. ej. estado == 'CONVOCATORIA' AND fecha IS NOT NULL" className="w-full h-8 rounded px-2 text-xs outline-hidden font-mono" style={inputStyle()} />
            </div>
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
                <input type="checkbox" checked={form.obligatorio} onChange={(e) => setForm({ ...form, obligatorio: e.target.checked })} /> Obligatoria
              </label>
              <label className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
                <input type="checkbox" checked={form.activa} onChange={(e) => setForm({ ...form, activa: e.target.checked })} /> Activa
              </label>
            </div>
            <button
              onClick={guardar}
              disabled={guardando || !form.nombre.trim()}
              className="w-full h-9 rounded text-sm font-semibold flex items-center justify-center gap-2 disabled:opacity-50"
              style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}
            >
              {guardando ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
              {editId ? 'Guardar cambios' : 'Crear regla'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
