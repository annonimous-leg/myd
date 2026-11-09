/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

/**
 * Megalodon Consistency Engine — Backend real obligatorio
 * Valida consistencia cross-domain: BIM = Costos = Programación = Expediente
 */
import { useState, useEffect, useCallback } from 'react';
import { CheckCircle, XCircle, AlertTriangle, Link2, RefreshCw, FolderKanban } from 'lucide-react';
import { megalodonClient } from '../../lib/api-client';
import { useExpedienteStore } from '../../stores/useExpedienteStore';

interface ConsistencyCheck {
  id: string;
  dominioA: string;
  dominioB: string;
  estado: 'CONSISTENTE' | 'INCONSISTENTE' | 'WARNING';
  descripcion: string;
  ultimaVerificacion: string;
}

export default function ConsistencyEngineApp() {
  const [checks, setChecks] = useState<ConsistencyCheck[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState('');

  // BUG ORIGINAL: este componente no recibe props (WindowManager monta
  // cada app sin argumentos), así que "sobre qué expediente estoy
  // verificando consistencia" no podía venir de ningún lado -- llamaba a
  // /expedientes-advanced/resumen-completo sin el {expediente_id} que el
  // backend exige (404 garantizado), además del token roto. Se usa la
  // misma fuente de verdad que ya existe para esto (useExpedienteStore,
  // poblada por la app Proyectos).
  const { expedienteActivoId, expedienteActivo, expedientes, cargarExpedientes } = useExpedienteStore();

  const fetchConsistency = useCallback(async () => {
    if (!expedienteActivoId) {
      setChecks([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data: any = await megalodonClient.expedientesAdvanced.resumenCompleto(expedienteActivoId);

      const generatedChecks: ConsistencyCheck[] = [];

      if (data.bim && data.presupuesto) {
        generatedChecks.push({
          id: '1',
          dominioA: 'BIM',
          dominioB: 'Costos',
          estado: data.bim.volumen_total === data.presupuesto.volumen_total ? 'CONSISTENTE' : 'INCONSISTENTE',
          descripcion: `Volumen BIM: ${data.bim.volumen_total} vs Presupuesto: ${data.presupuesto.volumen_total}`,
          ultimaVerificacion: new Date().toISOString(),
        });
      }
      if (data.presupuesto && data.programacion) {
        generatedChecks.push({
          id: '2',
          dominioA: 'Costos',
          dominioB: 'Programación',
          estado: data.presupuesto.monto_total === data.programacion.monto_programado ? 'CONSISTENTE' : 'WARNING',
          descripcion: `Presupuesto: $${data.presupuesto.monto_total} vs Programado: $${data.programacion.monto_programado}`,
          ultimaVerificacion: new Date().toISOString(),
        });
      }
      if (data.expediente && data.contrato) {
        generatedChecks.push({
          id: '3',
          dominioA: 'Expediente',
          dominioB: 'Contrato',
          estado: data.expediente.estado === data.contrato.estado ? 'CONSISTENTE' : 'WARNING',
          descripcion: `Estado expediente: ${data.expediente.estado} vs Contrato: ${data.contrato.estado}`,
          ultimaVerificacion: new Date().toISOString(),
        });
      }

      setChecks(generatedChecks);
      setLastUpdate(new Date().toLocaleString('es-MX'));
    } catch (e: any) {
      setError(e.message || 'Error de conexión');
      setChecks([]);
    } finally {
      setLoading(false);
    }
  }, [expedienteActivoId]);

  useEffect(() => {
    if (expedientes.length === 0) cargarExpedientes();
  }, [expedientes.length, cargarExpedientes]);

  useEffect(() => {
    fetchConsistency();
  }, [fetchConsistency]);

  if (!expedienteActivoId) {
    return (
      <div className="p-8 text-center text-gray-500 flex flex-col items-center gap-3">
        <FolderKanban className="w-8 h-8 text-gray-400" />
        <p>Selecciona un expediente activo en <strong>Proyectos</strong> para verificar su consistencia cross-domain.</p>
      </div>
    );
  }

  if (loading) return <div className="p-8 text-center">Verificando consistencia...</div>;
  if (error) return (
    <div className="p-8 text-center text-red-600">
      <AlertTriangle className="mx-auto mb-2" />
      <p>{error}</p>
      <button onClick={fetchConsistency} className="mt-4 px-4 py-2 bg-blue-600 text-white rounded">
        Reintentar
      </button>
    </div>
  );

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Link2 className="w-6 h-6" />
            Consistency Engine
          </h1>
          <p className="text-sm text-gray-500">{expedienteActivo()?.titulo || expedienteActivoId}</p>
        </div>
        <button onClick={fetchConsistency} className="p-2 hover:bg-gray-100 rounded">
          <RefreshCw className="w-5 h-5" />
        </button>
      </div>

      <div className="space-y-3">
        {checks.length === 0 && <p className="text-gray-500">No hay datos suficientes para verificar consistencia</p>}
        {checks.map(c => (
          <div key={c.id} className={`p-4 border rounded flex items-center gap-3 ${
            c.estado === 'CONSISTENTE' ? 'border-green-200 bg-green-50' :
            c.estado === 'WARNING' ? 'border-yellow-200 bg-yellow-50' : 'border-red-200 bg-red-50'
          }`}>
            {c.estado === 'CONSISTENTE' ? <CheckCircle className="text-green-600 w-5 h-5" /> :
             c.estado === 'WARNING' ? <AlertTriangle className="text-yellow-600 w-5 h-5" /> :
             <XCircle className="text-red-600 w-5 h-5" />}
            <div className="flex-1">
              <p className="font-medium">{c.dominioA} ↔ {c.dominioB}</p>
              <p className="text-sm text-gray-600">{c.descripcion}</p>
            </div>
            <span className="text-xs text-gray-400">{c.ultimaVerificacion}</span>
          </div>
        ))}
      </div>

      {lastUpdate && <p className="text-xs text-gray-400 mt-4">Última verificación: {lastUpdate}</p>}
    </div>
  );
}
