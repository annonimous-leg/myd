/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

// =============================================================================
// Megalodon CostOS v3.1 — Main Component (5 Tabs)
// =============================================================================

import { useState, useMemo, useRef, useEffect } from 'react';
import type { CSSProperties } from 'react';
import {
  DollarSign, CheckCircle, AlertTriangle, Clock, Plus, Search,
  Trash2, FileJson, Activity, ShieldCheck,
  Download, Calculator, X, Save, Loader2, FolderKanban, RefreshCw
} from 'lucide-react';
import { useMegalodonStore } from '@/stores/useMegalodonStore';
import { useExpedienteStore } from '@/stores/useExpedienteStore';
import { megalodonClient } from '@/lib/api-client';
import type { Presupuesto, PropuestaLicitacionData, ValidacionResultado, SolicitudActualizacionPrecio } from '@/lib/megalodon-client';
import { PresupuestoGuardado } from './PresupuestoGuardado';
import { CatalogoLibroPicker } from './CatalogoLibroPicker';
import { CatalogoImportadoPicker } from './CatalogoImportadoPicker';
import { ImportacionesCatalogosPanel } from './ImportacionesCatalogosPanel';
import { MaterialIndexadoPicker } from './MaterialIndexadoPicker';
import { FSR_CONST } from './data/legales';
import { computeComplianceScore, getOverallStatus } from './engines/validador';
import { formatMXN, getDefaultSimulationVariables } from './engines/montecarlo';
import { evaluateLegalFramework } from './engines/juridico';
import type { ValidationInput, ValidationRule, ValidationStatus } from './engines/validador';
import type { SimulationResult } from './engines/montecarlo';

type TabId = 'resumen' | 'presupuesto' | 'analisis' | 'validacion' | 'reporte';

interface BudgetLine {
  catalogoApuId?: string;
  actualizacionPrecio?: SolicitudActualizacionPrecio;
  catalogoLibroId?: string;
  sourceLabel?: string;
  id: string;
  conceptKey: string;
  description: string;
  unit: string;
  quantity: number;
  unitPrice: number;
  amount: number;
  status: 'validated' | 'pending' | 'error';
}

const TABS: { id: TabId; label: string }[] = [
  { id: 'resumen', label: 'Resumen' },
  { id: 'presupuesto', label: 'Presupuesto' },
  { id: 'analisis', label: 'Análisis' },
  { id: 'validacion', label: 'Validación' },
  { id: 'reporte', label: 'Reporte' },
];

// ---- KPI Card ----
function KpiCard({ icon: Icon, label, value, color }: {
  icon: React.ComponentType<{ className?: string; style?: CSSProperties }>;
  label: string;
  value: string;
  color: string;
}) {
  return (
    <div className="bg-[#1A1A26] border border-[#2A2A3E] rounded-lg p-4 flex items-start gap-3">
      <div className="p-2 rounded-md" style={{ backgroundColor: `${color}15` }}>
        <Icon className="w-5 h-5" style={{ color }} />
      </div>
      <div>
        <div className="text-[11px] uppercase tracking-wider text-[#8A8578] mb-1">{label}</div>
        <div className="text-lg font-semibold" style={{ color }}>{value}</div>
      </div>
    </div>
  );
}

// ---- Monte Carlo Histogram (canvas bar chart) ----
function HistogramChart({ result }: { result: SimulationResult | null }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!result || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.scale(dpr, dpr);

    ctx.clearRect(0, 0, w, h);

    const { histogram } = result;
    if (histogram.length === 0) return;

    const maxCount = Math.max(...histogram.map((b) => b.count));
    const barW = (w - 40) / histogram.length;
    const chartH = h - 50;

    // Grid lines
    ctx.strokeStyle = 'rgba(42,42,62,0.5)';
    ctx.lineWidth = 0.5;
    for (let i = 0; i <= 4; i++) {
      const y = 10 + (chartH / 4) * i;
      ctx.beginPath();
      ctx.moveTo(30, y);
      ctx.lineTo(w - 10, y);
      ctx.stroke();
    }

    // Bars
    histogram.forEach((bin, i) => {
      const bh = (bin.count / maxCount) * chartH;
      const x = 30 + i * barW;
      const y = 10 + chartH - bh;

      const gradient = ctx.createLinearGradient(0, y, 0, y + bh);
      gradient.addColorStop(0, '#C9A84C');
      gradient.addColorStop(1, '#8B7340');

      ctx.fillStyle = gradient;
      ctx.fillRect(x + 1, y, barW - 2, bh);
    });

    // Percentile lines
    const percentileX = (p: number) => {
      const range = result.p99 - result.p1 || 1;
      return 30 + ((p - result.p1) / range) * (w - 40);
    };

    const drawLine = (value: number, color: string, label: string, dashed = false) => {
      const x = percentileX(value);
      if (x < 30 || x > w - 10) return;
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5;
      if (dashed) ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(x, 10);
      ctx.lineTo(x, 10 + chartH);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = color;
      ctx.font = '10px Inter, sans-serif';
      ctx.fillText(label, x + 2, 8);
    };

    drawLine(result.mean, '#C9A84C', 'Media');
    drawLine(result.p50, '#E8E4DC', 'P50');
    drawLine(result.p95, '#5A9E6F', 'P95', true);

    // Axis labels
    ctx.fillStyle = '#8A8578';
    ctx.font = '10px Inter, sans-serif';
    ctx.fillText(`Min: ${formatMXN(result.p5)}`, 30, h - 8);
    ctx.fillText(`Max: ${formatMXN(result.p95)}`, w - 100, h - 8);
  }, [result]);

  if (!result) return <div className="text-[#8A8578] text-sm">Ejecute la simulación para ver histograma</div>;

  return <canvas ref={canvasRef} className="w-full h-48 rounded-md border border-[#2A2A3E] bg-[#0A0A0F]" />;
}

// ---- Tornado Chart ----
function TornadoChart({ sensitivity }: { sensitivity: SimulationResult['sensitivity'] }) {
  if (!sensitivity || sensitivity.length === 0) return null;
  const maxImpact = Math.max(...sensitivity.map((s) => s.impact));

  return (
    <div className="space-y-1.5">
      {sensitivity.map((item) => {
        const width = (item.impact / maxImpact) * 100;
        return (
          <div key={item.variable} className="flex items-center gap-2 text-xs">
            <div className="w-32 text-right text-[#8A8578] truncate">{item.variable}</div>
            <div className="flex-1 h-5 bg-[#0A0A0F] rounded-sm overflow-hidden relative">
              <div
                className="h-full rounded-sm transition-all"
                style={{ width: `${width}%`, backgroundColor: width > 70 ? '#D4953A' : width > 40 ? '#C9A84C' : '#8B7340' }}
              />
            </div>
            <div className="w-20 text-[#C9A84C] font-mono">{formatMXN(item.impact)}</div>
          </div>
        );
      })}
    </div>
  );
}

// ---- Budget Grid ----
function BudgetGrid() {
  const expedienteActivo = useExpedienteStore((s) => s.expedienteActivo());
  const [lines, setLines] = useState<BudgetLine[]>([]);
  const [search, setSearch] = useState('');
  const [showAddForm, setShowAddForm] = useState(false);
  const [showCatalog, setShowCatalog] = useState(false);
  const [showImportedCatalog, setShowImportedCatalog] = useState(false);
  const [catalogRevision, setCatalogRevision] = useState(0);
  const [showIndices, setShowIndices] = useState(false);
  const [newLine, setNewLine] = useState({ conceptKey: '', description: '', unit: '', quantity: 0, unitPrice: 0 });

  const [presupuestoAbierto, setPresupuestoAbierto] = useState<string | null>(null);
  const listaRequest = useRef(0);
  const [presupuestosGuardados, setPresupuestosGuardados] = useState<Presupuesto[]>([]);
  const [cargandoLista, setCargandoLista] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [mensaje, setMensaje] = useState<{ tipo: 'ok' | 'error'; texto: string } | null>(null);

  const [factorIndirecto, setFactorIndirecto] = useState(0);
  const [factorFinanciamiento, setFactorFinanciamiento] = useState(0);
  const [factorUtilidad, setFactorUtilidad] = useState(0);
  const [factorCargosAdicionales, setFactorCargosAdicionales] = useState(0);
  const [factorImpuesto, setFactorImpuesto] = useState(0);
  const [referenciaParametros, setReferenciaParametros] = useState('');

  const cargarPresupuestos = async () => {
    if (!expedienteActivo) return;
    const request = ++listaRequest.current;
    setCargandoLista(true);
    try {
      const lista = await megalodonClient.presupuestos.list(expedienteActivo.id);
      if (request === listaRequest.current) setPresupuestosGuardados(lista);
    } catch (e) {
      if (request === listaRequest.current) setMensaje({ tipo: 'error', texto: e instanceof Error ? e.message : 'No se pudieron cargar los presupuestos' });
      throw e;
    } finally {
      if (request === listaRequest.current) setCargandoLista(false);
    }
  };

  useEffect(() => {
    setPresupuestoAbierto(null); setPresupuestosGuardados([]); setLines([]); setMensaje(null);
    setFactorIndirecto(0); setFactorFinanciamiento(0); setFactorUtilidad(0);
    setFactorCargosAdicionales(0); setFactorImpuesto(0); setReferenciaParametros('');
    void cargarPresupuestos().catch(() => undefined);
    return () => { listaRequest.current++; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expedienteActivo?.id]);

  const filtered = useMemo(() => {
    if (!search) return lines;
    const s = search.toLowerCase();
    return lines.filter((l) => l.description.toLowerCase().includes(s) || l.conceptKey.toLowerCase().includes(s));
  }, [lines, search]);

  // Misma composición económica que el backend:
  // directo -> indirecto -> financiamiento -> utilidad -> cargos
  // adicionales -> impuesto. El riesgo de este editor permanece en cero.
  const montoDirecto = useMemo(() => lines.reduce((s, l) => s + l.amount, 0), [lines]);
  const montoIndirecto = montoDirecto * factorIndirecto;
  const subtotalConIndirecto = montoDirecto + montoIndirecto;
  const montoFinanciamiento = subtotalConIndirecto * factorFinanciamiento;
  const baseUtilidad = subtotalConIndirecto + montoFinanciamiento;
  const montoUtilidad = baseUtilidad * factorUtilidad;
  const baseCargosAdicionales = baseUtilidad + montoUtilidad;
  const montoCargosAdicionales = baseCargosAdicionales * factorCargosAdicionales;
  const baseImpuesto = baseCargosAdicionales + montoCargosAdicionales;
  const montoImpuesto = baseImpuesto * factorImpuesto;
  const total = baseImpuesto + montoImpuesto;

  const addLine = () => {
    if (!newLine.description || newLine.quantity <= 0 || newLine.unitPrice <= 0) return;
    const id = crypto.randomUUID();
    setLines([...lines, {
      id,
      conceptKey: newLine.conceptKey || id,
      description: newLine.description,
      unit: newLine.unit || 'm2',
      quantity: newLine.quantity,
      unitPrice: newLine.unitPrice,
      amount: newLine.quantity * newLine.unitPrice,
      status: 'pending',
    }]);
    setNewLine({ conceptKey: '', description: '', unit: '', quantity: 0, unitPrice: 0 });
    setShowAddForm(false);
  };

  const removeLine = (id: string) => setLines(lines.filter((l) => l.id !== id));

  const exportJSON = () => {
    const data = { lines, montoDirecto, montoIndirecto, montoFinanciamiento, montoUtilidad,
      montoCargosAdicionales, montoImpuesto, total, exportedAt: new Date().toISOString() };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `megalodon-presupuesto-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const guardarEnBackend = async () => {
    if (!expedienteActivo || lines.length === 0) return;
    if (!referenciaParametros.trim()) {
      setMensaje({ tipo: 'error', texto: 'Indica la fuente o referencia de los parámetros de costeo.' });
      return;
    }
    setGuardando(true);
    setMensaje(null);
    try {
      // Cada línea se manda como partida "tipo tabulador" (precio_unitario
      // directo, sin conceptos/insumos) -- son datos ya capturados a mano
      // en esta rejilla, no un APU que el backend tenga que recalcular.
      const presupuesto = await megalodonClient.presupuestos.create(expedienteActivo.id, {
        nombre: `Presupuesto ${new Date().toLocaleDateString('es-MX')}`,
        partidas: lines.map((l, i) => ({
          numero: i + 1,
          catalogo_libro_id: l.catalogoLibroId,
          catalogo_apu_id: l.catalogoApuId,
          descripcion: l.description,
          unidad: l.unit,
          cantidad: l.quantity,
          precio_unitario: l.unitPrice,
          ...(l.actualizacionPrecio ? { insumos: [{ clave: l.conceptKey, descripcion: l.description,
            tipo: 'MATERIAL', unidad: l.unit, cantidad: 1, actualizacion_precio: l.actualizacionPrecio }] } : {}),
        })),
        parametros_costeo: {
          factor_indirecto: factorIndirecto,
          factor_financiamiento: factorFinanciamiento,
          factor_utilidad: factorUtilidad,
          factor_cargos_adicionales: factorCargosAdicionales,
          factor_impuesto: factorImpuesto,
          factor_riesgo: 0,
          fuente: 'CAPTURA_USUARIO',
          referencia: referenciaParametros.trim(),
        },
      });
      setMensaje({ tipo: 'ok', texto: `Guardado como ${presupuesto.identificador} -- total confirmado por el backend: ${formatMXN(presupuesto.monto_total)}` });
      await cargarPresupuestos();
      setPresupuestoAbierto(presupuesto.id);
    } catch (e) {
      setMensaje({ tipo: 'error', texto: e instanceof Error ? e.message : 'No se pudo guardar el presupuesto' });
    } finally {
      setGuardando(false);
    }
  };

  if (!expedienteActivo) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-2 text-center px-6 h-full text-[#8A8578]">
        <FolderKanban className="w-8 h-8 opacity-50" />
        <p className="text-sm">No hay ningún expediente activo.</p>
        <p className="text-xs">Abre la app &quot;Proyectos&quot; y selecciona o crea un expediente para poder guardar presupuestos reales.</p>
      </div>
    );
  }

  const abierto = presupuestosGuardados.find((p) => p.id === presupuestoAbierto && p.expediente_id === expedienteActivo.id);
  if (abierto) return <PresupuestoGuardado key={`${expedienteActivo.id}:${abierto.id}`} presupuesto={abierto}
    onClose={() => setPresupuestoAbierto(null)} onReload={cargarPresupuestos}
    onChange={(saved) => {
      setPresupuestosGuardados((rows) => [saved, ...rows.filter((r) => r.id !== saved.id)]);
      setPresupuestoAbierto(saved.id);
    }} />;

  return (
    <div className="h-full overflow-y-auto">
      <div className="p-3 flex flex-wrap gap-2">
        {presupuestosGuardados.filter((p) => p.expediente_id === expedienteActivo.id).map((p) =>
          <button key={p.id} onClick={() => setPresupuestoAbierto(p.id)} className="rounded border border-zinc-700 px-3 py-2 text-xs text-zinc-200">
            Abrir {p.nombre} · {p.estado} · {formatMXN(p.monto_total)}
          </button>)}
      </div>
      <h2 className="px-3 text-sm text-zinc-200">Presupuesto nuevo</h2>
      {/* Barra de expediente + presupuestos guardados */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-[#12121A] border-b border-[#2A2A3E] text-[10px] text-[#8A8578]">
        <span className="flex items-center gap-1.5">
          <FolderKanban className="w-3 h-3 text-[#C9A84C]" /> {expedienteActivo.titulo}
        </span>
        <span className="flex items-center gap-1.5">
          {cargandoLista ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3 cursor-pointer hover:text-[#C9A84C]" onClick={() => void cargarPresupuestos().catch(() => undefined)} />}
          {presupuestosGuardados.length} presupuesto(s) guardado(s) en este expediente
        </span>
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap gap-2 items-center justify-between p-3 bg-[#0A0A0F] border-b border-[#2A2A3E]">
        <div className="flex flex-wrap items-center gap-2">
          <button onClick={() => setShowAddForm(!showAddForm)} className="flex items-center gap-1.5 px-3 py-1.5 bg-[#C9A84C] text-[#030305] text-xs font-semibold rounded hover:bg-[#D4B85A] transition-colors">
            <Plus className="w-3.5 h-3.5" /> Concepto
          </button>
          <button onClick={() => setShowCatalog(!showCatalog)} className="px-3 py-1.5 border border-[#C9A84C] text-[#C9A84C] text-xs rounded">Catálogo del libro</button>
          <button onClick={() => setShowImportedCatalog(!showImportedCatalog)} className="px-3 py-1.5 border border-[#C9A84C] text-[#C9A84C] text-xs rounded">Catálogos CMIC / fuentes</button>
          <button onClick={() => setShowIndices(!showIndices)} className="px-3 py-1.5 border border-[#C9A84C] text-[#C9A84C] text-xs rounded">Actualizar material</button>
          <button onClick={exportJSON} className="flex items-center gap-1.5 px-3 py-1.5 border border-[#2A2A3E] text-[#8A8578] text-xs rounded hover:border-[#C9A84C] hover:text-[#C9A84C] transition-colors">
            <FileJson className="w-3.5 h-3.5" /> Exportar JSON
          </button>
          <button
            onClick={guardarEnBackend}
            disabled={guardando || lines.length === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#5A9E6F] text-[#030305] text-xs font-semibold rounded hover:bg-[#6AAF7F] transition-colors disabled:opacity-50"
          >
            {guardando ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
            Guardar en backend
          </button>
        </div>
        <div className="flex items-center gap-2">
          <Search className="w-3.5 h-3.5 text-[#8A8578]" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar concepto..."
            className="bg-[#12121A] border border-[#2A2A3E] rounded px-2 py-1 text-xs text-[#E8E4DC] placeholder:text-[#4D4A42] focus:border-[#C9A84C] outline-hidden w-48"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-6 gap-2 px-3 py-2 bg-[#12121A] border-b border-[#2A2A3E] text-[10px]">
        {[
          ['Indirectos %', factorIndirecto, setFactorIndirecto],
          ['Financiamiento %', factorFinanciamiento, setFactorFinanciamiento],
          ['Utilidad %', factorUtilidad, setFactorUtilidad],
          ['Cargos adicionales %', factorCargosAdicionales, setFactorCargosAdicionales],
          ['Impuesto %', factorImpuesto, setFactorImpuesto],
        ].map(([label, value, setter]) => (
          <label key={String(label)} className="text-[#8A8578]">{String(label)}
            <input type="number" min={0} max={100} step={0.01} value={Number(value) * 100}
              onChange={(e) => (setter as (n: number) => void)(Number(e.target.value) / 100)}
              className="mt-1 w-full bg-[#0A0A0F] border border-[#2A2A3E] rounded px-2 py-1 text-[#E8E4DC]" />
          </label>
        ))}
        <label className="text-[#8A8578]">Fuente / referencia
          <input value={referenciaParametros} onChange={(e) => setReferenciaParametros(e.target.value)}
            placeholder="Contrato, convocatoria, análisis..."
            className="mt-1 w-full bg-[#0A0A0F] border border-[#2A2A3E] rounded px-2 py-1 text-[#E8E4DC]" />
        </label>
      </div>

      {mensaje && (
        <div className={`px-3 py-1.5 text-[11px] ${mensaje.tipo === 'ok' ? 'bg-[#5A9E6F]/10 text-[#5A9E6F]' : 'bg-[#B84A4A]/10 text-[#B84A4A]'}`}>
          {mensaje.texto}
        </div>
      )}

      {showImportedCatalog && <div className="border-b border-[#2A2A3E]">
        <ImportacionesCatalogosPanel onImported={() => setCatalogRevision(value => value + 1)} />
        <CatalogoImportadoPicker key={catalogRevision} onSelect={(item, quantity) => {
          setLines(previous => [...previous, {id: crypto.randomUUID(), catalogoApuId: item.id,
            sourceLabel: `${item.origen?.fuente.titulo} · ${item.vigencia_inicio} · páginas ${item.origen?.paginas.join(', ')}`,
            conceptKey: item.clave, description: item.descripcion, unit: item.unidad, quantity,
            unitPrice: item.precio_unitario, amount: Math.round(quantity * item.precio_unitario * 100) / 100, status: 'pending'}]);
        }} />
      </div>}

      {showCatalog && <CatalogoLibroPicker onSelect={(item, quantity) => {
        const unitPrice = Number(item.precio_unitario);
        setLines(previous => [...previous, {
          id: crypto.randomUUID(), catalogoLibroId: item.id,
          sourceLabel: `CSV · modelo ${item.modelo_id} · página ${item.pagina}`,
          conceptKey: `LIBRO-${item.modelo_id}-${item.fila_csv}`,
          description: item.descripcion, unit: item.unidad, quantity, unitPrice,
          amount: Math.round((quantity * unitPrice + Number.EPSILON) * 100) / 100,
          status: 'pending',
        }]);
      }} />}

      {showIndices && <MaterialIndexadoPicker onSelect={(snapshot, solicitud, quantity) => {
        const original = snapshot.vinculo.insumo_original;
        const unitPrice = Number(snapshot.precio_actualizado);
        setLines(previous => [...previous, { id: crypto.randomUUID(), actualizacionPrecio: solicitud,
          conceptKey: original.clave, description: original.descripcion, unit: original.unidad,
          quantity, unitPrice, amount: Math.round(quantity * unitPrice * 100) / 100, status: 'pending',
          sourceLabel: `Estimación ${snapshot.base.mes.slice(0, 7)} → ${snapshot.destino.mes.slice(0, 7)} · ${snapshot.serie.codigo}` }]);
      }} />}

      {/* Add form */}
      {showAddForm && (
        <div className="p-3 bg-[#1A1A26] border-b border-[#2A2A3E] grid grid-cols-6 gap-2">
          <input placeholder="Clave" value={newLine.conceptKey} onChange={(e) => setNewLine({ ...newLine, conceptKey: e.target.value })} className="bg-[#12121A] border border-[#2A2A3E] rounded px-2 py-1 text-xs text-[#E8E4DC] focus:border-[#C9A84C] outline-hidden" />
          <input placeholder="Descripción" value={newLine.description} onChange={(e) => setNewLine({ ...newLine, description: e.target.value })} className="bg-[#12121A] border border-[#2A2A3E] rounded px-2 py-1 text-xs text-[#E8E4DC] focus:border-[#C9A84C] outline-hidden col-span-2" />
          <input placeholder="Unidad" value={newLine.unit} onChange={(e) => setNewLine({ ...newLine, unit: e.target.value })} className="bg-[#12121A] border border-[#2A2A3E] rounded px-2 py-1 text-xs text-[#E8E4DC] focus:border-[#C9A84C] outline-hidden" />
          <input type="number" placeholder="Cantidad" value={newLine.quantity || ''} onChange={(e) => setNewLine({ ...newLine, quantity: parseFloat(e.target.value) || 0 })} className="bg-[#12121A] border border-[#2A2A3E] rounded px-2 py-1 text-xs text-[#E8E4DC] focus:border-[#C9A84C] outline-hidden" />
          <div className="flex items-center gap-1">
            <input type="number" placeholder="Precio unitario" value={newLine.unitPrice || ''} onChange={(e) => setNewLine({ ...newLine, unitPrice: parseFloat(e.target.value) || 0 })} className="bg-[#12121A] border border-[#2A2A3E] rounded px-2 py-1 text-xs text-[#E8E4DC] focus:border-[#C9A84C] outline-hidden flex-1" />
            <button onClick={addLine} className="px-2 py-1 bg-[#5A9E6F] text-[#030305] text-xs font-semibold rounded hover:bg-[#6AAF7F]"><Plus className="w-3 h-3" /></button>
          </div>
        </div>
      )}

      {/* Grid */}
      <div className="flex-1 overflow-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-[#1A1A26] z-10">
            <tr className="text-left text-[#8A8578] border-b border-[#2A2A3E]">
              <th className="p-2 w-10">#</th>
              <th className="p-2 w-24">Clave</th>
              <th className="p-2">Descripción</th>
              <th className="p-2 w-14">Unidad</th>
              <th className="p-2 w-20 text-right">Cantidad</th>
              <th className="p-2 w-24 text-right">P. Unitario</th>
              <th className="p-2 w-24 text-right">Importe</th>
              <th className="p-2 w-16">Estado</th>
              <th className="p-2 w-8"></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((line, i) => (
              <tr key={line.id} className="border-b border-[#2A2A3E]/50 hover:bg-[#222235]/50 transition-colors">
                <td className="p-2 text-[#4D4A42]">{i + 1}</td>
                <td className="p-2 font-mono text-[#C9A84C]">{line.conceptKey}</td>
                <td className="p-2 text-[#E8E4DC]">{line.description}{line.sourceLabel && <div className="text-[10px] text-[#8A8578]">{line.sourceLabel}</div>}</td>
                <td className="p-2 text-[#8A8578]">{line.unit}</td>
                <td className="p-2 text-right font-mono text-[#E8E4DC]">{line.quantity.toLocaleString('es-MX', { maximumFractionDigits: 4 })}</td>
                <td className="p-2 text-right font-mono text-[#8A8578]">{formatMXN(line.unitPrice)}</td>
                <td className="p-2 text-right font-mono text-[#C9A84C] font-medium">{formatMXN(line.amount)}</td>
                <td className="p-2">
                  <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-medium ${
                    line.status === 'validated' ? 'bg-[#5A9E6F]/15 text-[#5A9E6F]' :
                    line.status === 'pending' ? 'bg-[#D4953A]/15 text-[#D4953A]' :
                    'bg-[#B84A4A]/15 text-[#B84A4A]'
                  }`}>
                    {line.status === 'validated' ? 'Validado' : line.status === 'pending' ? 'Pendiente' : 'Error'}
                  </span>
                </td>
                <td className="p-2">
                  <button onClick={() => removeLine(line.id)} className="text-[#4D4A42] hover:text-[#B84A4A] transition-colors"><Trash2 className="w-3 h-3" /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Footer totals -- misma composición económica que confirma el backend. */}
      <div className="p-3 bg-[#0A0A0F] border-t border-[#2A2A3E] flex flex-wrap justify-end gap-5 text-xs">
        <div className="text-right">
          <div className="text-[#8A8578]">Directo</div>
          <div className="font-mono text-[#E8E4DC]">{formatMXN(montoDirecto)}</div>
        </div>
        <div className="text-right">
          <div className="text-[#8A8578]">Indirecto {(factorIndirecto * 100).toFixed(2)}%</div>
          <div className="font-mono text-[#E8E4DC]">{formatMXN(montoIndirecto)}</div>
        </div>
        <div className="text-right">
          <div className="text-[#8A8578]">Financiamiento {(factorFinanciamiento * 100).toFixed(2)}%</div>
          <div className="font-mono text-[#E8E4DC]">{formatMXN(montoFinanciamiento)}</div>
        </div>
        <div className="text-right">
          <div className="text-[#8A8578]">Utilidad {(factorUtilidad * 100).toFixed(2)}%</div>
          <div className="font-mono text-[#E8E4DC]">{formatMXN(montoUtilidad)}</div>
        </div>
        <div className="text-right">
          <div className="text-[#8A8578]">Cargos adicionales {(factorCargosAdicionales * 100).toFixed(2)}%</div>
          <div className="font-mono text-[#E8E4DC]">{formatMXN(montoCargosAdicionales)}</div>
        </div>
        <div className="text-right">
          <div className="text-[#8A8578]">Impuesto {(factorImpuesto * 100).toFixed(2)}%</div>
          <div className="font-mono text-[#E8E4DC]">{formatMXN(montoImpuesto)}</div>
        </div>
        <div className="text-right">
          <div className="text-[#C9A84C]">Total estimado</div>
          <div className="font-mono text-[#C9A84C] text-base font-bold">{formatMXN(total)}</div>
        </div>
      </div>
    </div>
  );
}

// ---- Validation Panel ----
function ValidationPanel() {
  const expedienteActivo = useExpedienteStore((s) => s.expedienteActivo());
  const [results, setResults] = useState<ValidationRule[]>([]);
  const [ejecutando, setEjecutando] = useState(false);
  const [errorEjecucion, setErrorEjecucion] = useState('');
  const [inputs, setInputs] = useState<ValidationInput>({
    rfc: 'ABC010101ABC',
    opinionSAT: 'POSITIVO',
    imssStatus: 'ACTIVO',
    infonavitStatus: 'ACTIVO',
    efirmaValid: true,
    efirmaExpiryDays: 365,
    fsrSeguridadSocial: 0.3056,
    fsrDiasPagados: 365,
    fsrDiasLaborados: 291,
    maquinariaItems: [
      { key: 'EQ-001', description: 'Revolvedora 9ft³', costoAdquisicion: 45000, vidaEconomica: 8, horasAnio: 1200, factorMantenimiento: 0.45, combustibleHora: 25, operadorHora: 85.5, seguroAnual: 900 },
      { key: 'EQ-080', description: 'Retroexcavadora CAT 420E', costoAdquisicion: 2800000, vidaEconomica: 10, horasAnio: 2000, factorMantenimiento: 0.55, combustibleHora: 180, operadorHora: 135, seguroAnual: 56000 },
    ],
    factorIndirectos: 0.125,
    factorFinanciamiento: 0.025,
    utilidad: 0.082,
    costoDirectoPct: 0.684,
    numWorkers: 45,
    hasCFDI: true,
  });

  // BUG ORIGINAL: run() llamaba runValidacion(inputs) -- el motor local en
  // engines/validador.ts -- y nunca tocaba el backend. Ahora manda el
  // mismo formulario a POST /validadores/{expediente_id}/evaluar-completo
  // (los 10 validadores reales, con bitácora persistida) y traduce la
  // respuesta al mismo shape ValidationRule[] para no tocar el render de
  // abajo. engines/validador.ts ya no se usa como resultado oficial.
  //
  // Nota de mapeo: el primer maquinariaItems[] se traduce a un
  // costo_horario_total aproximado (no es lo mismo que un operador
  // capturando directamente el costo horario ya declarado en su
  // propuesta) -- el formulario de maquinaria todavía está pensado para
  // "calcular costo desde specs", mientras el validador real espera
  // "verificar cifras ya declaradas". Sirve como primera integración,
  // pero si se va a usar en serio conviene rediseñar ese bloque del
  // formulario para capturar directamente lo que el bidder declaró.
  const run = async () => {
    if (!expedienteActivo) return;
    setEjecutando(true);
    setErrorEjecucion('');
    try {
      const maq = inputs.maquinariaItems[0];
      const costoHorarioAprox = maq
        ? maq.combustibleHora + maq.operadorHora +
          (maq.seguroAnual + maq.costoAdquisicion * maq.factorMantenimiento) / Math.max(maq.horasAnio, 1)
        : 0;

      const payload: PropuestaLicitacionData = {
        rfc_empresa: inputs.rfc,
        fiscal: {
          opinion_sat_sentido: inputs.opinionSAT,
          opinion_imss_sentido: inputs.imssStatus,
          opinion_infonavit_sentido: inputs.infonavitStatus,
        },
        administrativo: { efirma_valida: inputs.efirmaValid },
        economico: {
          analisis_fsr: {
            tp_dias_pagados: inputs.fsrDiasPagados,
            tl_dias_laborados: inputs.fsrDiasLaborados,
            ps_fraccion_imss_infonavit: inputs.fsrSeguridadSocial,
          },
          analisis_maquinaria: maq ? {
            codigo_equipo: maq.key,
            cargo_combustible: maq.combustibleHora,
            cargo_operacion: maq.operadorHora,
            costo_horario_total: costoHorarioAprox,
            total_cargos_fijos: maq.seguroAnual,
            horas_uso_anual: maq.horasAnio,
          } : undefined,
          analisis_sobrecostos: {
            pct_indirecto_oficina: inputs.factorIndirectos,
            pct_utilidad: inputs.utilidad,
            pct_financiamiento: inputs.factorFinanciamiento,
            factor_sobrecosto_total_declarado: 1 + inputs.factorIndirectos + inputs.utilidad + inputs.factorFinanciamiento,
          },
        },
      };

      const resultado = await megalodonClient.validadores.evaluarCompleto(expedienteActivo.id, payload);

      const estatusMap: Record<string, ValidationStatus> = { PASA: 'PASS', FALLA: 'FAIL', NO_APLICA: 'WARNING' };
      setResults(resultado.bitacora_evaluacion.map((r) => ({
        id: r.id_regla,
        name: r.seccion,
        category: r.seccion,
        status: estatusMap[r.estatus] ?? 'WARNING',
        detail: `Detectado: ${r.valor_detectado} — Esperado: ${r.valor_esperado}`,
        evidence: r.evidencia,
      })));
    } catch (e) {
      setErrorEjecucion(e instanceof Error ? e.message : 'No se pudo ejecutar la validación en el backend');
    } finally {
      setEjecutando(false);
    }
  };

  const score = useMemo(() => computeComplianceScore(results), [results]);
  const overall = useMemo(() => getOverallStatus(results), [results]);

  const update = (field: keyof ValidationInput, value: unknown) => {
    setInputs((prev) => ({ ...prev, [field]: value }));
  };

  if (!expedienteActivo) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-2 text-center px-6 h-full text-[#8A8578]">
        <FolderKanban className="w-8 h-8 opacity-50" />
        <p className="text-sm">No hay ningún expediente activo.</p>
        <p className="text-xs">Abre la app &quot;Proyectos&quot; y selecciona o crea un expediente para validar una propuesta contra él.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-auto p-4 gap-4">
      <div className="bg-[#16241A] border border-[#5A9E6F]/40 rounded-lg px-3 py-2 text-xs text-[#5A9E6F] flex items-center gap-2">
        <span className="font-bold">CONECTADO</span>
        <span className="text-[#8A8578]">— corre los 10 validadores reales del backend contra {expedienteActivo.titulo} y persiste la bitácora. El análisis de maquinaria abajo sigue siendo una aproximación (ver nota en el código).</span>
      </div>
      {errorEjecucion && (
        <div className="bg-[#2A1616] border border-[#B84A4A]/40 rounded-lg px-3 py-2 text-xs text-[#B84A4A]">{errorEjecucion}</div>
      )}
      {/* Input form */}
      <div className="grid grid-cols-4 gap-3">
        <div>
          <label className="text-[10px] uppercase text-[#8A8578] block mb-1">RFC</label>
          <input value={inputs.rfc} onChange={(e) => update('rfc', e.target.value)} className="w-full bg-[#12121A] border border-[#2A2A3E] rounded px-2 py-1 text-xs text-[#E8E4DC] focus:border-[#C9A84C] outline-hidden font-mono" />
        </div>
        <div>
          <label className="text-[10px] uppercase text-[#8A8578] block mb-1">Opinión SAT</label>
          <select value={inputs.opinionSAT} onChange={(e) => update('opinionSAT', e.target.value)} className="w-full bg-[#12121A] border border-[#2A2A3E] rounded px-2 py-1 text-xs text-[#E8E4DC] focus:border-[#C9A84C] outline-hidden">
            <option>POSITIVO</option>
            <option>EXTRAVIADA</option>
            <option>NEGATIVO</option>
            <option>DEFINITIVA</option>
          </select>
        </div>
        <div>
          <label className="text-[10px] uppercase text-[#8A8578] block mb-1">IMSS</label>
          <select value={inputs.imssStatus} onChange={(e) => update('imssStatus', e.target.value)} className="w-full bg-[#12121A] border border-[#2A2A3E] rounded px-2 py-1 text-xs text-[#E8E4DC] focus:border-[#C9A84C] outline-hidden">
            <option>ACTIVO</option>
            <option>INACTIVO</option>
          </select>
        </div>
        <div>
          <label className="text-[10px] uppercase text-[#8A8578] block mb-1">INFONAVIT</label>
          <select value={inputs.infonavitStatus} onChange={(e) => update('infonavitStatus', e.target.value)} className="w-full bg-[#12121A] border border-[#2A2A3E] rounded px-2 py-1 text-xs text-[#E8E4DC] focus:border-[#C9A84C] outline-hidden">
            <option>ACTIVO</option>
            <option>INACTIVO</option>
          </select>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-3">
        <div>
          <label className="text-[10px] uppercase text-[#8A8578] block mb-1">e.firma válida</label>
          <select value={inputs.efirmaValid ? 'si' : 'no'} onChange={(e) => update('efirmaValid', e.target.value === 'si')} className="w-full bg-[#12121A] border border-[#2A2A3E] rounded px-2 py-1 text-xs text-[#E8E4DC] focus:border-[#C9A84C] outline-hidden">
            <option value="si">Sí</option>
            <option value="no">No</option>
          </select>
        </div>
        <div>
          <label className="text-[10px] uppercase text-[#8A8578] block mb-1">Días vigencia e.firma</label>
          <input type="number" value={inputs.efirmaExpiryDays} onChange={(e) => update('efirmaExpiryDays', parseInt(e.target.value) || 0)} className="w-full bg-[#12121A] border border-[#2A2A3E] rounded px-2 py-1 text-xs text-[#E8E4DC] focus:border-[#C9A84C] outline-hidden font-mono" />
        </div>
        <div>
          <label className="text-[10px] uppercase text-[#8A8578] block mb-1">Fracción SS (PS)</label>
          <input type="number" step="0.001" value={inputs.fsrSeguridadSocial} onChange={(e) => update('fsrSeguridadSocial', parseFloat(e.target.value) || 0)} className="w-full bg-[#12121A] border border-[#2A2A3E] rounded px-2 py-1 text-xs text-[#E8E4DC] focus:border-[#C9A84C] outline-hidden font-mono" />
        </div>
        <div>
          <label className="text-[10px] uppercase text-[#8A8578] block mb-1">Factor indirectos</label>
          <input type="number" step="0.001" value={inputs.factorIndirectos} onChange={(e) => update('factorIndirectos', parseFloat(e.target.value) || 0)} className="w-full bg-[#12121A] border border-[#2A2A3E] rounded px-2 py-1 text-xs text-[#E8E4DC] focus:border-[#C9A84C] outline-hidden font-mono" />
        </div>
      </div>

      <div className="grid grid-cols-4 gap-3">
        <div>
          <label className="text-[10px] uppercase text-[#8A8578] block mb-1">Días pagados (TP)</label>
          <input type="number" value={inputs.fsrDiasPagados} onChange={(e) => update('fsrDiasPagados', parseInt(e.target.value) || 0)} className="w-full bg-[#12121A] border border-[#2A2A3E] rounded px-2 py-1 text-xs text-[#E8E4DC] focus:border-[#C9A84C] outline-hidden font-mono" />
        </div>
        <div>
          <label className="text-[10px] uppercase text-[#8A8578] block mb-1">Días laborados (TL)</label>
          <input type="number" value={inputs.fsrDiasLaborados} onChange={(e) => update('fsrDiasLaborados', parseInt(e.target.value) || 0)} className="w-full bg-[#12121A] border border-[#2A2A3E] rounded px-2 py-1 text-xs text-[#E8E4DC] focus:border-[#C9A84C] outline-hidden font-mono" />
        </div>
        <div>
          <label className="text-[10px] uppercase text-[#8A8578] block mb-1">Utilidad</label>
          <input type="number" step="0.001" value={inputs.utilidad} onChange={(e) => update('utilidad', parseFloat(e.target.value) || 0)} className="w-full bg-[#12121A] border border-[#2A2A3E] rounded px-2 py-1 text-xs text-[#E8E4DC] focus:border-[#C9A84C] outline-hidden font-mono" />
        </div>
        <div>
          <label className="text-[10px] uppercase text-[#8A8578] block mb-1">% Costo directo</label>
          <input type="number" step="0.001" value={inputs.costoDirectoPct} onChange={(e) => update('costoDirectoPct', parseFloat(e.target.value) || 0)} className="w-full bg-[#12121A] border border-[#2A2A3E] rounded px-2 py-1 text-xs text-[#E8E4DC] focus:border-[#C9A84C] outline-hidden font-mono" />
        </div>
      </div>

      <button onClick={run} disabled={ejecutando} className="flex items-center justify-center gap-2 px-4 py-2 bg-[#C9A84C] text-[#030305] text-sm font-semibold rounded hover:bg-[#D4B85A] transition-colors self-start disabled:opacity-50">
        <ShieldCheck className="w-4 h-4" /> {ejecutando ? 'Validando en el backend...' : 'Ejecutar Validación'}
      </button>

      {/* Results */}
      {results.length > 0 && (
        <>
          {/* Score banner */}
          <div className={`p-3 rounded-lg border ${
            overall === 'PASS' ? 'bg-[#5A9E6F]/10 border-[#5A9E6F]/30' :
            overall === 'WARNING' ? 'bg-[#D4953A]/10 border-[#D4953A]/30' :
            'bg-[#B84A4A]/10 border-[#B84A4A]/30'
          }`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {overall === 'PASS' ? <CheckCircle className="w-5 h-5 text-[#5A9E6F]" /> :
                 overall === 'WARNING' ? <AlertTriangle className="w-5 h-5 text-[#D4953A]" /> :
                 <X className="w-5 h-5 text-[#B84A4A]" />}
                <span className={`font-semibold ${
                  overall === 'PASS' ? 'text-[#5A9E6F]' : overall === 'WARNING' ? 'text-[#D4953A]' : 'text-[#B84A4A]'
                }`}>
                  {overall === 'PASS' ? 'Todas las validaciones aprobadas' : overall === 'WARNING' ? 'Advertencias detectadas' : 'Validaciones fallidas'}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[#8A8578] text-xs">Cumplimiento:</span>
                <span className={`text-lg font-bold font-mono ${
                  score >= 80 ? 'text-[#5A9E6F]' : score >= 50 ? 'text-[#D4953A]' : 'text-[#B84A4A]'
                }`}>{score}%</span>
              </div>
            </div>
          </div>

          {/* Rule results */}
          <div className="space-y-2">
            {results.map((rule) => (
              <div key={rule.id} className="bg-[#1A1A26] border border-[#2A2A3E] rounded-md p-3">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5">
                    {rule.status === 'PASS' ? <CheckCircle className="w-4 h-4 text-[#5A9E6F]" /> :
                     rule.status === 'WARNING' ? <AlertTriangle className="w-4 h-4 text-[#D4953A]" /> :
                     <X className="w-4 h-4 text-[#B84A4A]" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-mono text-[#4D4A42] px-1 py-0.5 bg-[#0A0A0F] rounded">{rule.id}</span>
                      <span className="text-xs font-semibold text-[#E8E4DC]">{rule.name}</span>
                    </div>
                    <div className="text-[11px] text-[#8A8578] mt-1">{rule.detail}</div>
                    <div className="text-[10px] text-[#4D4A42] mt-1 font-mono">{rule.evidence}</div>
                    {rule.fixAction && (
                      <div className="text-[11px] text-[#D4953A] mt-1">Acción: {rule.fixAction}</div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// ---- Analysis Panel ----
function AnalysisPanel() {
  const [iterations, setIterations] = useState(1000);
  const [confidence, setConfidence] = useState(95);
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [oficialEstado, setOficialEstado] = useState<'idle' | 'enviando' | 'procesando' | 'listo' | 'error'>('idle');
  const [oficialError, setOficialError] = useState('');

  const runOficial = async () => {
    setOficialEstado('enviando');
    setOficialError('');
    setResult(null);
    try {
      const vars = getDefaultSimulationVariables();
      const presupuestoBase = vars.reduce((s, v) => s + v.mean, 0);
      const task = await megalodonClient.riesgo.simular({
        presupuesto_base: presupuestoBase,
        presupuesto_maximo: presupuestoBase * 1.15,
        iteraciones: iterations,
        confidence_level: confidence / 100,
        variables: vars.map((v) => ({
          nombre: v.name,
          distribucion: 'normal' as const,
          parametros: { media: 0, desviacion: v.mean > 0 ? v.stdDev / v.mean : 0 },
          impacto: 'costo_pct' as const,
        })),
      });
      setOficialEstado('procesando');

      const poll = async (): Promise<void> => {
        const status = await megalodonClient.riesgo.consultar(task.task_id);
        if (status.status === 'COMPLETADO') {
          const r = status.result as any;
          const normalized: SimulationResult = {
            mean: r.media,
            median: r.mediana,
            stdDev: r.desviacion,
            p1: r.p1,
            p5: r.percentil_5,
            p10: r.percentil_10,
            p25: r.percentil_25,
            p50: r.mediana,
            p75: r.percentil_75,
            p90: r.percentil_90,
            p95: r.percentil_95,
            p99: r.percentil_99,
            cv: r.cv,
            confidenceLevel: r.nivel_confianza,
            confidenceInterval: (r.intervalo_confianza_media || r.ic_95) as [number, number],
            probabilityBudgetExceedance: r.prob_exceder_presupuesto,
            schedule: r.plazo?.estado === 'SIMULADO' ? {
              p50: r.plazo.p50,
              p80: r.plazo.p80,
              p90: r.plazo.p90,
              p95: r.plazo.p95,
              probabilityExceedance: r.prob_exceder_plazo,
            } : undefined,
            histogram: (r.histograma || []).map((b: any) => ({
              min: b.min ?? b.bin_start,
              max: b.max ?? b.bin_end,
              count: b.count ?? b.frecuencia,
              frequency: b.frequency ?? b.probabilidad,
            })),
            sensitivity: (r.sensibilidad_presupuesto || []).map((item: any) => ({
              variable: item.variable,
              impact: item.impact ?? item.impacto ?? 0,
              lowValue: 0,
              highValue: 0,
            })),
          };
          setResult(normalized);
          setOficialEstado('listo');
          return;
        }
        if (status.status === 'ERROR') {
          setOficialError(status.error?.mensaje || 'La simulación falló en el backend.');
          setOficialEstado('error');
          return;
        }
        window.setTimeout(() => void poll(), 1500);
      };
      await poll();
    } catch (e) {
      setOficialError(e instanceof Error ? e.message : 'No se pudo ejecutar la simulación.');
      setOficialEstado('error');
    }
  };

  const fsrPS = FSR_CONST.FORMULA.FRACCION_SEGURIDAD_SOCIAL_DEFAULT;
  const fsrTP = FSR_CONST.FORMULA.DIAS_PAGADOS;
  const fsrTL = FSR_CONST.FORMULA.DIAS_LABORADOS;
  const fsrValue = fsrPS * (fsrTP / fsrTL) + (fsrTP / fsrTL);

  return (
    <div className="flex flex-col h-full overflow-auto p-4 gap-4">
      <div className="bg-[#1A1A26] border border-[#2A2A3E] rounded-lg p-4">
        <div className="flex items-center gap-2 mb-3">
          <Calculator className="w-4 h-4 text-[#C9A84C]" />
          <h3 className="text-sm font-semibold text-[#E8E4DC]">Calculadora FSR (LAASSP Art. 12)</h3>
        </div>
        <div className="text-[11px] text-[#8A8578] mb-3">
          Fórmula: FSR = PS × (TP/TL) + (TP/TL)
        </div>
        <div className="grid grid-cols-4 gap-4 text-xs">
          <div className="bg-[#0A0A0F] rounded p-2"><div className="text-[10px] text-[#8A8578]">PS (Fracción SS)</div><div className="font-mono text-[#C9A84C] font-semibold">{fsrPS.toFixed(4)}</div></div>
          <div className="bg-[#0A0A0F] rounded p-2"><div className="text-[10px] text-[#8A8578]">TP (Días pagados)</div><div className="font-mono text-[#C9A84C] font-semibold">{fsrTP}</div></div>
          <div className="bg-[#0A0A0F] rounded p-2"><div className="text-[10px] text-[#8A8578]">TL (Días laborados)</div><div className="font-mono text-[#C9A84C] font-semibold">{fsrTL}</div></div>
          <div className="bg-[#0A0A0F] rounded p-2 border border-[#C9A84C]/30"><div className="text-[10px] text-[#C9A84C]">FSR</div><div className="font-mono text-[#C9A84C] font-bold text-lg">{fsrValue.toFixed(4)}</div></div>
        </div>
      </div>

      <div className="bg-[#1A1A26] border border-[#2A2A3E] rounded-lg p-4">
        <div className="flex items-center gap-2 mb-3"><Activity className="w-4 h-4 text-[#C9A84C]" /><h3 className="text-sm font-semibold text-[#E8E4DC]">Simulación Monte Carlo oficial</h3></div>
        <div className="flex items-end gap-4">
          <div><label className="text-[10px] uppercase text-[#8A8578] block mb-1">Iteraciones</label><input type="number" min={100} max={1000000} value={iterations} onChange={(e) => setIterations(parseInt(e.target.value) || 1000)} className="w-28 bg-[#12121A] border border-[#2A2A3E] rounded px-2 py-1 text-xs text-[#E8E4DC] font-mono" /></div>
          <div><label className="text-[10px] uppercase text-[#8A8578] block mb-1">Confianza {confidence}%</label><input type="range" min={80} max={99} value={confidence} onChange={(e) => setConfidence(parseInt(e.target.value))} className="w-32 accent-[#C9A84C]" /></div>
          <button onClick={() => void runOficial()} disabled={oficialEstado === 'enviando' || oficialEstado === 'procesando'} className="flex items-center gap-1.5 px-4 py-1.5 border border-[#5A9E6F] text-[#5A9E6F] text-xs font-semibold rounded hover:bg-[#5A9E6F]/10 transition-colors disabled:opacity-50">
            {oficialEstado === 'enviando' || oficialEstado === 'procesando' ? 'Procesando en backend...' : 'Ejecutar simulación oficial'}
          </button>
        </div>
      </div>

      {oficialError && <div className="bg-[#B84A4A]/10 border border-[#B84A4A]/30 rounded-lg p-3 text-xs text-[#B84A4A]">{oficialError}</div>}

      {result && (
        <>
          <div className="bg-[#1A1A26] border border-[#5A9E6F]/40 rounded-lg p-4">
            <h3 className="text-sm font-semibold text-[#5A9E6F] mb-3">Resultado oficial persistido en backend</h3>
            <div className="grid grid-cols-4 gap-2 text-xs">
              {[
                { label: 'Media', value: formatMXN(result.mean) },
                { label: 'P50', value: formatMXN(result.p50) },
                { label: 'Desv. estándar', value: formatMXN(result.stdDev) },
                { label: 'P5 / P95', value: `${formatMXN(result.p5)} / ${formatMXN(result.p95)}` },
                { label: `IC ${(result.confidenceLevel ?? confidence / 100) * 100}%`, value: result.confidenceInterval ? `${formatMXN(result.confidenceInterval[0])} - ${formatMXN(result.confidenceInterval[1])}` : 'No disponible' },
                { label: 'CV', value: `${result.cv.toFixed(2)}%` },
              ].map((s) => <div key={s.label} className="bg-[#0A0A0F] rounded p-2"><div className="text-[10px] text-[#8A8578]">{s.label}</div><div className="font-mono text-[#5A9E6F] font-semibold">{s.value}</div></div>)}
            </div>
          </div>
          <div className="bg-[#1A1A26] border border-[#2A2A3E] rounded-lg p-4"><h3 className="text-sm font-semibold text-[#E8E4DC] mb-3">Distribución de costos</h3><HistogramChart result={result} /></div>
          <div className="bg-[#1A1A26] border border-[#2A2A3E] rounded-lg p-4"><h3 className="text-sm font-semibold text-[#E8E4DC] mb-3">Estadísticas</h3><div className="grid grid-cols-4 gap-2 text-xs">
            {[
              { label: 'Media', value: formatMXN(result.mean) },
              { label: 'P50', value: formatMXN(result.p50) },
              { label: 'P5', value: formatMXN(result.p5) },
              { label: 'P95', value: formatMXN(result.p95) },
              { label: 'P25', value: formatMXN(result.p25) },
              { label: 'P75', value: formatMXN(result.p75) },
              { label: 'P99', value: formatMXN(result.p99) },
              { label: 'CV', value: `${result.cv.toFixed(2)}%` },
            ].map((s) => <div key={s.label} className="bg-[#0A0A0F] rounded p-2"><div className="text-[10px] text-[#8A8578]">{s.label}</div><div className="font-mono text-[#C9A84C] font-semibold">{s.value}</div></div>)}
          </div></div>
          {result.sensitivity.length > 0 && <div className="bg-[#1A1A26] border border-[#2A2A3E] rounded-lg p-4"><h3 className="text-sm font-semibold text-[#E8E4DC] mb-3">Análisis de Sensibilidad (Tornado)</h3><TornadoChart sensitivity={result.sensitivity} /></div>}
        </>
      )}
    </div>
  );
}

// ---- Report Panel ----
function ReportPanel() {
  const expedienteActivo = useExpedienteStore((s) => s.expedienteActivo());
  const [presupuesto, setPresupuesto] = useState<Presupuesto | null>(null);
  const [elementosPorNivel, setElementosPorNivel] = useState<Record<string, number>>({});
  const [totalElementosBim, setTotalElementosBim] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [errorCarga, setErrorCarga] = useState('');

  // Este panel consume exclusivamente el presupuesto persistido y los
  // elementos BIM del expediente activo. Si todavía no existen, muestra
  // el estado real sin inventar cifras.
  useEffect(() => {
    if (!expedienteActivo) {
      setCargando(false);
      return;
    }
    let cancelado = false;
    setCargando(true);
    setErrorCarga('');
    (async () => {
      try {
        const [presupuestos, modelos] = await Promise.all([
          megalodonClient.presupuestos.list(expedienteActivo.id),
          megalodonClient.bim.listarModelos(expedienteActivo.id),
        ]);
        if (cancelado) return;
        setPresupuesto(presupuestos[0] ?? null);

        if (modelos[0]) {
          const elementos = await megalodonClient.bim.listarElementos(expedienteActivo.id, modelos[0].id);
          if (cancelado) return;
          const porNivel: Record<string, number> = {};
          for (const el of elementos) {
            const nivel = el.nivel || 'Sin nivel asignado';
            porNivel[nivel] = (porNivel[nivel] || 0) + 1;
          }
          setElementosPorNivel(porNivel);
          setTotalElementosBim(elementos.length);
        }
      } catch (e) {
        if (!cancelado) setErrorCarga(e instanceof Error ? e.message : 'No se pudo cargar el reporte');
      } finally {
        if (!cancelado) setCargando(false);
      }
    })();
    return () => { cancelado = true; };
  }, [expedienteActivo?.id]);

  const total = presupuesto?.monto_total ?? 0;
  const subtotal = total - (presupuesto?.monto_impuesto ?? 0);

  // Recomendaciones de redacción de reporte (heurística local, no una
  // determinación legal -- eso lo decide el backend más abajo). Ahora usa
  // los factores REALES del presupuesto en vez de 0.684/0.082/0.125 fijos.
  const legal = useMemo(() => (
    presupuesto
      ? evaluateLegalFramework(
          total, true, true, true,
          presupuesto.factor_indirecto, presupuesto.factor_utilidad,
          presupuesto.factor_financiamiento ?? 0,
        )
      : null
  ), [presupuesto, total]);

  const [procedimiento, setProcedimiento] = useState<{ procedimiento: string; [k: string]: any } | null>(null);
  const [procedimientoError, setProcedimientoError] = useState('');

  useEffect(() => {
    if (!total) return;
    // Sin presupuesto_dependencia_miles (el Anexo 9 federal es una tabla
    // escalonada por el presupuesto autorizado de la dependencia, dato
    // que no vive en este expediente): el backend responde SIN_DETERMINAR
    // en vez de que finjamos un monto de dependencia que no conocemos.
    megalodonClient.juridico.determinarProcedimiento({
      monto: total, es_obra_publica: true,
    })
      .then(setProcedimiento)
      .catch((e) => setProcedimientoError(e instanceof Error ? e.message : 'No se pudo determinar el procedimiento'));
  }, [total]);

  const exportReport = () => {
    const lines = [
      '='.repeat(70),
      'MEGALODON COSTOS — REPORTE DE ANÁLISIS',
      '='.repeat(70),
      `Fecha: ${new Date().toLocaleString('es-MX')}`,
      `Proyecto: ${expedienteActivo?.titulo ?? 'N/A'}`,
      `Procedimiento: ${procedimiento?.procedimiento || 'consultando backend...'}`,
      '-'.repeat(70),
      '',
      'RESUMEN PRESUPUESTAL',
      '-'.repeat(40),
      presupuesto
        ? [
            `Costo directo:      ${formatMXN(presupuesto.monto_directo)}`,
            `Indirectos:         ${formatMXN(presupuesto.monto_indirecto)}`,
            `Utilidad:           ${formatMXN(presupuesto.monto_utilidad)}`,
            `Impuestos:          ${formatMXN(presupuesto.monto_impuesto)}`,
            `TOTAL:              ${formatMXN(presupuesto.monto_total)}`,
          ].join('\n')
        : '(sin presupuesto calculado todavía para este expediente)',
      '',
      'ELEMENTOS BIM POR NIVEL',
      '-'.repeat(40),
      totalElementosBim > 0
        ? [
            ...Object.entries(elementosPorNivel).map(([nivel, n]) => `  ${nivel.padEnd(28)} ${String(n).padStart(6)} elementos`),
            `  ${'TOTAL'.padEnd(28)} ${String(totalElementosBim).padStart(6)} elementos`,
          ].join('\n')
        : '(sin modelo BIM cargado todavía para este expediente)',
      '',
      'CUMPLIMIENTO LEGAL (determinado por el backend)',
      '-'.repeat(40),
      ...(procedimiento?.requisitos || []).map((r: any) => `[${r.obligatorio ? 'OBLIGATORIO' : 'opcional'}] ${r.codigo}: ${r.descripcion}`),
      '',
      'RECOMENDACIONES',
      '-'.repeat(40),
      ...(legal?.recommendations || []).map((r) => `  • ${r}`),
      '',
      `Generado por Megalodon CostOS`,
      '='.repeat(70),
    ];

    const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `megalodon-reporte-${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!expedienteActivo) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-2 text-center px-6 h-full text-[#8A8578]">
        <FolderKanban className="w-8 h-8 opacity-50" />
        <p className="text-sm">No hay ningún expediente activo.</p>
        <p className="text-xs">Abre la app &quot;Proyectos&quot; y selecciona o crea un expediente para generar su reporte.</p>
      </div>
    );
  }

  if (cargando) {
    return <div className="flex-1 flex items-center justify-center text-xs text-[#8A8578] h-full">Cargando reporte de {expedienteActivo.titulo}...</div>;
  }

  return (
    <div className="flex flex-col h-full overflow-auto p-4 gap-4">
      {errorCarga && (
        <div className="bg-[#2A1616] border border-[#B84A4A]/40 rounded-lg px-3 py-2 text-xs text-[#B84A4A]">{errorCarga}</div>
      )}

      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-[#E8E4DC]">Reporte Ejecutivo</h2>
          <p className="text-[11px] text-[#8A8578] flex items-center gap-1"><FolderKanban className="w-3 h-3" /> {expedienteActivo.titulo}</p>
        </div>
        <button onClick={exportReport} className="flex items-center gap-1.5 px-3 py-1.5 bg-[#C9A84C] text-[#030305] text-xs font-semibold rounded hover:bg-[#D4B85A] transition-colors">
          <Download className="w-3.5 h-3.5" /> Exportar Reporte
        </button>
      </div>

      <div className="bg-[#1A1A26] border border-[#2A2A3E] rounded-lg p-4">
        <h3 className="text-sm font-semibold text-[#E8E4DC] mb-3">Resumen Presupuestal</h3>
        {presupuesto ? (
          <div className="grid grid-cols-3 gap-3 text-xs">
            <div className="bg-[#0A0A0F] rounded p-3">
              <div className="text-[10px] text-[#8A8578]">Subtotal</div>
              <div className="font-mono text-[#E8E4DC] text-base font-semibold">{formatMXN(subtotal)}</div>
            </div>
            <div className="bg-[#0A0A0F] rounded p-3">
              <div className="text-[10px] text-[#8A8578]">Impuestos</div>
              <div className="font-mono text-[#E8E4DC] text-base font-semibold">{formatMXN(presupuesto.monto_impuesto)}</div>
            </div>
            <div className="bg-[#0A0A0F] rounded p-3 border border-[#C9A84C]/30">
              <div className="text-[10px] text-[#C9A84C]">TOTAL</div>
              <div className="font-mono text-[#C9A84C] text-lg font-bold">{formatMXN(total)}</div>
            </div>
          </div>
        ) : (
          <p className="text-xs text-[#8A8578]">Este expediente todavía no tiene un presupuesto calculado — ábrelo en la pestaña &quot;Presupuestos&quot; primero.</p>
        )}
      </div>

      <div className="bg-[#1A1A26] border border-[#2A2A3E] rounded-lg p-4">
        <h3 className="text-sm font-semibold text-[#E8E4DC] mb-3">Elementos BIM por Nivel</h3>
        {totalElementosBim > 0 ? (
          <div className="space-y-1.5 text-xs">
            {Object.entries(elementosPorNivel).map(([nivel, n]) => (
              <div key={nivel} className="flex items-center justify-between">
                <span className="text-[#8A8578]">{nivel}</span>
                <span className="font-mono text-[#E8E4DC]">{n} elementos</span>
              </div>
            ))}
            <div className="border-t border-[#2A2A3E] pt-1 flex justify-between font-semibold">
              <span className="text-[#C9A84C]">Total elementos</span>
              <span className="font-mono text-[#C9A84C]">{totalElementosBim}</span>
            </div>
          </div>
        ) : (
          <p className="text-xs text-[#8A8578]">Este expediente todavía no tiene un modelo BIM cargado — súbelo en la app &quot;BIM&quot;.</p>
        )}
      </div>

      <div className="bg-[#1A1A26] border border-[#2A2A3E] rounded-lg p-4">
        <h3 className="text-sm font-semibold text-[#E8E4DC] mb-3">Marco Legal Aplicable</h3>

        {procedimientoError && (
          <div className="text-[11px] text-[#B84A4A] mb-2">{procedimientoError}</div>
        )}

        {!procedimiento && !procedimientoError && !total && (
          <div className="text-[11px] text-[#8A8578] mb-2">Calcula un presupuesto primero para determinar el procedimiento aplicable.</div>
        )}

        {!procedimiento && !procedimientoError && !!total && (
          <div className="text-[11px] text-[#8A8578] mb-2">Consultando procedimiento aplicable...</div>
        )}

        {procedimiento && (
          <>
            <div className="mb-3 text-xs">
              <span className="text-[#8A8578]">Procedimiento (determinado por el backend): </span>
              <span className="text-[#C9A84C] font-medium">{procedimiento.procedimiento}</span>
            </div>
            {procedimiento.es_candidato && (
              <div className="mb-3 px-2 py-1.5 rounded text-[11px] flex items-start gap-1.5"
                   style={{ background: 'rgba(212,149,58,0.12)', color: '#D4953A' }}>
                <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                <span>Umbral CANDIDATO sin confirmar contra el Anexo 9 oficial -- no usar como
                única base de una decisión de cumplimiento real.</span>
              </div>
            )}
            {procedimiento.procedimiento === 'SIN_DETERMINAR' && (
              <div className="mb-3 px-2 py-1.5 rounded text-[11px]"
                   style={{ background: 'rgba(184,74,74,0.12)', color: '#B84A4A' }}>
                Sin datos suficientes para determinar el procedimiento -- ver observaciones abajo.
              </div>
            )}
            <div className="space-y-2">
              {(procedimiento.requisitos || []).map((req: any) => (
                <div key={req.codigo} className="flex items-start gap-2 text-xs">
                  {req.obligatorio
                    ? <AlertTriangle className="w-3.5 h-3.5 text-[#D4953A] mt-0.5 shrink-0" />
                    : <CheckCircle className="w-3.5 h-3.5 text-[#5A9E6F] mt-0.5 shrink-0" />}
                  <div>
                    <span className="font-mono text-[#4D4A42] mr-1">{req.codigo}</span>
                    <span className="text-[#E8E4DC]">{req.descripcion}</span>
                    {req.obligatorio && <div className="text-[#D4953A] mt-0.5">Obligatorio</div>}
                  </div>
                </div>
              ))}
            </div>
            {(procedimiento.observaciones || []).length > 0 && (
              <div className="mt-3 pt-3 border-t border-[#2A2A3E]">
                <div className="text-[10px] uppercase text-[#8A8578] mb-1">Observaciones (backend)</div>
                {procedimiento.observaciones.map((r: string, i: number) => (
                  <div key={i} className="text-[11px] text-[#D4953A] flex items-start gap-1">
                    <span className="mt-0.5">•</span> {r}
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {/* Recomendaciones: esto sigue siendo local -- son sugerencias de
            redacción de reporte, no una determinación legal, así que no
            compite con lo que ya decide el backend arriba. Ahora usa los
            factores reales del presupuesto en vez de datos de ejemplo. */}
        {legal && legal.recommendations.length > 0 && (
          <div className="mt-3 pt-3 border-t border-[#2A2A3E]">
            <div className="text-[10px] uppercase text-[#8A8578] mb-1">Recomendaciones</div>
            {legal.recommendations.map((r, i) => (
              <div key={i} className="text-[11px] text-[#D4953A] flex items-start gap-1">
                <span className="mt-0.5">•</span> {r}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ---- Resumen (Dashboard) Tab ----
function ResumenTab() {
  const expedienteActivo = useExpedienteStore((s) => s.expedienteActivo());
  const [presupuesto, setPresupuesto] = useState<Presupuesto | null>(null);
  const [totalElementosBim, setTotalElementosBim] = useState<number | null>(null);
  const [procedimiento, setProcedimiento] = useState<{ procedimiento: string } | null>(null);
  const [ultimaValidacion, setUltimaValidacion] = useState<ValidacionResultado | null>(null);
  const [cargando, setCargando] = useState(true);

  // BUG ORIGINAL: este dashboard (la PRIMERA pestaña que ve el usuario)
  // corría enteramente sobre datos de ejemplo -- incluyendo un índice de
  // riesgo (12.4%) y "45 días para entrega" escritos a mano en el código,
  // sin relación con ningún expediente real. Ahora jala presupuesto,
  // BIM, procedimiento y última validación reales del expediente activo.
  // "Exposición de Riesgo" se deja honesto (sin inventar cifra) porque
  // hoy no existe un endpoint que liste corridas de Monte Carlo pasadas
  // por expediente_id (montecarlo.py solo hace submit + poll por
  // task_id) -- para mostrarlo de verdad aquí primero hay que persistir
  // esas corridas ligadas al expediente.
  useEffect(() => {
    if (!expedienteActivo) { setCargando(false); return; }
    let cancelado = false;
    setCargando(true);
    (async () => {
      try {
        const [presupuestos, validaciones] = await Promise.all([
          megalodonClient.presupuestos.list(expedienteActivo.id),
          megalodonClient.validadores.historial(expedienteActivo.id, 1).catch(() => []),
        ]);
        if (cancelado) return;
        const pres = presupuestos[0] ?? null;
        setPresupuesto(pres);
        setUltimaValidacion(validaciones[0] ?? null);

        const modelos = await megalodonClient.bim.listarModelos(expedienteActivo.id);
        if (cancelado) return;
        if (modelos[0]) {
          const elementos = await megalodonClient.bim.listarElementos(expedienteActivo.id, modelos[0].id);
          if (!cancelado) setTotalElementosBim(elementos.length);
        } else {
          setTotalElementosBim(0);
        }

        if (pres?.monto_total) {
          megalodonClient.juridico.determinarProcedimiento({ monto: pres.monto_total, es_obra_publica: true })
            .then((r) => { if (!cancelado) setProcedimiento(r); })
            .catch(() => {});
        }
      } finally {
        if (!cancelado) setCargando(false);
      }
    })();
    return () => { cancelado = true; };
  }, [expedienteActivo?.id]);

  const validationResults = useMegalodonStore(s => s.validationResults);
  const calculationResults = useMegalodonStore(s => s.calculationResults);
  const activities = useMemo(() => {
    const validations = validationResults.slice(-3).map(v => ({
      time: new Date(v.timestamp).toLocaleString('es-MX', { hour: '2-digit', minute: '2-digit' }),
      action: `Validacion ejecutada — ${v.rulesPassed}/${v.rulesChecked} reglas aprobadas`,
      user: 'Sistema',
      type: (v.overall === 'PASS' ? 'success' : v.overall === 'WARNING' ? 'warning' : 'error') as 'success' | 'warning' | 'error' | 'info',
    }));
    const calculations = calculationResults.slice(-2).map(c => ({
      time: new Date(c.timestamp).toLocaleString('es-MX', { hour: '2-digit', minute: '2-digit' }),
      action: c.summary,
      user: 'Sistema',
      type: 'info' as const,
    }));
    return [...validations, ...calculations].length > 0
      ? [...validations, ...calculations].slice(0, 6)
      : [{ time: 'Ahora', action: expedienteActivo ? `Trabajando en ${expedienteActivo.titulo}` : 'Bienvenido a Megalodon CostOS — abre o crea un proyecto', user: 'Sistema', type: 'info' as const }];
  }, [validationResults, calculationResults, expedienteActivo?.titulo]);

  if (!expedienteActivo) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-2 text-center px-6 h-full text-[#8A8578]">
        <FolderKanban className="w-8 h-8 opacity-50" />
        <p className="text-sm">No hay ningún expediente activo.</p>
        <p className="text-xs">Abre la app &quot;Proyectos&quot; y selecciona o crea un expediente para ver su resumen.</p>
      </div>
    );
  }

  if (cargando) {
    return <div className="flex-1 flex items-center justify-center text-xs text-[#8A8578] h-full">Cargando resumen de {expedienteActivo.titulo}...</div>;
  }

  const conceptosValidados = ultimaValidacion
    ? `${ultimaValidacion.bitacora_evaluacion.filter((r) => r.estatus === 'PASA').length} / ${ultimaValidacion.bitacora_evaluacion.length}`
    : 'Sin validar';

  return (
    <div className="flex flex-col h-full overflow-auto p-4 gap-4">
      <div className="grid grid-cols-4 gap-3">
        <KpiCard icon={DollarSign} label="Presupuesto Total" value={presupuesto ? formatMXN(presupuesto.monto_total) : 'Sin calcular'} color="#C9A84C" />
        <KpiCard icon={CheckCircle} label="Conceptos Validados" value={conceptosValidados} color="#5A9E6F" />
        <KpiCard icon={AlertTriangle} label="Exposición de Riesgo" value="Ejecutar en Análisis" color="#D4953A" />
        <KpiCard icon={Clock} label="Elementos BIM" value={totalElementosBim !== null ? String(totalElementosBim) : '—'} color="#5A8AB8" />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="bg-[#1A1A26] border border-[#2A2A3E] rounded-lg p-4">
          <h3 className="text-sm font-semibold text-[#E8E4DC] mb-3">Estado del Proyecto</h3>
          <div className="space-y-3 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-[#8A8578]">Identificador</span>
              <span className="text-[#E8E4DC] font-mono">{expedienteActivo.identificador}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[#8A8578]">Estado</span>
              <span className="text-[#C9A84C] font-medium">{expedienteActivo.estado}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[#8A8578]">Procedimiento (backend)</span>
              <span className="text-[#C9A84C] font-medium">{procedimiento?.procedimiento ?? (presupuesto ? 'consultando...' : 'requiere presupuesto')}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[#8A8578]">Presupuesto del expediente</span>
              <span className="font-mono text-[#E8E4DC]">{expedienteActivo.monto_contrato ? formatMXN(expedienteActivo.monto_contrato) : '—'}</span>
            </div>
          </div>
        </div>

        <div className="bg-[#1A1A26] border border-[#2A2A3E] rounded-lg p-4">
          <h3 className="text-sm font-semibold text-[#E8E4DC] mb-3">Última Validación</h3>
          {ultimaValidacion ? (
            <div className="space-y-1.5 text-xs max-h-40 overflow-auto">
              {ultimaValidacion.bitacora_evaluacion.slice(0, 6).map((r) => (
                <div key={r.id_regla} className="flex items-center justify-between">
                  <span className="text-[#8A8578]">{r.seccion}</span>
                  <span className={r.estatus === 'PASA' ? 'text-[#5A9E6F]' : r.estatus === 'FALLA' ? 'text-[#B84A4A]' : 'text-[#8A8578]'}>{r.estatus}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-[#8A8578]">Sin validaciones todavía — corre una en la pestaña &quot;Validación&quot;.</p>
          )}
        </div>
      </div>

      <div className="bg-[#1A1A26] border border-[#2A2A3E] rounded-lg p-4">
        <h3 className="text-sm font-semibold text-[#E8E4DC] mb-3">Actividad Reciente</h3>
        <div className="space-y-1.5">
          {activities.map((act, i) => (
            <div key={i} className="flex items-center gap-3 py-1.5 px-2 rounded hover:bg-[#222235]/30 transition-colors text-xs">
              <div className={`w-2 h-2 rounded-full shrink-0 ${
                act.type === 'success' ? 'bg-[#5A9E6F]' : act.type === 'warning' ? 'bg-[#D4953A]' : 'bg-[#5A8AB8]'
              }`} />
              <span className="text-[#4D4A42] w-20 shrink-0">{act.time}</span>
              <span className="text-[#E8E4DC] flex-1">{act.action}</span>
              <span className="text-[#8A8578]">{act.user}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// MAIN COMPONENT
// =============================================================================
export default function MegalodonCostos() {
  const [activeTab, setActiveTab] = useState<TabId>('resumen');
  const expedienteActivo = useExpedienteStore((s) => s.expedienteActivo());
  const [resumenPresupuesto, setResumenPresupuesto] = useState<Presupuesto | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!expedienteActivo) {
      setResumenPresupuesto(null);
      return;
    }
    void megalodonClient.presupuestos.list(expedienteActivo.id).then((items) => {
      if (!cancelled) setResumenPresupuesto(items[0] ?? null);
    }).catch(() => {
      if (!cancelled) setResumenPresupuesto(null);
    });
    return () => { cancelled = true; };
  }, [expedienteActivo?.id]);

  const totalBudget = resumenPresupuesto?.monto_total ?? 0;

  return (
    <div className="w-full h-full bg-[#12121A] text-[#E8E4DC] flex flex-col font-sans">
      {/* Menu bar */}
      <div className="h-7 shrink-0 bg-[#0A0A0F] border-b border-[#2A2A3E] flex items-center px-3 gap-4 text-[11px] text-[#8A8578]">
        {['Archivo', 'Proyecto', 'Catálogos', 'Análisis', 'Reportes', 'Herramientas', 'Ayuda'].map((m) => (
          <button key={m} className="hover:text-[#E8E4DC] hover:bg-[#222235] px-2 py-0.5 rounded transition-colors">
            {m}
          </button>
        ))}
      </div>

      {/* Tab bar */}
      <div className="flex shrink-0 items-center gap-0 bg-[#0A0A0F] border-b border-[#2A2A3E] px-2">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 text-xs font-medium border-b-2 transition-colors ${
              activeTab === tab.id
                ? 'border-[#C9A84C] text-[#C9A84C]'
                : 'border-transparent text-[#8A8578] hover:text-[#E8E4DC] hover:bg-[#222235]/50'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {activeTab === 'resumen' && <ResumenTab />}
        {activeTab === 'presupuesto' && <BudgetGrid key={expedienteActivo?.id} />}
        {activeTab === 'analisis' && <AnalysisPanel />}
        {activeTab === 'validacion' && <ValidationPanel />}
        {activeTab === 'reporte' && <ReportPanel />}
      </div>

      {/* Status bar */}
      <div className="h-6 shrink-0 bg-[#0A0A0F] border-t border-[#2A2A3E] flex items-center justify-between px-3 text-[10px] font-mono text-[#8A8578]">
        <div className="flex items-center gap-1.5">
          <div className={`w-1.5 h-1.5 rounded-full ${resumenPresupuesto ? 'bg-[#5A9E6F]' : 'bg-[#D4953A]'}`} />
          <span>{resumenPresupuesto ? 'Presupuesto confirmado por backend' : 'Sin presupuesto confirmado'}</span>
        </div>
        <div className="flex items-center gap-4">
          <span>Total: <span className="text-[#C9A84C]">{formatMXN(totalBudget)}</span></span>
        </div>
      </div>
    </div>
  );
}
