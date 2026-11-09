/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 */

import { useCallback, useRef, useState } from 'react';
import { Activity, Dice5, Play, Plus, Square, Trash2 } from 'lucide-react';
import { megalodonClient } from '../../lib/api-client';

type Distribucion = 'normal' | 'triangular' | 'uniform' | 'lognormal' | 'beta';
type Impacto = 'costo_pct' | 'plazo_pct' | 'plazo_dias' | 'costo_y_plazo_pct';

interface SimulationResult {
  mean: number;
  median: number;
  stdDev: number;
  min: number;
  max: number;
  p10: number;
  p90: number;
  p80?: number;
  prob_exceder_presupuesto?: number | null;
  prob_exceder_plazo?: number | null;
  contingencia_p80?: number;
  contingencia_p90?: number;
  plazo?: {
    estado: string;
    media?: number;
    mediana?: number;
    p80?: number;
    p90?: number;
    prob_exceder_plazo?: number | null;
  };
}

interface VariableRiesgo {
  id: string;
  nombre: string;
  distribucion: Distribucion;
  parametros: Record<string, number>;
  impacto: Impacto;
}

const PARAMS_POR_DISTRIBUCION: Record<Distribucion, { key: string; label: string }[]> = {
  normal: [
    { key: 'media', label: 'Media' },
    { key: 'desviacion', label: 'Desv. estándar' },
  ],
  triangular: [
    { key: 'min', label: 'Mínimo' },
    { key: 'moda', label: 'Moda' },
    { key: 'max', label: 'Máximo' },
  ],
  uniform: [
    { key: 'min', label: 'Mínimo' },
    { key: 'max', label: 'Máximo' },
  ],
  lognormal: [
    { key: 'mu', label: 'Mu' },
    { key: 'sigma', label: 'Sigma' },
  ],
  beta: [
    { key: 'alpha', label: 'Alpha' },
    { key: 'beta', label: 'Beta' },
  ],
};

function nuevaVariable(): VariableRiesgo {
  return {
    id: crypto.randomUUID(),
    nombre: '',
    distribucion: 'triangular',
    parametros: { min: -0.05, moda: 0, max: 0.10 },
    impacto: 'costo_pct',
  };
}

const money = (value?: number | null) =>
  typeof value === 'number'
    ? `$${value.toLocaleString('es-MX', { maximumFractionDigits: 2 })}`
    : '—';

export default function MonteCarloApp() {
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState<'idle' | 'running' | 'complete' | 'error'>('idle');
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [iterations, setIterations] = useState(10000);
  const [presupuestoBase, setPresupuestoBase] = useState(1000000);
  const [presupuestoMaximo, setPresupuestoMaximo] = useState(1200000);
  const [plazoBaseDias, setPlazoBaseDias] = useState(180);
  const [plazoMaximoDias, setPlazoMaximoDias] = useState(220);
  const [variables, setVariables] = useState<VariableRiesgo[]>([nuevaVariable()]);
  const taskIdRef = useRef<string | null>(null);

  const actualizarVariable = (id: string, cambios: Partial<VariableRiesgo>) => {
    setVariables((prev) => prev.map((v) => (v.id === id ? { ...v, ...cambios } : v)));
  };

  const cambiarDistribucion = (id: string, distribucion: Distribucion) => {
    const parametros = Object.fromEntries(PARAMS_POR_DISTRIBUCION[distribucion].map(({ key }) => [key, 0]));
    actualizarVariable(id, { distribucion, parametros });
  };

  const startSimulation = useCallback(async () => {
    if (!variables.length || variables.some((v) => !v.nombre.trim())) {
      setErrorMsg('Agrega al menos una variable de riesgo con nombre.');
      setStatus('error');
      return;
    }
    if (presupuestoMaximo < presupuestoBase || plazoMaximoDias < plazoBaseDias) {
      setErrorMsg('Los máximos deben ser mayores o iguales a los valores base.');
      setStatus('error');
      return;
    }

    setStatus('running');
    setProgress(0);
    setResult(null);
    setErrorMsg(null);

    try {
      const response: any = await megalodonClient.montecarlo.simular({
        presupuestoBase,
        presupuestoMaximo,
        plazoBaseDias,
        plazoMaximoDias,
        variables: variables.map(({ nombre, distribucion, parametros, impacto }) => ({
          nombre,
          distribucion,
          parametros,
          impacto,
        })),
        iteraciones: iterations,
      });
      if (!response.task_id) throw new Error('El backend no devolvió task_id.');
      taskIdRef.current = response.task_id;

      const poll = async (): Promise<void> => {
        const state: any = await megalodonClient.montecarlo.consultarStatus(response.task_id);
        setProgress(state.progreso ?? 0);

        if (state.status === 'COMPLETADO') {
          taskIdRef.current = null;
          setResult(state.result as SimulationResult);
          setStatus('complete');
          return;
        }
        if (state.status === 'ERROR') {
          taskIdRef.current = null;
          setErrorMsg(state.error?.mensaje || 'La simulación falló en backend.');
          setStatus('error');
          return;
        }
        if (state.status === 'CANCELADO') {
          taskIdRef.current = null;
          setStatus('idle');
          return;
        }
        if (taskIdRef.current === response.task_id) {
          window.setTimeout(() => void poll(), 1500);
        }
      };

      await poll();
    } catch (error) {
      taskIdRef.current = null;
      setStatus('error');
      setErrorMsg(error instanceof Error ? error.message : 'No se pudo ejecutar la simulación.');
    }
  }, [iterations, plazoBaseDias, plazoMaximoDias, presupuestoBase, presupuestoMaximo, variables]);

  const cancelSimulation = useCallback(async () => {
    const taskId = taskIdRef.current;
    if (!taskId) return;
    try {
      await megalodonClient.montecarlo.cancel(taskId);
      taskIdRef.current = null;
      setProgress(0);
      setStatus('idle');
    } catch (error) {
      setStatus('error');
      setErrorMsg(error instanceof Error ? error.message : 'No se pudo cancelar la simulación.');
    }
  }, []);

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Dice5 className="w-6 h-6" />
          Monte Carlo — Riesgo de costo y plazo
        </h1>
        <span className="text-xs text-gray-500">Motor oficial backend + Celery</span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <label className="text-sm">
          <span className="block mb-1 font-medium">Iteraciones</span>
          <input type="number" min={100} max={1000000} value={iterations} onChange={(e) => setIterations(Number(e.target.value))} disabled={status === 'running'} className="w-full px-3 py-2 border rounded" />
        </label>
        <label className="text-sm">
          <span className="block mb-1 font-medium">Presupuesto base</span>
          <input type="number" min={1} value={presupuestoBase} onChange={(e) => setPresupuestoBase(Number(e.target.value))} disabled={status === 'running'} className="w-full px-3 py-2 border rounded" />
        </label>
        <label className="text-sm">
          <span className="block mb-1 font-medium">Presupuesto máximo</span>
          <input type="number" min={presupuestoBase} value={presupuestoMaximo} onChange={(e) => setPresupuestoMaximo(Number(e.target.value))} disabled={status === 'running'} className="w-full px-3 py-2 border rounded" />
        </label>
        <label className="text-sm">
          <span className="block mb-1 font-medium">Plazo base / máximo (días)</span>
          <div className="grid grid-cols-2 gap-2">
            <input type="number" min={1} value={plazoBaseDias} onChange={(e) => setPlazoBaseDias(Number(e.target.value))} disabled={status === 'running'} className="w-full px-2 py-2 border rounded" />
            <input type="number" min={plazoBaseDias} value={plazoMaximoDias} onChange={(e) => setPlazoMaximoDias(Number(e.target.value))} disabled={status === 'running'} className="w-full px-2 py-2 border rounded" />
          </div>
        </label>
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">Variables de riesgo</h2>
          <button onClick={() => setVariables((prev) => [...prev, nuevaVariable()])} disabled={status === 'running'} className="flex items-center gap-1 text-sm text-blue-600 disabled:opacity-50">
            <Plus className="w-4 h-4" /> Agregar variable
          </button>
        </div>
        {variables.map((v) => (
          <div key={v.id} className="p-3 border rounded-lg bg-gray-50 space-y-2">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
              <input type="text" placeholder="Nombre (ej. acero)" value={v.nombre} onChange={(e) => actualizarVariable(v.id, { nombre: e.target.value })} disabled={status === 'running'} className="px-3 py-2 border rounded text-sm" />
              <select value={v.distribucion} onChange={(e) => cambiarDistribucion(v.id, e.target.value as Distribucion)} disabled={status === 'running'} className="px-2 py-2 border rounded text-sm">
                <option value="normal">Normal</option>
                <option value="triangular">Triangular</option>
                <option value="uniform">Uniforme</option>
                <option value="lognormal">Log-normal</option>
                <option value="beta">Beta</option>
              </select>
              <select value={v.impacto} onChange={(e) => actualizarVariable(v.id, { impacto: e.target.value as Impacto })} disabled={status === 'running'} className="px-2 py-2 border rounded text-sm">
                <option value="costo_pct">Costo %</option>
                <option value="plazo_pct">Plazo %</option>
                <option value="plazo_dias">Plazo días</option>
                <option value="costo_y_plazo_pct">Costo + plazo %</option>
              </select>
              <button onClick={() => setVariables((prev) => prev.filter((x) => x.id !== v.id))} disabled={status === 'running' || variables.length === 1} className="justify-self-end p-2 text-red-500 hover:bg-red-50 rounded disabled:opacity-50">
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
              {PARAMS_POR_DISTRIBUCION[v.distribucion].map((param) => (
                <label key={param.key} className="text-xs">
                  <span className="block text-gray-500 mb-1">{param.label}</span>
                  <input type="number" value={v.parametros[param.key] ?? 0} onChange={(e) => actualizarVariable(v.id, { parametros: { ...v.parametros, [param.key]: Number(e.target.value) } })} disabled={status === 'running'} className="w-full px-2 py-1 border rounded" />
                </label>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-3">
        {status === 'running' ? (
          <button onClick={() => void cancelSimulation()} className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded">
            <Square className="w-4 h-4" /> Cancelar ejecución
          </button>
        ) : (
          <button onClick={() => void startSimulation()} className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded">
            <Play className="w-4 h-4" /> Ejecutar Monte Carlo oficial
          </button>
        )}
      </div>

      {status === 'running' && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm"><Activity className="w-4 h-4 animate-pulse" /> Procesando {progress}%</div>
          <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden"><div className="bg-blue-600 h-3 transition-all" style={{ width: `${progress}%` }} /></div>
        </div>
      )}

      {status === 'error' && errorMsg && <div className="p-4 bg-red-50 border border-red-200 rounded text-red-700">{errorMsg}</div>}

      {status === 'complete' && result && (
        <div className="p-4 bg-green-50 border border-green-200 rounded space-y-4">
          <h3 className="font-semibold text-green-800">Simulación completada y persistida</h3>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <Metric label="Media" value={money(result.mean)} />
            <Metric label="P50" value={money(result.median)} />
            <Metric label="P80" value={money(result.p80)} />
            <Metric label="P90" value={money(result.p90)} />
            <Metric label="P95" value={money(result.max)} />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Metric label="Prob. exceder presupuesto" value={result.prob_exceder_presupuesto == null ? 'No evaluada' : `${(result.prob_exceder_presupuesto * 100).toFixed(2)}%`} />
            <Metric label="Contingencia P80" value={money(result.contingencia_p80)} />
            <Metric label="Contingencia P90" value={money(result.contingencia_p90)} />
            <Metric label="Clipping" value={String((result as any).valores_recortados ?? 0)} />
          </div>
          {result.plazo?.estado === 'SIMULADO' ? (
            <div className="p-3 bg-white border rounded">
              <h4 className="font-semibold mb-2">Riesgo de plazo</h4>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Metric label="P50" value={`${(result.plazo.mediana ?? 0).toFixed(1)} días`} />
                <Metric label="P80" value={`${(result.plazo.p80 ?? 0).toFixed(1)} días`} />
                <Metric label="P90" value={`${(result.plazo.p90 ?? 0).toFixed(1)} días`} />
                <Metric label="Prob. exceder" value={result.plazo.prob_exceder_plazo == null ? 'No evaluada' : `${(result.plazo.prob_exceder_plazo * 100).toFixed(2)}%`} />
              </div>
            </div>
          ) : (
            <div className="p-3 bg-white border rounded text-sm text-gray-600">Plazo no simulado.</div>
          )}
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="p-3 bg-white border rounded">
      <div className="text-xs text-gray-500">{label}</div>
      <div className="font-mono text-sm mt-1">{value}</div>
    </div>
  );
}
