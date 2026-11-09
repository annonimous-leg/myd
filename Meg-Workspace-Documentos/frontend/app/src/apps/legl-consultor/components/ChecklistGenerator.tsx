/**
 * Generador de Checklist según Procedimiento Detectado
 */
import { useState } from 'react';
import { motion } from 'framer-motion';
import { ListChecks, RefreshCw, CheckCircle2, Circle, AlertTriangle } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';
import { claveProcedimiento, nombreProcedimiento, advertenciaConfiabilidad } from '../lib/procedimiento';

interface CheckItem {
  id: string;
  texto: string;
  categoria: string;
  obligatorio: boolean;
  completado: boolean;
}

export default function ChecklistGenerator() {
  const [monto, setMonto] = useState('');
  const [presupuestoDependenciaMiles, setPresupuestoDependenciaMiles] = useState('');
  const [checklist, setChecklist] = useState<CheckItem[]>([]);
  const [procedimiento, setProcedimiento] = useState('');
  const [advertencia, setAdvertencia] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);
  const [progreso, setProgreso] = useState(0);

  const generar = async () => {
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
        setProcedimiento('No determinado');
        setChecklist([]);
        return;
      }

      const proc = claveProcedimiento(res);
      setProcedimiento(nombreProcedimiento(res));

      // Generar checklist basado en el procedimiento
      const items: CheckItem[] = [
        // Documentos base (todos)
        { id: '1', texto: 'Dictamen técnico de la obra', categoria: 'Planeación', obligatorio: true, completado: false },
        { id: '2', texto: 'Especificaciones técnicas completas', categoria: 'Planeación', obligatorio: true, completado: false },
        { id: '3', texto: 'Presupuesto base con APU desglosados', categoria: 'Planeación', obligatorio: true, completado: false },
        { id: '4', texto: 'Programa de obra (CPM/Gantt)', categoria: 'Planeación', obligatorio: true, completado: false },
        { id: '5', texto: 'Análisis de riesgos', categoria: 'Planeación', obligatorio: false, completado: false },
      ];

      if (proc !== 'adjudicacion_directa') {
        items.push(
          { id: '6', texto: 'Publicación de convocatoria en CompraNet', categoria: 'Convocatoria', obligatorio: true, completado: false },
          { id: '7', texto: 'Bases de licitación aprobadas', categoria: 'Convocatoria', obligatorio: true, completado: false },
          { id: '8', texto: 'Junta de aclaraciones (si aplica)', categoria: 'Convocatoria', obligatorio: false, completado: false },
          { id: '9', texto: 'Recepción de proposiciones (sobre cerrado)', categoria: 'Proposiciones', obligatorio: true, completado: false },
          { id: '10', texto: 'Garantía de seriedad de proposición (5%)', categoria: 'Proposiciones', obligatorio: true, completado: false },
          { id: '11', texto: 'Evaluación técnica de proposiciones', categoria: 'Evaluación', obligatorio: true, completado: false },
          { id: '12', texto: 'Evaluación económica de proposiciones', categoria: 'Evaluación', obligatorio: true, completado: false },
          { id: '13', texto: 'Dictamen de la comisión de evaluación', categoria: 'Evaluación', obligatorio: true, completado: false },
        );
      }

      if (proc === 'licitacion_publica') {
        items.push(
          { id: '14', texto: 'Publicación en DOF (si aplica)', categoria: 'Convocatoria', obligatorio: true, completado: false },
          { id: '15', texto: 'Mínimo 3 licitantes participantes', categoria: 'Proposiciones', obligatorio: true, completado: false },
          { id: '16', texto: 'Acta de apertura de proposiciones', categoria: 'Proposiciones', obligatorio: true, completado: false },
        );
      }

      items.push(
        { id: '17', texto: 'Acta de fallo firmada', categoria: 'Fallo', obligatorio: true, completado: false },
        { id: '18', texto: 'Notificación al ganador', categoria: 'Fallo', obligatorio: true, completado: false },
        { id: '19', texto: 'Notificación a no ganadores', categoria: 'Fallo', obligatorio: true, completado: false },
        { id: '20', texto: 'Contrato de precios unitarios firmado', categoria: 'Contrato', obligatorio: true, completado: false },
        { id: '21', texto: 'Garantía de cumplimiento (10%)', categoria: 'Contrato', obligatorio: true, completado: false },
        { id: '22', texto: 'Garantía de vicios ocultos (5%)', categoria: 'Contrato', obligatorio: true, completado: false },
        { id: '23', texto: 'Anexo técnico del contrato', categoria: 'Contrato', obligatorio: true, completado: false },
        { id: '24', texto: 'Programa de obra detallado', categoria: 'Contrato', obligatorio: true, completado: false },
      );

      setChecklist(items);
      setProgreso(0);
    } catch (e) {
      console.error(e);
    } finally {
      setCargando(false);
    }
  };

  const toggleItem = (id: string) => {
    setChecklist(prev => {
      const updated = prev.map(item => 
        item.id === id ? { ...item, completado: !item.completado } : item
      );
      const completados = updated.filter(i => i.completado).length;
      setProgreso(Math.round((completados / updated.length) * 100));
      return updated;
    });
  };

  const categorias = [...new Set(checklist.map(i => i.categoria))];

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-2 mb-4">
        <ListChecks className="w-4 h-4 text-emerald-400" />
        <h3 className="text-sm font-semibold text-zinc-200">Checklist del Proceso</h3>
      </div>

      <div className="flex gap-2 mb-2">
        <input
          type="number"
          value={monto}
          onChange={(e) => setMonto(e.target.value)}
          placeholder="Monto estimado ($)"
          className="flex-1 bg-zinc-800/60 border border-zinc-700 rounded-lg px-3 py-2 text-sm 
                   text-zinc-200 placeholder-zinc-600 focus:outline-hidden focus:border-emerald-500/40"
        />
        <button
          onClick={generar}
          disabled={cargando || !monto.trim()}
          className="px-3 py-2 rounded-lg bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 
                   hover:bg-emerald-500/25 transition-colors disabled:opacity-30"
        >
          <RefreshCw className={`w-4 h-4 ${cargando ? 'animate-spin' : ''}`} />
        </button>
      </div>
      <input
        type="number"
        value={presupuestoDependenciaMiles}
        onChange={(e) => setPresupuestoDependenciaMiles(e.target.value)}
        placeholder="Presupuesto autorizado de la dependencia (miles $)"
        title="El Anexo 9 del PEF es una tabla escalonada por este dato, no por el monto del contrato aislado."
        className="w-full mb-4 bg-zinc-800/60 border border-zinc-700 rounded-lg px-3 py-2 text-sm 
                 text-zinc-200 placeholder-zinc-600 focus:outline-hidden focus:border-emerald-500/40"
      />

      {procedimiento && (
        <div className="mb-3 p-2 rounded-lg bg-emerald-500/5 border border-emerald-500/15">
          <p className="text-[10px] text-emerald-400 uppercase tracking-wider">Procedimiento</p>
          <p className="text-sm font-bold text-zinc-100">{procedimiento}</p>
        </div>
      )}

      {advertencia && (
        <div className="mb-3 flex items-start gap-2 p-2 rounded-lg bg-amber-500/5 border border-amber-500/15">
          <AlertTriangle className="w-3 h-3 text-amber-400 mt-0.5 shrink-0" />
          <p className="text-[11px] text-amber-300">{advertencia}</p>
        </div>
      )}

      {checklist.length > 0 && (
        <>
          {/* Barra de progreso */}
          <div className="mb-3">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] text-zinc-500">Progreso</span>
              <span className="text-[10px] text-emerald-400 font-bold">{progreso}%</span>
            </div>
            <div className="w-full h-1.5 bg-zinc-800 rounded-full overflow-hidden">
              <motion.div
                className="h-full bg-emerald-500 rounded-full"
                initial={{ width: 0 }}
                animate={{ width: `${progreso}%` }}
                transition={{ duration: 0.3 }}
              />
            </div>
          </div>

          {/* Checklist por categoría */}
          <div className="space-y-3 overflow-auto flex-1">
            {categorias.map(cat => (
              <div key={cat}>
                <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1.5">{cat}</p>
                <div className="space-y-1">
                  {checklist.filter(i => i.categoria === cat).map(item => (
                    <button
                      key={item.id}
                      onClick={() => toggleItem(item.id)}
                      className={`w-full flex items-start gap-2.5 p-2 rounded-lg text-left transition-all ${
                        item.completado 
                          ? 'bg-emerald-500/5 border border-emerald-500/15' 
                          : 'bg-zinc-800/30 border border-zinc-700/30 hover:bg-zinc-800/50'
                      }`}
                    >
                      {item.completado ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                      ) : (
                        <Circle className="w-4 h-4 text-zinc-600 shrink-0 mt-0.5" />
                      )}
                      <div className="flex-1">
                        <p className={`text-[11px] leading-relaxed ${item.completado ? 'text-zinc-500 line-through' : 'text-zinc-300'}`}>
                          {item.texto}
                        </p>
                        {item.obligatorio && !item.completado && (
                          <span className="text-[9px] text-rose-400 mt-0.5 block">Obligatorio</span>
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
