/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { useCallback, useEffect, useState } from 'react';
import { Plus, Loader2, AlertCircle, MessageSquareWarning, X, Save } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';
import { useExpedienteStore } from '@/stores/useExpedienteStore';
import {
  ESTADOS_INCONFORMIDAD,
  type Inconformidad, type InconformidadInput,
} from '@/lib/megalodon-client';

function inputStyle(): React.CSSProperties {
  return { background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-primary)' };
}

function estadoColor(estado: string): string {
  switch (estado) {
    case 'REGISTRADA': return 'var(--info)';
    case 'EN_ANALISIS': return 'var(--amber)';
    case 'RESPONDIDA': return 'var(--accent-cyan)';
    case 'RESUELTA': return 'var(--success)';
    case 'ARCHIVADA': return 'var(--text-muted)';
    default: return 'var(--text-secondary)';
  }
}

function fmtFecha(iso?: string): string {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleDateString('es-MX'); } catch { return iso; }
}

const CREAR_VACIA = (expedienteId: string): InconformidadInput => ({
  expediente_id: expedienteId, licitacion_id: '', contrato_id: '', titulo: '', descripcion: '',
  severidad: undefined, regla_id: '', asignado_a: '', fecha_limite: '',
});

const SEVERIDADES = ['BAJA', 'MEDIA', 'ALTA', 'CRITICA'] as const;

interface EditState {
  estado: string;
  severidad: string;
  asignado_a: string;
  fecha_limite: string;
  respuesta: string;
  resolucion: string;
  dictamen: string;
  fecha_dictamen: string;
}

export default function InconformidadesPanel() {
  const expedienteActivoId = useExpedienteStore((s) => s.expedienteActivoId);
  const [items, setItems] = useState<Inconformidad[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [filtroEstado, setFiltroEstado] = useState('');
  const [filtroExpediente, setFiltroExpediente] = useState('');

  const [showCreate, setShowCreate] = useState(false);
  const [crearForm, setCrearForm] = useState<InconformidadInput>(CREAR_VACIA(''));
  const [guardando, setGuardando] = useState(false);

  const [editItem, setEditItem] = useState<Inconformidad | null>(null);
  const [editForm, setEditForm] = useState<EditState>({
    estado: '', severidad: '', asignado_a: '', fecha_limite: '',
    respuesta: '', resolucion: '', dictamen: '', fecha_dictamen: '',
  });

  const cargar = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const res = await megalodonClient.compliance.inconformidades.listar({
        estado: filtroEstado || undefined,
        expediente_id: filtroExpediente.trim() || undefined,
        limit: 200,
      });
      setItems(res.items); setTotal(res.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudieron cargar las inconformidades');
    } finally {
      setLoading(false);
    }
  }, [filtroEstado, filtroExpediente]);

  useEffect(() => { void cargar(); }, [cargar]);

  const abrirNueva = () => {
    setCrearForm(CREAR_VACIA(expedienteActivoId || filtroExpediente || ''));
    setShowCreate(true);
  };

  const crear = async () => {
    if (!crearForm.expediente_id.trim() || !crearForm.titulo.trim() || !crearForm.descripcion.trim()) return;
    setGuardando(true); setError('');
    try {
      const payload: InconformidadInput = {
        expediente_id: crearForm.expediente_id.trim(),
        titulo: crearForm.titulo.trim(),
        descripcion: crearForm.descripcion.trim(),
        licitacion_id: crearForm.licitacion_id?.trim() || undefined,
        contrato_id: crearForm.contrato_id?.trim() || undefined,
        severidad: crearForm.severidad || undefined,
        regla_id: crearForm.regla_id?.trim() || undefined,
        asignado_a: crearForm.asignado_a?.trim() || undefined,
        fecha_limite: crearForm.fecha_limite?.trim() || undefined,
      };
      await megalodonClient.compliance.inconformidades.crear(payload);
      setShowCreate(false);
      await cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo registrar la inconformidad');
    } finally {
      setGuardando(false);
    }
  };

  const abrirDetalle = (item: Inconformidad) => {
    setEditItem(item);
    setEditForm({
      estado: item.estado,
      severidad: item.severidad || '',
      asignado_a: item.asignado_a || '',
      fecha_limite: item.fecha_limite ? item.fecha_limite.slice(0, 10) : '',
      respuesta: item.respuesta || '',
      resolucion: item.resolucion || '',
      dictamen: item.dictamen || '',
      fecha_dictamen: item.fecha_dictamen ? item.fecha_dictamen.slice(0, 10) : '',
    });
  };

  const guardarDetalle = async () => {
    if (!editItem) return;
    setGuardando(true); setError('');
    try {
      await megalodonClient.compliance.inconformidades.actualizar(editItem.id, {
        estado: editForm.estado,
        severidad: editForm.severidad || undefined,
        asignado_a: editForm.asignado_a.trim() || undefined,
        fecha_limite: editForm.fecha_limite || undefined,
        respuesta: editForm.respuesta.trim() || undefined,
        resolucion: editForm.resolucion.trim() || undefined,
        dictamen: editForm.dictamen.trim() || undefined,
        fecha_dictamen: editForm.fecha_dictamen || undefined,
      });
      setEditItem(null);
      await cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo actualizar la inconformidad');
    } finally {
      setGuardando(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-3 py-2 flex-wrap" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        <select value={filtroEstado} onChange={(e) => setFiltroEstado(e.target.value)} className="h-8 rounded px-2 text-xs outline-hidden" style={inputStyle()}>
          <option value="">Todos los estados</option>
          {ESTADOS_INCONFORMIDAD.map((e) => <option key={e} value={e}>{e}</option>)}
        </select>
        <input
          value={filtroExpediente}
          onChange={(e) => setFiltroExpediente(e.target.value)}
          placeholder="Filtrar por expediente_id"
          className="h-8 rounded px-2 text-xs outline-hidden w-48"
          style={inputStyle()}
        />
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{total} inconformidad{total !== 1 ? 'es' : ''}</span>
        <div className="flex-1" />
        <button onClick={abrirNueva} className="flex items-center gap-1.5 h-8 px-3 rounded text-xs font-medium" style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}>
          <Plus size={13} /> Nueva inconformidad
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
            Sin inconformidades registradas.
          </div>
        ) : (
          <div className="divide-y" style={{ borderColor: 'var(--border-subtle)' }}>
            {items.map((i) => (
              <button
                key={i.id}
                onClick={() => abrirDetalle(i)}
                className="w-full flex items-start gap-3 px-3 py-2.5 text-left hover:opacity-90"
                style={{ borderBottom: '1px solid var(--border-subtle)' }}
              >
                <MessageSquareWarning size={15} className="mt-0.5 shrink-0" style={{ color: estadoColor(i.estado) }} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{i.titulo}</p>
                  <p className="text-[11px] truncate" style={{ color: 'var(--text-muted)' }}>{i.descripcion}</p>
                  <p className="text-[10px] mt-0.5" style={{ color: 'var(--text-muted)' }}>Expediente {i.expediente_id} · {fmtFecha(i.created_at)}</p>
                </div>
                <span
                  className="text-[10px] font-medium px-1.5 py-0.5 rounded shrink-0"
                  style={{ color: estadoColor(i.estado), background: `${estadoColor(i.estado)}22`, border: `1px solid ${estadoColor(i.estado)}44` }}
                >
                  {i.estado}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {showCreate && (
        <div className="fixed inset-0 flex items-center justify-center z-50" style={{ background: 'rgba(0,0,0,0.6)' }} onClick={() => setShowCreate(false)}>
          <div onClick={(e) => e.stopPropagation()} className="w-[440px] rounded-lg p-4 space-y-3" style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-active)' }}>
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">Nueva inconformidad</h3>
              <button onClick={() => setShowCreate(false)} style={{ color: 'var(--text-muted)' }}><X size={14} /></button>
            </div>
            <div>
              <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Expediente ID</label>
              <input value={crearForm.expediente_id} onChange={(e) => setCrearForm({ ...crearForm, expediente_id: e.target.value })} className="w-full h-8 rounded px-2 text-xs outline-hidden font-mono" style={inputStyle()} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Licitación ID (opcional)</label>
                <input value={crearForm.licitacion_id} onChange={(e) => setCrearForm({ ...crearForm, licitacion_id: e.target.value })} className="w-full h-8 rounded px-2 text-xs outline-hidden font-mono" style={inputStyle()} />
              </div>
              <div>
                <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Contrato ID (opcional)</label>
                <input value={crearForm.contrato_id} onChange={(e) => setCrearForm({ ...crearForm, contrato_id: e.target.value })} className="w-full h-8 rounded px-2 text-xs outline-hidden font-mono" style={inputStyle()} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Severidad (opcional)</label>
                <select value={crearForm.severidad || ''} onChange={(e) => setCrearForm({ ...crearForm, severidad: (e.target.value || undefined) as any })} className="w-full h-8 rounded px-2 text-xs outline-hidden" style={inputStyle()}>
                  <option value="">Sin definir</option>
                  {SEVERIDADES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Fecha límite (opcional)</label>
                <input type="date" value={crearForm.fecha_limite} onChange={(e) => setCrearForm({ ...crearForm, fecha_limite: e.target.value })} className="w-full h-8 rounded px-2 text-xs outline-hidden" style={inputStyle()} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Regla vinculada ID (opcional)</label>
                <input value={crearForm.regla_id} onChange={(e) => setCrearForm({ ...crearForm, regla_id: e.target.value })} className="w-full h-8 rounded px-2 text-xs outline-hidden font-mono" style={inputStyle()} />
              </div>
              <div>
                <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Asignado a (user ID, opcional)</label>
                <input value={crearForm.asignado_a} onChange={(e) => setCrearForm({ ...crearForm, asignado_a: e.target.value })} className="w-full h-8 rounded px-2 text-xs outline-hidden font-mono" style={inputStyle()} />
              </div>
            </div>
            <div>
              <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Título</label>
              <input value={crearForm.titulo} onChange={(e) => setCrearForm({ ...crearForm, titulo: e.target.value })} className="w-full h-8 rounded px-2 text-xs outline-hidden" style={inputStyle()} />
            </div>
            <div>
              <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Descripción</label>
              <textarea value={crearForm.descripcion} onChange={(e) => setCrearForm({ ...crearForm, descripcion: e.target.value })} rows={3} className="w-full rounded px-2 py-1.5 text-xs outline-hidden resize-none" style={inputStyle()} />
            </div>
            <button
              onClick={crear}
              disabled={guardando || !crearForm.expediente_id.trim() || !crearForm.titulo.trim() || !crearForm.descripcion.trim()}
              className="w-full h-9 rounded text-sm font-semibold flex items-center justify-center gap-2 disabled:opacity-50"
              style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}
            >
              {guardando ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
              Registrar inconformidad
            </button>
          </div>
        </div>
      )}

      {editItem && (
        <div className="fixed inset-0 flex items-center justify-center z-50" style={{ background: 'rgba(0,0,0,0.6)' }} onClick={() => setEditItem(null)}>
          <div onClick={(e) => e.stopPropagation()} className="w-[460px] max-h-[85vh] overflow-auto rounded-lg p-4 space-y-3" style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-active)' }}>
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">{editItem.titulo}</h3>
              <button onClick={() => setEditItem(null)} style={{ color: 'var(--text-muted)' }}><X size={14} /></button>
            </div>
            <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>{editItem.descripcion}</p>
            <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>Expediente {editItem.expediente_id} · Registrada {fmtFecha(editItem.created_at)}</p>

            <div>
              <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Estado</label>
              <select value={editForm.estado} onChange={(e) => setEditForm({ ...editForm, estado: e.target.value })} className="w-full h-8 rounded px-2 text-xs outline-hidden" style={inputStyle()}>
                {ESTADOS_INCONFORMIDAD.map((e) => <option key={e} value={e}>{e}</option>)}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Severidad</label>
                <select value={editForm.severidad} onChange={(e) => setEditForm({ ...editForm, severidad: e.target.value })} className="w-full h-8 rounded px-2 text-xs outline-hidden" style={inputStyle()}>
                  <option value="">Sin definir</option>
                  {SEVERIDADES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Fecha límite</label>
                <input type="date" value={editForm.fecha_limite} onChange={(e) => setEditForm({ ...editForm, fecha_limite: e.target.value })} className="w-full h-8 rounded px-2 text-xs outline-hidden" style={inputStyle()} />
              </div>
            </div>
            <div>
              <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Asignado a (user ID)</label>
              <input value={editForm.asignado_a} onChange={(e) => setEditForm({ ...editForm, asignado_a: e.target.value })} className="w-full h-8 rounded px-2 text-xs outline-hidden font-mono" style={inputStyle()} />
            </div>
            <div>
              <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Respuesta del proveedor</label>
              <textarea value={editForm.respuesta} onChange={(e) => setEditForm({ ...editForm, respuesta: e.target.value })} rows={2} className="w-full rounded px-2 py-1.5 text-xs outline-hidden resize-none" style={inputStyle()} />
            </div>
            <div>
              <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Resolución</label>
              <textarea value={editForm.resolucion} onChange={(e) => setEditForm({ ...editForm, resolucion: e.target.value })} rows={2} className="w-full rounded px-2 py-1.5 text-xs outline-hidden resize-none" style={inputStyle()} />
            </div>
            <div>
              <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Dictamen</label>
              <textarea value={editForm.dictamen} onChange={(e) => setEditForm({ ...editForm, dictamen: e.target.value })} rows={2} className="w-full rounded px-2 py-1.5 text-xs outline-hidden resize-none" style={inputStyle()} />
            </div>
            <div>
              <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Fecha de dictamen</label>
              <input type="date" value={editForm.fecha_dictamen} onChange={(e) => setEditForm({ ...editForm, fecha_dictamen: e.target.value })} className="w-full h-8 rounded px-2 text-xs outline-hidden" style={inputStyle()} />
            </div>
            <button
              onClick={guardarDetalle}
              disabled={guardando}
              className="w-full h-9 rounded text-sm font-semibold flex items-center justify-center gap-2 disabled:opacity-50"
              style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}
            >
              {guardando ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
              Guardar cambios
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
