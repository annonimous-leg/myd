/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

/**
 * Panel de Contrato — ciclo de vida completo.
 * Antes: solo "crear contrato" + un botón fijo "Poner en vigencia".
 * Se agrega lo que pedía la auditoría (modificatorios, garantías,
 * penalizaciones) más una máquina de estados real en vez del botón fijo.
 *
 * Al mapear el backend para construir esto encontré 4 problemas reales que
 * ya se corrigieron en backend/app/services/contrato_service.py y
 * backend/app/api/v1/contratos.py (ver ese turno para el detalle):
 *  - listar_garantias no existía en el servicio -> 500 garantizado.
 *  - listar_modificatorios / listar_entregables devolvían dicts sin
 *    contrato_id/created_at (requeridos por el schema) -> 500 de validación
 *    en cuanto hubiera un registro real.
 *  - no existía forma de listar penalizaciones ya creadas (solo crear).
 * Este panel asume que esos 4 endpoints ya responden con la forma real.
 *
 * Entregables/estimaciones NO se tocan aquí a propósito: ya viven en
 * EstimacionesPanel.tsx (fase "Ejecución"), que ya los cubre por completo.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  FileText, Play, AlertTriangle, Plus, X, Loader2, RefreshCw,
  ShieldCheck, FileWarning, Gavel, ChevronRight, Ban, PauseCircle, CheckCircle2,
  type LucideIcon,
} from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';
import { useAuthStore } from '@/stores/useAuthStore';
import {
  TIPOS_GARANTIA, TIPOS_MODIFICACION, TIPOS_PENALIZACION, TRANSICIONES_CONTRATO, ESTADOS_CONTRATO,
  type Contrato, type Modificatorio, type ModificatorioInput,
  type Garantia, type GarantiaInput, type AlertaGarantia,
  type Penalizacion, type PenalizacionInput, type ResumenContrato,
} from '@/lib/megalodon-client';

// ---------- helpers ----------
function money(n?: number | null): string {
  if (n === undefined || n === null) return '—';
  return Number(n).toLocaleString('es-MX', { style: 'currency', currency: 'MXN', maximumFractionDigits: 0 });
}
function fecha(iso?: string | null): string {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleDateString('es-MX'); } catch { return iso; }
}
function inputCls(): string {
  return 'w-full rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm outline-hidden focus:border-orange-500/50';
}

function Metric({ l, v, tone }: { l: string; v: string; tone?: string }) {
  return (
    <div className="rounded-lg border border-zinc-800 p-3">
      <div className="text-xs text-zinc-500">{l}</div>
      <div className={`font-semibold mt-1 ${tone || 'text-zinc-200'}`}>{v}</div>
    </div>
  );
}

const ESTADO_TONE: Record<string, string> = {
  EN_FIRMA: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
  VIGENTE: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
  EN_MODIFICACION: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/30',
  SUSPENDIDO: 'text-orange-400 bg-orange-500/10 border-orange-500/30',
  TERMINADO: 'text-zinc-400 bg-zinc-500/10 border-zinc-500/30',
  RESCINDIDO: 'text-rose-400 bg-rose-500/10 border-rose-500/30',
  CERRADO: 'text-zinc-500 bg-zinc-800/50 border-zinc-700',
};

const TRANSICION_ICON: Record<string, LucideIcon> = {
  VIGENTE: Play, EN_MODIFICACION: FileText, SUSPENDIDO: PauseCircle,
  TERMINADO: CheckCircle2, RESCINDIDO: Ban, CERRADO: ShieldCheck,
};

type SubTab = 'resumen' | 'modificatorios' | 'garantias' | 'penalizaciones';
type Workspace = { licitacion: { proposicion_ganadora_id: string | null }; proposiciones: any[]; contrato: Contrato | null };

export default function ContratoPanel({ expedienteId }: { expedienteId: string }) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const winner = workspace?.licitacion?.proposicion_ganadora_id || '';
  const role = useAuthStore(s => s.user?.role);
  const canApprove = ['admin', 'superadmin', 'revisor'].includes(role || '');
  const [number, setNumber] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [subTab, setSubTab] = useState<SubTab>('resumen');

  const [resumen, setResumen] = useState<ResumenContrato | null>(null);
  const [modificatorios, setModificatorios] = useState<Modificatorio[]>([]);
  const [garantias, setGarantias] = useState<Garantia[]>([]);
  const [alertasGarantia, setAlertasGarantia] = useState<AlertaGarantia[]>([]);
  const [penalizaciones, setPenalizaciones] = useState<Penalizacion[]>([]);

  const load = useCallback(async () => {
    try {
      const ws = await megalodonClient.licitacionesObra.workspace(expedienteId);
      setWorkspace(ws);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [expedienteId]);

  useEffect(() => { void load(); }, [load]);

  const c = workspace?.contrato || null;

  const loadDetalle = useCallback(async () => {
    if (!c?.id) return;
    try {
      const [r, m, g, av, p] = await Promise.all([
        megalodonClient.contratos.resumen(c.id),
        megalodonClient.contratos.modificatorios.listar(c.id),
        megalodonClient.contratos.garantias.listar(c.id),
        megalodonClient.contratos.garantias.vigencia(c.id),
        megalodonClient.contratos.penalizaciones.listar(c.id),
      ]);
      setResumen(r); setModificatorios(m); setGarantias(g); setAlertasGarantia(av); setPenalizaciones(p);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [c?.id]);

  useEffect(() => { void loadDetalle(); }, [loadDetalle]);

  const create = async () => {
    setBusy(true); setError('');
    try {
      await megalodonClient.licitacionesObra.contrato.generar(expedienteId, { proposicion_id: winner, numero_contrato: number });
      await load();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };

  const transicionar = async (nuevo: typeof ESTADOS_CONTRATO[number]) => {
    if (!c?.id) return;
    if (nuevo === 'RESCINDIDO' && !window.confirm('¿Rescindir el contrato? Esta acción no se puede deshacer.')) return;
    setBusy(true); setError('');
    try {
      await megalodonClient.contratos.transicionar(c.id, nuevo);
      await load();
      await loadDetalle();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };

  if (!workspace) {
    return (
      <div className="flex items-center justify-center h-40 text-sm text-zinc-500 gap-2">
        <Loader2 className="w-4 h-4 animate-spin" /> Cargando...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2"><FileText className="w-5 h-5 text-orange-400" /> Contrato</h2>
          <p className="text-sm text-zinc-500">El contrato conserva el proveedor, monto y plazo del fallo registrado y queda en estado EN_FIRMA.</p>
        </div>
        <button onClick={() => void load()} className="flex items-center gap-2 px-3 py-2 border border-zinc-700 rounded-lg text-sm text-zinc-400 hover:bg-zinc-800/60">
          <RefreshCw className="w-4 h-4" /> Actualizar
        </button>
      </header>

      {error && (
        <div className="rounded-lg border border-red-800 bg-red-950/30 p-3 text-sm text-red-300 flex gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" /> {error}
        </div>
      )}

      {!c ? (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5 space-y-4">
          <select value={winner} disabled aria-label="Proposición ganadora del fallo" className={inputCls()}>
            <option value="">Pendiente de fallo registrado</option>
            {(workspace.proposiciones || []).filter((p: any) => p.id === winner).map((p: any) => (
              <option key={p.id} value={p.id}>{p.proveedor?.razon_social || p.proveedor_id} · {money(p.monto)}</option>
            ))}
          </select>
          <input value={number} onChange={(e) => setNumber(e.target.value)} placeholder="Número de contrato" className={inputCls()} aria-label="Número de contrato" />
          <button
            disabled={busy || !winner || !number.trim() || !canApprove}
            onClick={() => void create()}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-orange-500/20 border border-orange-500/30 text-orange-300 disabled:opacity-40"
          >
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />} Crear contrato
          </button>
        </div>
      ) : (
        <>
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5 space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Metric l="Número" v={c.numero_contrato} />
              <Metric l="Estado" v={c.estado} tone={ESTADO_TONE[c.estado]?.split(' ')[0]} />
              <Metric l="Monto total" v={money(resumen?.monto_total ?? c.monto_total)} />
              <Metric l="Avance físico" v={`${c.avance_fisico ?? 0}%`} />
            </div>

            {resumen && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Metric l="Monto original" v={money(resumen.monto_original)} />
                <Metric l="Modificaciones" v={money(resumen.monto_modificaciones)} tone={resumen.monto_modificaciones > 0 ? 'text-cyan-400' : undefined} />
                <Metric l="Penalizaciones" v={money(resumen.monto_penalizaciones)} tone={resumen.monto_penalizaciones > 0 ? 'text-rose-400' : undefined} />
                <Metric l="Plazo actual" v={`${resumen.plazo_actual} días`} />
              </div>
            )}

            {alertasGarantia.filter((a) => a.estado !== 'VIGENTE').length > 0 && (
              <div className="space-y-1.5">
                {alertasGarantia.filter((a) => a.estado !== 'VIGENTE').map((a) => (
                  <div key={a.garantia_id} className={`flex items-center gap-2 rounded-lg px-3 py-2 text-xs border ${a.estado === 'VENCIDA' ? 'border-rose-800 bg-rose-950/30 text-rose-300' : 'border-amber-800 bg-amber-950/30 text-amber-300'}`}>
                    <FileWarning className="w-3.5 h-3.5 shrink-0" />
                    Garantía {a.tipo} ({a.numero_poliza || 'sin póliza'}): {a.estado === 'VENCIDA' ? 'vencida' : `vence en ${a.dias_restantes} días`}
                  </div>
                ))}
              </div>
            )}

            {/* Máquina de estados: sólo se ofrecen las transiciones que el backend permite desde el estado actual (TRANSICIONES_CONTRATO espeja ContratoService.TRANSICIONES) */}
            {TRANSICIONES_CONTRATO[c.estado]?.length > 0 && (
              <div className="flex items-center gap-2 flex-wrap pt-1">
                <span className="text-xs text-zinc-500 flex items-center gap-1"><ChevronRight className="w-3.5 h-3.5" /> Transicionar a:</span>
                {TRANSICIONES_CONTRATO[c.estado].map((estado) => {
                  const Icon = TRANSICION_ICON[estado] || Play;
                  return (
                    <button
                      key={estado}
                      disabled={busy || !canApprove}
                      onClick={() => void transicionar(estado as typeof ESTADOS_CONTRATO[number])}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border disabled:opacity-40 ${ESTADO_TONE[estado] || 'text-zinc-300 bg-zinc-800/50 border-zinc-700'}`}
                    >
                      <Icon className="w-3.5 h-3.5" /> {estado}
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <div className="flex items-center gap-1 border-b border-zinc-800 overflow-x-auto">
            {([
              ['resumen', 'Resumen', ShieldCheck],
              ['modificatorios', `Modificatorios (${modificatorios.length})`, FileText],
              ['garantias', `Garantías (${garantias.length})`, ShieldCheck],
              ['penalizaciones', `Penalizaciones (${penalizaciones.length})`, Gavel],
            ] as [SubTab, string, LucideIcon][]).map(([id, label, Icon]) => (
              <button
                key={id}
                onClick={() => setSubTab(id)}
                className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium border-b-2 whitespace-nowrap ${subTab === id ? 'text-orange-400 border-orange-400' : 'text-zinc-500 border-transparent hover:text-zinc-300'}`}
              >
                <Icon className="w-3.5 h-3.5" /> {label}
              </button>
            ))}
          </div>

          {subTab === 'resumen' && (
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5 text-sm text-zinc-400 space-y-2">
              <p><span className="text-zinc-500">Objeto:</span> {c.objeto}</p>
              <p><span className="text-zinc-500">Firma:</span> {fecha(c.fecha_firma)} · <span className="text-zinc-500">Inicio:</span> {fecha(c.fecha_inicio)} · <span className="text-zinc-500">Término:</span> {fecha(c.fecha_termino)}</p>
              {resumen && (
                <p className="text-zinc-500">
                  {resumen.total_modificatorios} modificatorio{resumen.total_modificatorios !== 1 ? 's' : ''} · {resumen.total_garantias} garantía{resumen.total_garantias !== 1 ? 's' : ''} · {resumen.total_entregables} entregable{resumen.total_entregables !== 1 ? 's' : ''} (ver fase Ejecución) · {resumen.total_penalizaciones} penalización{resumen.total_penalizaciones !== 1 ? 'es' : ''}
                </p>
              )}
            </div>
          )}
          {subTab === 'modificatorios' && <ModificatoriosSection contratoId={c.id} items={modificatorios} onChange={loadDetalle} />}
          {subTab === 'garantias' && <GarantiasSection contratoId={c.id} items={garantias} onChange={loadDetalle} />}
          {subTab === 'penalizaciones' && <PenalizacionesSection contratoId={c.id} items={penalizaciones} onChange={loadDetalle} />}
        </>
      )}
    </div>
  );
}

// ───────────────────────── Modificatorios ─────────────────────────

const MOD_VACIO: ModificatorioInput = { numero: '', tipo: TIPOS_MODIFICACION[0], descripcion: '', justificacion: '' };

function ModificatoriosSection({ contratoId, items, onChange }: { contratoId: string; items: Modificatorio[]; onChange: () => void }) {
  const [show, setShow] = useState(false);
  const [form, setForm] = useState<ModificatorioInput>(MOD_VACIO);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const guardar = async () => {
    if (!form.numero.trim()) return;
    setBusy(true); setError('');
    try {
      await megalodonClient.contratos.modificatorios.crear(contratoId, {
        ...form,
        monto_anterior: form.monto_anterior || undefined,
        monto_nuevo: form.monto_nuevo || undefined,
        plazo_anterior: form.plazo_anterior || undefined,
        plazo_nuevo: form.plazo_nuevo || undefined,
      });
      setShow(false); setForm(MOD_VACIO); onChange();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <button onClick={() => setShow(true)} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-orange-500/20 border border-orange-500/30 text-orange-300 text-xs">
          <Plus className="w-3.5 h-3.5" /> Nuevo convenio modificatorio
        </button>
      </div>
      {error && <div className="text-xs text-red-400">{error}</div>}
      {items.length === 0 ? (
        <div className="rounded-xl border border-zinc-800 p-6 text-sm text-zinc-500 text-center">Sin modificatorios registrados.</div>
      ) : (
        <div className="space-y-2">
          {items.map((m) => (
            <div key={m.id} className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
              <div className="flex items-center justify-between">
                <b className="text-sm text-zinc-200">Convenio {m.numero}</b>
                <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-cyan-500/10 border border-cyan-500/30 text-cyan-300">{m.tipo}</span>
              </div>
              {m.descripcion && <p className="text-xs text-zinc-500 mt-1">{m.descripcion}</p>}
              <div className="flex gap-4 text-xs text-zinc-400 mt-2 flex-wrap">
                {(m.monto_anterior !== undefined || m.monto_nuevo !== undefined) && <span>{money(m.monto_anterior)} → {money(m.monto_nuevo)}</span>}
                {(m.plazo_anterior !== undefined || m.plazo_nuevo !== undefined) && <span>{m.plazo_anterior ?? '—'} → {m.plazo_nuevo ?? '—'} días</span>}
                <span className="text-zinc-600">{fecha(m.fecha_aprobacion) !== '—' ? `Aprobado ${fecha(m.fecha_aprobacion)}` : 'Pendiente de aprobación'}</span>
              </div>
              {m.justificacion && <p className="text-xs text-zinc-600 mt-1 italic">{m.justificacion}</p>}
            </div>
          ))}
        </div>
      )}

      {show && (
        <div className="fixed inset-0 flex items-center justify-center z-50 bg-black/60" onClick={() => setShow(false)}>
          <div onClick={(e) => e.stopPropagation()} className="w-[440px] max-h-[85vh] overflow-auto rounded-xl bg-zinc-900 border border-zinc-700 p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-zinc-200">Nuevo convenio modificatorio</h3>
              <button onClick={() => setShow(false)} className="text-zinc-500"><X className="w-4 h-4" /></button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <input value={form.numero} onChange={(e) => setForm({ ...form, numero: e.target.value })} placeholder="Número" className={inputCls()} />
              <select value={form.tipo} onChange={(e) => setForm({ ...form, tipo: e.target.value as ModificatorioInput['tipo'] })} className={inputCls()}>
                {TIPOS_MODIFICACION.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <textarea value={form.descripcion} onChange={(e) => setForm({ ...form, descripcion: e.target.value })} placeholder="Descripción" rows={2} className={inputCls()} />
            <div className="grid grid-cols-2 gap-3">
              <input type="number" value={form.monto_anterior ?? ''} onChange={(e) => setForm({ ...form, monto_anterior: e.target.value ? Number(e.target.value) : undefined })} placeholder="Monto anterior" className={inputCls()} />
              <input type="number" value={form.monto_nuevo ?? ''} onChange={(e) => setForm({ ...form, monto_nuevo: e.target.value ? Number(e.target.value) : undefined })} placeholder="Monto nuevo" className={inputCls()} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <input type="number" value={form.plazo_anterior ?? ''} onChange={(e) => setForm({ ...form, plazo_anterior: e.target.value ? Number(e.target.value) : undefined })} placeholder="Plazo anterior (días)" className={inputCls()} />
              <input type="number" value={form.plazo_nuevo ?? ''} onChange={(e) => setForm({ ...form, plazo_nuevo: e.target.value ? Number(e.target.value) : undefined })} placeholder="Plazo nuevo (días)" className={inputCls()} />
            </div>
            <textarea value={form.justificacion} onChange={(e) => setForm({ ...form, justificacion: e.target.value })} placeholder="Justificación" rows={2} className={inputCls()} />
            <button
              disabled={busy || !form.numero.trim()}
              onClick={() => void guardar()}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-orange-500/20 border border-orange-500/30 text-orange-300 disabled:opacity-40"
            >
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Registrar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ───────────────────────── Garantías ─────────────────────────

const GAR_VACIA: GarantiaInput = { tipo: TIPOS_GARANTIA[0], monto: 0, institucion: '', numero_poliza: '', vigencia_inicio: '', vigencia_fin: '' };

function GarantiasSection({ contratoId, items, onChange }: { contratoId: string; items: Garantia[]; onChange: () => void }) {
  const [show, setShow] = useState(false);
  const [form, setForm] = useState<GarantiaInput>(GAR_VACIA);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const guardar = async () => {
    if (!form.monto || form.monto <= 0) return;
    setBusy(true); setError('');
    try {
      await megalodonClient.contratos.garantias.crear(contratoId, form);
      setShow(false); setForm(GAR_VACIA); onChange();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <button onClick={() => setShow(true)} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-orange-500/20 border border-orange-500/30 text-orange-300 text-xs">
          <Plus className="w-3.5 h-3.5" /> Nueva garantía
        </button>
      </div>
      {error && <div className="text-xs text-red-400">{error}</div>}
      {items.length === 0 ? (
        <div className="rounded-xl border border-zinc-800 p-6 text-sm text-zinc-500 text-center">Sin garantías registradas.</div>
      ) : (
        <div className="space-y-2">
          {items.map((g) => (
            <div key={g.id} className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <b className="text-sm text-zinc-200">{g.tipo}</b>
                  {g.liberada && <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-zinc-700">Liberada</span>}
                  {g.ejecutada && <span className="text-[10px] px-1.5 py-0.5 rounded bg-rose-500/10 text-rose-300 border border-rose-500/30">Ejecutada</span>}
                </div>
                <p className="text-xs text-zinc-500 mt-0.5 truncate">{g.institucion || 'Sin institución'} {g.numero_poliza ? `· Póliza ${g.numero_poliza}` : ''}</p>
                <p className="text-xs text-zinc-600">{fecha(g.vigencia_inicio)} → {fecha(g.vigencia_fin)}</p>
              </div>
              <span className="text-sm font-mono text-zinc-300 shrink-0">{money(g.monto)}</span>
            </div>
          ))}
        </div>
      )}

      {show && (
        <div className="fixed inset-0 flex items-center justify-center z-50 bg-black/60" onClick={() => setShow(false)}>
          <div onClick={(e) => e.stopPropagation()} className="w-[420px] rounded-xl bg-zinc-900 border border-zinc-700 p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-zinc-200">Nueva garantía</h3>
              <button onClick={() => setShow(false)} className="text-zinc-500"><X className="w-4 h-4" /></button>
            </div>
            <select value={form.tipo} onChange={(e) => setForm({ ...form, tipo: e.target.value as GarantiaInput['tipo'] })} className={inputCls()}>
              {TIPOS_GARANTIA.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <input type="number" value={form.monto || ''} onChange={(e) => setForm({ ...form, monto: Number(e.target.value) })} placeholder="Monto" className={inputCls()} />
            <input value={form.institucion} onChange={(e) => setForm({ ...form, institucion: e.target.value })} placeholder="Institución afianzadora" className={inputCls()} />
            <input value={form.numero_poliza} onChange={(e) => setForm({ ...form, numero_poliza: e.target.value })} placeholder="Número de póliza" className={inputCls()} />
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[11px] text-zinc-500">Vigencia inicio</label>
                <input type="date" value={form.vigencia_inicio} onChange={(e) => setForm({ ...form, vigencia_inicio: e.target.value })} className={inputCls()} />
              </div>
              <div>
                <label className="text-[11px] text-zinc-500">Vigencia fin</label>
                <input type="date" value={form.vigencia_fin} onChange={(e) => setForm({ ...form, vigencia_fin: e.target.value })} className={inputCls()} />
              </div>
            </div>
            <button
              disabled={busy || !form.monto || form.monto <= 0}
              onClick={() => void guardar()}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-orange-500/20 border border-orange-500/30 text-orange-300 disabled:opacity-40"
            >
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Registrar garantía
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ───────────────────────── Penalizaciones ─────────────────────────

const PEN_VACIA: PenalizacionInput = { tipo: TIPOS_PENALIZACION[0], monto: 0, descripcion: '', tope_legal: 0 };

function PenalizacionesSection({ contratoId, items, onChange }: { contratoId: string; items: Penalizacion[]; onChange: () => void }) {
  const [show, setShow] = useState(false);
  const [form, setForm] = useState<PenalizacionInput>(PEN_VACIA);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const guardar = async () => {
    if (!form.descripcion.trim() || !form.monto || form.monto <= 0) return;
    setBusy(true); setError('');
    try {
      await megalodonClient.contratos.penalizaciones.crear(contratoId, { ...form, dias_atraso: form.dias_atraso || undefined });
      setShow(false); setForm(PEN_VACIA); onChange();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <button onClick={() => setShow(true)} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-orange-500/20 border border-orange-500/30 text-orange-300 text-xs">
          <Plus className="w-3.5 h-3.5" /> Nueva penalización
        </button>
      </div>
      {error && <div className="text-xs text-red-400">{error}</div>}
      {items.length === 0 ? (
        <div className="rounded-xl border border-zinc-800 p-6 text-sm text-zinc-500 text-center">Sin penalizaciones registradas.</div>
      ) : (
        <div className="space-y-2">
          {items.map((p) => (
            <div key={p.id} className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 flex-wrap">
                  <b className="text-sm text-zinc-200">{p.tipo}</b>
                  {!p.dentro_tope && <span className="text-[10px] px-1.5 py-0.5 rounded bg-rose-500/10 text-rose-300 border border-rose-500/30">Excede tope legal</span>}
                  {p.aplicada && <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/30">Aplicada</span>}
                </div>
                <span className="text-sm font-mono text-zinc-300 shrink-0">{money(p.monto)}</span>
              </div>
              <p className="text-xs text-zinc-500 mt-1">{p.descripcion}</p>
              <p className="text-xs text-zinc-600 mt-1">
                {p.dias_atraso !== undefined && p.dias_atraso !== null ? `${p.dias_atraso} días de atraso · ` : ''}
                Tope legal {money(p.tope_legal)} {fecha(p.fecha_aplicacion) !== '—' ? `· Aplicada ${fecha(p.fecha_aplicacion)}` : ''}
              </p>
            </div>
          ))}
        </div>
      )}

      {show && (
        <div className="fixed inset-0 flex items-center justify-center z-50 bg-black/60" onClick={() => setShow(false)}>
          <div onClick={(e) => e.stopPropagation()} className="w-[420px] rounded-xl bg-zinc-900 border border-zinc-700 p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-zinc-200">Nueva penalización</h3>
              <button onClick={() => setShow(false)} className="text-zinc-500"><X className="w-4 h-4" /></button>
            </div>
            <select value={form.tipo} onChange={(e) => setForm({ ...form, tipo: e.target.value as PenalizacionInput['tipo'] })} className={inputCls()}>
              {TIPOS_PENALIZACION.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <textarea value={form.descripcion} onChange={(e) => setForm({ ...form, descripcion: e.target.value })} placeholder="Descripción" rows={2} className={inputCls()} />
            <div className="grid grid-cols-2 gap-3">
              <input type="number" value={form.monto || ''} onChange={(e) => setForm({ ...form, monto: Number(e.target.value) })} placeholder="Monto" className={inputCls()} />
              <input type="number" value={form.dias_atraso ?? ''} onChange={(e) => setForm({ ...form, dias_atraso: e.target.value ? Number(e.target.value) : undefined })} placeholder="Días de atraso" className={inputCls()} />
            </div>
            <input type="number" value={form.tope_legal || ''} onChange={(e) => setForm({ ...form, tope_legal: Number(e.target.value) })} placeholder="Tope legal" className={inputCls()} />
            <button
              disabled={busy || !form.descripcion.trim() || !form.monto || form.monto <= 0}
              onClick={() => void guardar()}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-orange-500/20 border border-orange-500/30 text-orange-300 disabled:opacity-40"
            >
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Registrar penalización
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
