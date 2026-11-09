/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

/**
 * Megalodon Transparencia - Portal de Consulta Pública
 * App de escritorio para consulta de datos abiertos y transparencia
 */
import { useState, useEffect, useCallback } from 'react';
import { Search, FileText, Download, Eye, Calendar, DollarSign, Building2 } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';

interface ExpedientePublico {
  id: string;
  identificador: string;
  titulo: string;
  estado: string;
  monto_contrato?: number;
  organo: string;
  created_at: string;
}

interface FiltrosBusqueda {
  query: string;
  estado: string;
  fechaInicio: string;
  fechaFin: string;
  montoMin: string;
  montoMax: string;
}

export default function TransparenciaApp() {
  const [expedientes, setExpedientes] = useState<ExpedientePublico[]>([]);
  const [loading, setLoading] = useState(false);
  const [filtros, setFiltros] = useState<FiltrosBusqueda>({
    query: '',
    estado: '',
    fechaInicio: '',
    fechaFin: '',
    montoMin: '',
    montoMax: '',
  });
  const [expedienteSeleccionado, setExpedienteSeleccionado] = useState<ExpedientePublico | null>(null);
  const [totalResultados, setTotalResultados] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const buscarExpedientes = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data: any = await megalodonClient.transparencia.expedientesPublicos({
        q: filtros.query || undefined,
        estado: filtros.estado || undefined,
        skip: 0,
        limit: 100,
      });
      setExpedientes(data.resultados || []);
      setTotalResultados(data.total ?? (data.resultados || []).length);
    } catch (e: any) {
      // NO hay fallback a datos demo: si el backend no responde, se
      // muestra el error (mismo principio que compliance-dashboard).
      console.error('Error buscando expedientes:', e);
      setError(e.message || 'Error de conexión con el backend');
      setExpedientes([]);
      setTotalResultados(0);
    } finally {
      setLoading(false);
    }
  }, [filtros]);

  useEffect(() => {
    buscarExpedientes();
  }, [buscarExpedientes]);

  const formatCurrency = (amount?: number) => {
    if (!amount) return '$0.00';
    return new Intl.NumberFormat('es-MX', {
      style: 'currency',
      currency: 'MXN',
      minimumFractionDigits: 2,
    }).format(amount);
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('es-MX', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  };

  const getEstadoColor = (estado: string) => {
    const colores: Record<string, string> = {
      BORRADOR: 'bg-gray-500/20 text-gray-400',
      EN_REVISION: 'bg-yellow-500/20 text-yellow-400',
      APROBADO: 'bg-blue-500/20 text-blue-400',
      EN_EJECUCION: 'bg-green-500/20 text-green-400',
      FINALIZADO: 'bg-emerald-500/20 text-emerald-400',
      SUSPENDIDO: 'bg-orange-500/20 text-orange-400',
      CANCELADO: 'bg-red-500/20 text-red-400',
      ARCHIVADO: 'bg-slate-500/20 text-slate-400',
    };
    return colores[estado] || 'bg-gray-500/20 text-gray-400';
  };

  return (
    <div className="w-full h-full bg-[#0A0A0F] text-[#E8E4DC] flex flex-col">
      {/* Header */}
      <div className="px-6 py-4 border-b border-[#C9A84C]/20 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Eye className="w-5 h-5 text-[#C9A84C]" />
          <h1 className="text-lg font-semibold text-[#C9A84C]">Portal de Transparencia</h1>
        </div>
        <div className="text-sm text-[#8A8578]">
          {totalResultados} expedientes públicos
        </div>
      </div>

      {/* Filtros */}
      <div className="px-6 py-3 border-b border-[#C9A84C]/10 bg-[#12121A]/50">
        <div className="flex gap-3 items-center flex-wrap">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#8A8578]" />
            <input
              type="text"
              placeholder="Buscar expedientes..."
              value={filtros.query}
              onChange={(e) => setFiltros({ ...filtros, query: e.target.value })}
              className="w-full pl-10 pr-4 py-2 bg-[#1A1A24] border border-[#C9A84C]/20 rounded-lg text-sm text-[#E8E4DC] placeholder-[#8A8578] focus:outline-hidden focus:border-[#C9A84C]/50"
            />
          </div>
          <select
            value={filtros.estado}
            onChange={(e) => setFiltros({ ...filtros, estado: e.target.value })}
            className="px-3 py-2 bg-[#1A1A24] border border-[#C9A84C]/20 rounded-lg text-sm text-[#E8E4DC] focus:outline-hidden focus:border-[#C9A84C]/50"
          >
            <option value="">Todos los estados</option>
            <option value="BORRADOR">Borrador</option>
            <option value="EN_REVISION">En Revisión</option>
            <option value="APROBADO">Aprobado</option>
            <option value="EN_EJECUCION">En Ejecución</option>
            <option value="FINALIZADO">Finalizado</option>
            <option value="SUSPENDIDO">Suspendido</option>
            <option value="CANCELADO">Cancelado</option>
          </select>
          <button
            onClick={buscarExpedientes}
            disabled={loading}
            className="px-4 py-2 bg-[#C9A84C]/20 hover:bg-[#C9A84C]/30 border border-[#C9A84C]/30 rounded-lg text-sm text-[#C9A84C] transition-colors disabled:opacity-50"
          >
            {loading ? 'Buscando...' : 'Buscar'}
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Lista */}
        <div className="flex-1 overflow-y-auto p-4">
          {error && (
            <div className="mb-3 p-3 rounded-lg border border-red-300 bg-red-50 text-sm text-red-700">
              {error}
            </div>
          )}
          <div className="space-y-3">
            {expedientes.map((exp) => (
              <div
                key={exp.id}
                onClick={() => setExpedienteSeleccionado(exp)}
                className={`p-4 rounded-lg border cursor-pointer transition-all ${
                  expedienteSeleccionado?.id === exp.id
                    ? 'border-[#C9A84C]/50 bg-[#C9A84C]/10'
                    : 'border-[#C9A84C]/10 bg-[#12121A]/50 hover:border-[#C9A84C]/30'
                }`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <FileText className="w-4 h-4 text-[#8A8578]" />
                      <span className="text-xs text-[#8A8578] font-mono">{exp.identificador}</span>
                      <span className={`px-2 py-0.5 rounded-full text-xs ${getEstadoColor(exp.estado)}`}>
                        {exp.estado.replace('_', ' ')}
                      </span>
                    </div>
                    <h3 className="text-sm font-medium text-[#E8E4DC] mb-1">{exp.titulo}</h3>
                    <div className="flex items-center gap-4 text-xs text-[#8A8578]">
                      <span className="flex items-center gap-1">
                        <Building2 className="w-3 h-3" />
                        {exp.organo}
                      </span>
                      <span className="flex items-center gap-1">
                        <Calendar className="w-3 h-3" />
                        {formatDate(exp.created_at)}
                      </span>
                      <span className="flex items-center gap-1">
                        <DollarSign className="w-3 h-3" />
                        {formatCurrency(exp.monto_contrato)}
                      </span>
                    </div>
                  </div>
                  <button className="p-2 hover:bg-[#C9A84C]/10 rounded-lg transition-colors">
                    <Eye className="w-4 h-4 text-[#8A8578]" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Detail Panel */}
        {expedienteSeleccionado && (
          <div className="w-80 border-l border-[#C9A84C]/20 bg-[#12121A]/30 p-4 overflow-y-auto">
            <h2 className="text-sm font-semibold text-[#C9A84C] mb-4">Detalle del Expediente</h2>
            <div className="space-y-4">
              <div>
                <label className="text-xs text-[#8A8578] block mb-1">Identificador</label>
                <p className="text-sm font-mono text-[#E8E4DC]">{expedienteSeleccionado.identificador}</p>
              </div>
              <div>
                <label className="text-xs text-[#8A8578] block mb-1">Título</label>
                <p className="text-sm text-[#E8E4DC]">{expedienteSeleccionado.titulo}</p>
              </div>
              <div>
                <label className="text-xs text-[#8A8578] block mb-1">Estado</label>
                <span className={`inline-block px-2 py-1 rounded-full text-xs ${getEstadoColor(expedienteSeleccionado.estado)}`}>
                  {expedienteSeleccionado.estado.replace('_', ' ')}
                </span>
              </div>
              <div>
                <label className="text-xs text-[#8A8578] block mb-1">Órgano</label>
                <p className="text-sm text-[#E8E4DC]">{expedienteSeleccionado.organo}</p>
              </div>
              <div>
                <label className="text-xs text-[#8A8578] block mb-1">Monto del Contrato</label>
                <p className="text-lg font-semibold text-[#C9A84C]">
                  {formatCurrency(expedienteSeleccionado.monto_contrato)}
                </p>
              </div>
              <div>
                <label className="text-xs text-[#8A8578] block mb-1">Fecha de Creación</label>
                <p className="text-sm text-[#E8E4DC]">{formatDate(expedienteSeleccionado.created_at)}</p>
              </div>
              <div className="pt-4 border-t border-[#C9A84C]/10">
                <button className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-[#C9A84C]/20 hover:bg-[#C9A84C]/30 border border-[#C9A84C]/30 rounded-lg text-sm text-[#C9A84C] transition-colors">
                  <Download className="w-4 h-4" />
                  Descargar Información
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
