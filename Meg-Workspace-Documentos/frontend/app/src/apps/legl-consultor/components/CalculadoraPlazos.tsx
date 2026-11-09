/**
 * Calculadora de Plazos Interactiva
 * Calcula días hábiles, fecha de cierre, alertas de vencimiento
 */
import { useState } from 'react';
import { motion } from 'framer-motion';
import { Calendar, Clock, AlertTriangle, CheckCircle2, Calculator } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';
import { claveProcedimiento, nombreProcedimiento, plazosPara, advertenciaConfiabilidad } from '../lib/procedimiento';

interface ResultadoPlazo {
  procedimiento: string;
  nombre: string;
  plazos: {
    publicacion_dias_habiles: number;
    recepcion_dias_habiles: number;
    total_minimo: number;
  };
  fecha_inicio: string;
  fecha_cierre_estimada: string;
  fecha_fallo_estimada: string;
  alertas: string[];
}

export default function CalculadoraPlazos() {
  const [monto, setMonto] = useState('');
  const [presupuestoDependenciaMiles, setPresupuestoDependenciaMiles] = useState('');
  const [fechaInicio, setFechaInicio] = useState(new Date().toISOString().split('T')[0]);
  const [resultado, setResultado] = useState<ResultadoPlazo | null>(null);
  const [advertencia, setAdvertencia] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);

  const calcular = async () => {
    if (!monto.trim()) return;
    setCargando(true);
    try {
      const res = await megalodonClient.juridico.determinarProcedimiento({
        monto: parseFloat(monto),
        es_obra_publica: true,
        presupuesto_dependencia_miles: presupuestoDependenciaMiles.trim()
          ? parseFloat(presupuestoDependenciaMiles)
          : undefined,
      });
      setAdvertencia(advertenciaConfiabilidad(res));

      if (!res.valido) {
        setResultado(null);
        return;
      }

      const proc = claveProcedimiento(res);
      const plazos = proc ? plazosPara(proc) : { publicacionDiasHabiles: 0, recepcionDiasHabiles: 0, totalMinimo: 0 };
      const totalMinimo = plazos.totalMinimo;

      // CORREGIDO (contra-auditoría V8): antes se calculaban fecha_cierre/
      // fecha_fallo con Date.setDate() -- días CALENDARIO -- pese a que la
      // UI y la ley hablan de días HÁBILES. Ahora se piden al backend, que
      // usa el calendario laboral real (LFT Art. 74, ya usado por el
      // módulo de programación/CPM).
      const fechas = proc
        ? await megalodonClient.legal.calcularFechas(fechaInicio, proc)
        : null;

      const alertas: string[] = [];
      if (totalMinimo < 10) {
        alertas.push('Plazo corto: Asegúrate de que los licitantes tengan tiempo suficiente');
      }
      if (proc === 'licitacion_publica') {
        alertas.push('Monto elevado: Requiere licitación pública obligatoria');
      }
      if (proc === 'adjudicacion_directa') {
        alertas.push('Adjudicación directa: Requiere justificación técnica documentada');
      }

      const aISO = (iso: string) => new Date(iso + 'T00:00:00').toLocaleDateString('es-MX');

      setResultado({
        procedimiento: res.procedimiento,
        nombre: nombreProcedimiento(res),
        plazos: {
          publicacion_dias_habiles: plazos.publicacionDiasHabiles,
          recepcion_dias_habiles: plazos.recepcionDiasHabiles,
          total_minimo: totalMinimo,
        },
        fecha_inicio: fechas ? aISO(fechas.fecha_inicio) : new Date(fechaInicio + 'T00:00:00').toLocaleDateString('es-MX'),
        fecha_cierre_estimada: fechas ? aISO(fechas.fecha_cierre_estimada) : '—',
        fecha_fallo_estimada: fechas ? aISO(fechas.fecha_fallo_estimada) : '—',
        alertas,
      });
    } catch (e) {
      console.error(e);
    } finally {
      setCargando(false);
    }
  };

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-2 mb-4">
        <Calculator className="w-4 h-4 text-cyan-400" />
        <h3 className="text-sm font-semibold text-zinc-200">Calculadora de Plazos</h3>
      </div>

      <div className="space-y-3 mb-4">
        <div>
          <label className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1 block">Monto Estimado ($)</label>
          <input
            type="number"
            value={monto}
            onChange={(e) => setMonto(e.target.value)}
            placeholder="Ej: 5000000"
            className="w-full bg-zinc-800/60 border border-zinc-700 rounded-lg px-3 py-2 text-sm 
                     text-zinc-200 placeholder-zinc-600 focus:outline-hidden focus:border-cyan-500/40"
          />
        </div>
        <div>
          <label className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1 block">Fecha de Inicio</label>
          <input
            type="date"
            value={fechaInicio}
            onChange={(e) => setFechaInicio(e.target.value)}
            className="w-full bg-zinc-800/60 border border-zinc-700 rounded-lg px-3 py-2 text-sm 
                     text-zinc-200 focus:outline-hidden focus:border-cyan-500/40"
          />
        </div>
        <div>
          <label className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1 block">
            Presupuesto Autorizado de la Dependencia (miles $)
          </label>
          <input
            type="number"
            value={presupuestoDependenciaMiles}
            onChange={(e) => setPresupuestoDependenciaMiles(e.target.value)}
            placeholder="Ej: 45000"
            title="El Anexo 9 del PEF es una tabla escalonada por este dato, no por el monto del contrato aislado."
            className="w-full bg-zinc-800/60 border border-zinc-700 rounded-lg px-3 py-2 text-sm 
                     text-zinc-200 placeholder-zinc-600 focus:outline-hidden focus:border-cyan-500/40"
          />
        </div>
        <button
          onClick={calcular}
          disabled={cargando || !monto.trim()}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-cyan-500/15 
                   border border-cyan-500/30 text-cyan-400 hover:bg-cyan-500/25 transition-colors 
                   text-sm font-medium disabled:opacity-30"
        >
          <Clock className="w-4 h-4" />
          {cargando ? 'Calculando...' : 'Calcular Plazos'}
        </button>
      </div>

      {advertencia && (
        <div className="mb-3 flex items-start gap-2 p-2 rounded-lg bg-amber-500/5 border border-amber-500/15">
          <AlertTriangle className="w-3 h-3 text-amber-400 mt-0.5 shrink-0" />
          <p className="text-[11px] text-amber-300">{advertencia}</p>
        </div>
      )}

      {resultado && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-3 overflow-auto"
        >
          {/* Procedimiento detectado */}
          <div className="p-3 rounded-xl bg-cyan-500/5 border border-cyan-500/20">
            <p className="text-[10px] text-cyan-400 uppercase tracking-wider mb-1">Procedimiento Detectado</p>
            <p className="text-lg font-bold text-zinc-100">{resultado.nombre}</p>
          </div>

          {/* Timeline visual */}
          <div className="p-3 rounded-xl bg-zinc-800/40 border border-zinc-700/50">
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-3">Timeline Estimado</p>
            <div className="space-y-2">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center shrink-0">
                  <Calendar className="w-3.5 h-3.5 text-emerald-400" />
                </div>
                <div className="flex-1">
                  <p className="text-xs text-zinc-300">Inicio</p>
                  <p className="text-[10px] text-zinc-500">{resultado.fecha_inicio}</p>
                </div>
              </div>
              <div className="ml-4 w-0.5 h-4 bg-zinc-700" />
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-amber-500/15 border border-amber-500/30 flex items-center justify-center shrink-0">
                  <Clock className="w-3.5 h-3.5 text-amber-400" />
                </div>
                <div className="flex-1">
                  <p className="text-xs text-zinc-300">Cierre de Proposiciones</p>
                  <p className="text-[10px] text-zinc-500">{resultado.fecha_cierre_estimada}</p>
                  <p className="text-[10px] text-amber-400">+{resultado.plazos.total_minimo} días hábiles</p>
                </div>
              </div>
              <div className="ml-4 w-0.5 h-4 bg-zinc-700" />
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-rose-500/15 border border-rose-500/30 flex items-center justify-center shrink-0">
                  <CheckCircle2 className="w-3.5 h-3.5 text-rose-400" />
                </div>
                <div className="flex-1">
                  <p className="text-xs text-zinc-300">Fallo Estimado</p>
                  <p className="text-[10px] text-zinc-500">{resultado.fecha_fallo_estimada}</p>
                </div>
              </div>
            </div>
          </div>

          {/* Alertas */}
          {resultado.alertas.length > 0 && (
            <div className="space-y-1.5">
              {resultado.alertas.map((alerta, i) => (
                <div key={i} className="flex items-start gap-2 p-2 rounded-lg bg-amber-500/5 border border-amber-500/15">
                  <AlertTriangle className="w-3 h-3 text-amber-400 mt-0.5 shrink-0" />
                  <p className="text-[11px] text-amber-300">{alerta}</p>
                </div>
              ))}
            </div>
          )}
        </motion.div>
      )}
    </div>
  );
}
