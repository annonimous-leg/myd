/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { useState, useEffect, useCallback } from 'react';
import {
  CalendarDays, Loader2, AlertCircle, RefreshCw, X, Save, Trash2, FolderKanban,
  GanttChartSquare, Sigma, Gauge, TrendingUp, GitBranch, type LucideIcon,
} from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';
import { useExpedienteStore } from '@/stores/useExpedienteStore';
import type { Actividad, Programa } from '@/lib/megalodon-client';
import GanttChart from './GanttChart';
import NuevoCronograma from './NuevoCronograma';
import PertPanel from './components/PertPanel';
import EvmPanel from './components/EvmPanel';
import CurvaSPanel from './components/CurvaSPanel';
import RutaCriticaPanel from './components/RutaCriticaPanel';

type Tab = 'calendario' | 'gantt' | 'pert' | 'evm' | 'curva-s' | 'ruta-critica';
const TABS: { id: Tab; label: string; icon: LucideIcon }[] = [
  { id: 'calendario', label: 'Calendario', icon: CalendarDays },
  { id: 'gantt', label: 'Gantt', icon: GanttChartSquare },
  { id: 'pert', label: 'PERT', icon: Sigma },
  { id: 'evm', label: 'EVM', icon: Gauge },
  { id: 'curva-s', label: 'Curva S', icon: TrendingUp },
  { id: 'ruta-critica', label: 'Ruta crítica', icon: GitBranch },
];

const TIPOS_ACTIVIDAD = ['CONSTRUCCION', 'SUMINISTRO', 'INSTALACION', 'PRUEBA', 'DOCUMENTACION', 'HITO'];
const TIPOS_DEPENDENCIA: Record<string, string> = {
  FS: 'Fin → Inicio',
  SS: 'Inicio → Inicio',
  FF: 'Fin → Fin',
  SF: 'Inicio → Fin',
};

function EditorActividad({
  actividad,
  todas,
  onClose,
  onGuardar,
  guardando,
}: {
  actividad: Actividad;
  todas: Actividad[];
  onClose: () => void;
  onGuardar: (cambios: {
    nombre?: string;
    wbs_codigo?: string;
    duracion?: number;
    tipo?: string;
    predecesoras?: string[];
    dependencias_tipo?: Record<string, string>;
  }) => Promise<void>;
  guardando: boolean;
}) {
  const [nombre, setNombre] = useState(actividad.nombre);
  const [wbs, setWbs] = useState(actividad.wbs_codigo);
  const [duracion, setDuracion] = useState(String(actividad.duracion));
  const [tipo, setTipo] = useState(actividad.tipo);
  const [predecesoras, setPredecesoras] = useState<string[]>(actividad.predecesoras || []);
  const [depTipos, setDepTipos] = useState<Record<string, string>>(actividad.dependencias_tipo || {});
  const [nuevaPred, setNuevaPred] = useState('');

  // El input se re-crea cuando cambia la actividad seleccionada (no al
  // reescribir mientras se edita) -- por eso la key en el padre es el id.
  const otras = todas.filter((a) => a.identificador !== actividad.identificador);
  const disponibles = otras.filter((a) => !predecesoras.includes(a.identificador));

  const handleGuardar = async () => {
    await onGuardar({
      nombre: nombre !== actividad.nombre ? nombre : undefined,
      wbs_codigo: wbs !== actividad.wbs_codigo ? wbs : undefined,
      duracion: Number(duracion) !== actividad.duracion ? Number(duracion) : undefined,
      tipo: tipo !== actividad.tipo ? tipo : undefined,
      predecesoras:
        JSON.stringify(predecesoras) !== JSON.stringify(actividad.predecesoras || []) ? predecesoras : undefined,
      dependencias_tipo: Object.keys(depTipos).length > 0 ? depTipos : undefined,
    });
  };

  return (
    <div className="w-[320px] shrink-0 border-l border-[#2A2A3E] bg-[#0F0F16] flex flex-col overflow-y-auto">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#2A2A3E]">
        <h3 className="text-sm font-semibold text-[#E8E4DC]">Editar actividad</h3>
        <button onClick={onClose} className="text-[#8A8578] hover:text-[#E8E4DC]">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="p-4 space-y-3 flex-1">
        <div>
          <label className="block text-[11px] text-[#8A8578] mb-1">Nombre</label>
          <input
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            className="w-full h-9 bg-[#0A0A0F] border border-[#2A2A3E] rounded-md px-3 text-sm text-[#E8E4DC] outline-hidden focus:border-[#C9A84C]"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-[11px] text-[#8A8578] mb-1">WBS</label>
            <input
              value={wbs}
              onChange={(e) => setWbs(e.target.value)}
              className="w-full h-9 bg-[#0A0A0F] border border-[#2A2A3E] rounded-md px-3 text-sm text-[#E8E4DC] outline-hidden focus:border-[#C9A84C]"
            />
          </div>
          <div>
            <label className="block text-[11px] text-[#8A8578] mb-1">Duración (días)</label>
            <input
              type="number"
              min={0.5}
              step={0.5}
              value={duracion}
              onChange={(e) => setDuracion(e.target.value)}
              className="w-full h-9 bg-[#0A0A0F] border border-[#2A2A3E] rounded-md px-3 text-sm text-[#E8E4DC] outline-hidden focus:border-[#C9A84C]"
            />
          </div>
        </div>

        <div>
          <label className="block text-[11px] text-[#8A8578] mb-1">Tipo</label>
          <select
            value={tipo}
            onChange={(e) => setTipo(e.target.value)}
            className="w-full h-9 bg-[#0A0A0F] border border-[#2A2A3E] rounded-md px-3 text-sm text-[#E8E4DC] outline-hidden focus:border-[#C9A84C]"
          >
            {TIPOS_ACTIVIDAD.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>

        <div className="pt-2 border-t border-[#2A2A3E]">
          <label className="block text-[11px] text-[#8A8578] mb-2">
            Predecesoras
            <span className="block text-[10px] opacity-70 mt-0.5">
              (o arrastra desde el punto de salida de una barra en el Gantt)
            </span>
          </label>

          {predecesoras.length === 0 && (
            <p className="text-[11px] text-[#8A8578] mb-2">Sin predecesoras — inicia al comienzo del programa.</p>
          )}

          <div className="space-y-1.5 mb-2">
            {predecesoras.map((predId) => {
              const pred = todas.find((a) => a.identificador === predId);
              return (
                <div key={predId} className="flex items-center gap-1.5">
                  <span className="flex-1 text-xs text-[#E8E4DC] truncate">{pred?.nombre || predId}</span>
                  <select
                    value={depTipos[predId] || 'FS'}
                    onChange={(e) => setDepTipos((d) => ({ ...d, [predId]: e.target.value }))}
                    className="h-7 bg-[#0A0A0F] border border-[#2A2A3E] rounded text-[10px] text-[#8A8578] px-1 outline-hidden"
                  >
                    {Object.entries(TIPOS_DEPENDENCIA).map(([k, label]) => (
                      <option key={k} value={k}>{label}</option>
                    ))}
                  </select>
                  <button
                    onClick={() => setPredecesoras((p) => p.filter((id) => id !== predId))}
                    className="text-[#8A8578] hover:text-[#B84A4A]"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              );
            })}
          </div>

          {disponibles.length > 0 && (
            <div className="flex items-center gap-1.5">
              <select
                value={nuevaPred}
                onChange={(e) => setNuevaPred(e.target.value)}
                className="flex-1 h-8 bg-[#0A0A0F] border border-[#2A2A3E] rounded-md text-xs text-[#E8E4DC] px-2 outline-hidden"
              >
                <option value="">Agregar predecesora...</option>
                {disponibles.map((a) => (
                  <option key={a.identificador} value={a.identificador}>{a.nombre}</option>
                ))}
              </select>
              <button
                disabled={!nuevaPred}
                onClick={() => {
                  if (nuevaPred) {
                    setPredecesoras((p) => [...p, nuevaPred]);
                    setNuevaPred('');
                  }
                }}
                className="h-8 px-2 text-xs bg-[#1C1C28] border border-[#2A2A3E] rounded-md text-[#E8E4DC] disabled:opacity-40"
              >
                +
              </button>
            </div>
          )}
        </div>

        <div className="pt-3 border-t border-[#2A2A3E] text-[11px] text-[#8A8578] space-y-1">
          <p>Ruta crítica: <span className={actividad.en_ruta_critica ? 'text-[#B84A4A]' : 'text-[#E8E4DC]'}>{actividad.en_ruta_critica ? 'Sí' : 'No'}</span></p>
          <p>Holgura total: {actividad.holgura_total} días</p>
          {actividad.inicio_temprano && <p>Inicio: {new Date(actividad.inicio_temprano).toLocaleDateString('es-MX')}</p>}
          {actividad.fin_temprano && <p>Fin: {new Date(actividad.fin_temprano).toLocaleDateString('es-MX')}</p>}
        </div>
      </div>

      <div className="p-4 border-t border-[#2A2A3E]">
        <button
          onClick={handleGuardar}
          disabled={guardando}
          className="w-full h-9 bg-[#C9A84C] text-[#030305] font-semibold text-sm rounded-md hover:bg-[#D4B85A] transition-colors disabled:opacity-60 flex items-center justify-center gap-2"
        >
          {guardando ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          Guardar y recalcular
        </button>
      </div>
    </div>
  );
}

export default function ProgramacionObra({ workspace = false }: { workspace?: boolean }) {
  const [creando, setCreando] = useState(false);
  const expedienteId = useExpedienteStore((s) => s.expedienteActivoId);

  const [programas, setProgramas] = useState<Programa[]>([]);
  const [programaId, setProgramaId] = useState<string | null>(null);
  const [actividades, setActividades] = useState<Actividad[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [tab, setTab] = useState<Tab>('gantt');

  const cargarProgramas = useCallback(async () => {
    if (!expedienteId) return;
    setLoading(true);
    setError('');
    try {
      const solicitado = new URLSearchParams(window.location.search).get('programa');
      const lista = await megalodonClient.programacion.listar(expedienteId);
      if (solicitado && !lista.some(p => p.id === solicitado)) {
        const detalle = await megalodonClient.programacion.obtener(expedienteId, solicitado);
        lista.unshift(detalle.programa);
      }
      setProgramas(lista);
      setProgramaId(previous => {
        if (solicitado && lista.some(p => p.id === solicitado)) return solicitado;
        return lista.some(p => p.id === previous) ? previous : lista[0]?.id || null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudieron cargar los programas');
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expedienteId]);

  const cargarActividades = useCallback(async () => {
    if (!expedienteId || !programaId) return;
    setLoading(true);
    setError('');
    try {
      const lista = await megalodonClient.programacion.listarActividades(expedienteId, programaId);
      setActividades(lista);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudieron cargar las actividades');
    } finally {
      setLoading(false);
    }
  }, [expedienteId, programaId]);

  useEffect(() => { cargarProgramas(); }, [cargarProgramas]);
  useEffect(() => { cargarActividades(); }, [cargarActividades]);

  const recalcularCPM = async () => {
    if (!expedienteId || !programaId) return;
    setBusy(true);
    setError('');
    try {
      await megalodonClient.programacion.calcularCPM(expedienteId, programaId);
      await cargarActividades();
      await cargarProgramas();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo calcular el CPM');
    } finally {
      setBusy(false);
    }
  };

  const guardarCambios = async (
    actividadId: string,
    cambios: Parameters<typeof megalodonClient.programacion.actualizarActividad>[3],
  ) => {
    if (!expedienteId || !programaId) return;
    setBusy(true);
    setError('');
    try {
      await megalodonClient.programacion.actualizarActividad(expedienteId, programaId, actividadId, cambios);
      await cargarActividades();
      await cargarProgramas();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo guardar el cambio');
    } finally {
      setBusy(false);
    }
  };

  const conectarDependencia = (actividadId: string, nuevaPredecesora: string) => {
    const act = actividades.find((a) => a.identificador === actividadId);
    if (!act) return;
    const actuales = act.predecesoras || [];
    if (actuales.includes(nuevaPredecesora)) return;
    guardarCambios(actividadId, { predecesoras: [...actuales, nuevaPredecesora] });
  };

  const resizeDuracion = (actividadId: string, nuevaDuracion: number) => {
    guardarCambios(actividadId, { duracion: nuevaDuracion });
  };

  const programaActual = programas.find((p) => p.id === programaId);
  const actividadSeleccionada = actividades.find((a) => a.identificador === selectedId) || null;

  if (!expedienteId) {
    return (
      <div className="h-full flex flex-col items-center justify-center bg-[#0A0A0F] text-[#8A8578] gap-2 text-center p-6">
        <FolderKanban className="w-10 h-10 opacity-40" />
        <p className="text-sm">Selecciona un expediente activo en "Proyectos" primero.</p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-[#0A0A0F] text-[#E8E4DC]">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#2A2A3E] flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <CalendarDays className="w-4 h-4 text-[#C9A84C]" />
          <h2 className="text-sm font-semibold">{workspace ? 'Cronograma de obra' : 'Programación de Obra'}</h2>
        </div>

        <div className="flex items-center gap-2">
          {workspace && <button type="button" disabled={busy} onClick={() => setCreando(value => !value)}
            className="rounded border border-zinc-600 p-2">{creando ? 'Cerrar formulario' : 'Nuevo cronograma'}</button>}
          {programas.length > 0 && (
            <select
              aria-label="Cronograma de esta obra"
              value={programaId || ''}
              onChange={(e) => { setProgramaId(e.target.value); setSelectedId(null); }}
              className="h-8 bg-[#12121A] border border-[#2A2A3E] rounded-md px-2 text-xs text-[#E8E4DC] outline-hidden"
            >
              {programas.map((p) => (
                <option key={p.id} value={p.id}>{p.nombre}</option>
              ))}
            </select>
          )}
          <button
            onClick={recalcularCPM}
            disabled={busy || !programaId}
            className="flex items-center gap-1.5 h-8 px-3 bg-[#1C1C28] border border-[#2A2A3E] text-xs font-medium rounded-md hover:border-[#C9A84C] transition-colors disabled:opacity-50"
          >
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
            Calcular CPM
          </button>
        </div>
      </div>

      {workspace && creando && <NuevoCronograma expedienteId={expedienteId} onCreated={programa => {
        setProgramas(prev => [...prev, programa]);
        setProgramaId(programa.id);
        setActividades([]);
        setSelectedId(null);
        setCreando(false);
      }} />}
      <div className="flex items-center gap-1 px-3 pt-1.5 border-b border-[#2A2A3E]">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-t-md"
            style={
              tab === id
                ? { color: '#C9A84C', borderBottom: '2px solid #C9A84C', background: '#12121A' }
                : { color: '#8A8578', borderBottom: '2px solid transparent' }
            }
          >
            <Icon className="w-3.5 h-3.5" /> {label}
          </button>
        ))}
      </div>

      {programaActual && (
        <div className="flex items-center gap-4 px-4 py-2 text-[11px] text-[#8A8578] border-b border-[#2A2A3E]">
          <span>{programaActual.identificador}</span>
          <span>Duración plan: {programaActual.duracion_plan_dias} días</span>
          {programaActual.fecha_fin_plan && (
            <span>Fin plan: {new Date(programaActual.fecha_fin_plan).toLocaleDateString('es-MX')}</span>
          )}
          <span>Estado: {programaActual.estado}</span>
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 text-sm text-[#B84A4A] bg-[#B84A4A]/10 border-b border-[#B84A4A]/30 px-4 py-2">
          <AlertCircle className="w-4 h-4 shrink-0" /> {error}
        </div>
      )}

      {loading && actividades.length === 0 ? (
        <div className="flex-1 flex items-center justify-center gap-2 text-sm text-[#8A8578]">
          <Loader2 className="w-4 h-4 animate-spin" /> Cargando...
        </div>
      ) : programas.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-sm text-[#8A8578] text-center p-6">
          Este expediente todavía no tiene cronogramas. En Workspace puedes crear uno o abrir el generado desde BIM.
        </div>
      ) : (
        <div className="flex-1 flex min-h-0">
          {tab === 'gantt' ? (
            <>
              {actividades.some(a => !a.inicio_temprano || !a.fin_temprano) && (
                <aside className="w-52 shrink-0 overflow-auto p-3 text-xs" aria-label="Actividades por programar">
                  <p>Revisa duraciones y dependencias antes de calcular.</p>
                  {actividades.filter(a => !a.inicio_temprano || !a.fin_temprano).map(a => (
                    <button type="button" key={a.id} className="my-2 block text-left underline"
                      onClick={() => setSelectedId(a.identificador)}>{a.nombre}</button>
                  ))}
                </aside>
              )}
              <GanttChart
                actividades={actividades}
                selectedId={selectedId}
                busy={busy}
                onSelectActividad={setSelectedId}
                onResizeDuracion={resizeDuracion}
                onConectarDependencia={conectarDependencia}
              />
              {actividadSeleccionada && (
                <EditorActividad
                  key={actividadSeleccionada.identificador}
                  actividad={actividadSeleccionada}
                  todas={actividades}
                  onClose={() => setSelectedId(null)}
                  guardando={busy}
                  onGuardar={(cambios) => guardarCambios(actividadSeleccionada.identificador, cambios)}
                />
              )}
            </>
          ) : (
            <div className="flex-1 min-h-0">
              {tab === 'calendario' && <div className="overflow-auto p-4">
                <h3 className="mb-3 font-semibold">Calendario de actividades calculadas</h3>
                <table className="w-full text-left text-xs">
                  <thead><tr><th>Actividad</th><th>Inicio</th><th>Fin</th></tr></thead>
                  <tbody>{actividades.filter(a => a.inicio_temprano && a.fin_temprano)
                    .sort((a, b) => Date.parse(a.inicio_temprano!) - Date.parse(b.inicio_temprano!))
                    .map(a => <tr key={a.id}><td className="py-2">{a.nombre}</td>
                      <td>{a.inicio_temprano!.slice(0, 10)}</td><td>{a.fin_temprano!.slice(0, 10)}</td></tr>)}</tbody>
                </table>
                {actividades.some(a => !a.inicio_temprano || !a.fin_temprano) &&
                  <p className="mt-3">Hay actividades pendientes de calcular. Revisa sus duraciones y dependencias y ejecuta CPM.</p>}
              </div>}
              {tab === 'pert' && programaId && <PertPanel expedienteId={expedienteId} programaId={programaId} />}
              {tab === 'evm' && programaId && <EvmPanel expedienteId={expedienteId} programaId={programaId} />}
              {tab === 'curva-s' && programaId && <CurvaSPanel expedienteId={expedienteId} programaId={programaId} />}
              {tab === 'ruta-critica' && programaId && (
                <RutaCriticaPanel expedienteId={expedienteId} programaId={programaId} actividades={actividades} />
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
