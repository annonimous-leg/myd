/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

/**
 * Megalodon Search - Búsqueda Global y Semántica
 * Búsqueda across todos los dominios del sistema
 */
import { useState, useEffect, useCallback } from 'react';
import { Search, FileText, Folder, Calculator, Gavel, Award, Filter, X } from 'lucide-react';
import { megalodonClient } from '../../lib/api-client';

interface SearchResult {
  id: string;
  titulo: string;
  descripcion?: string;
  tipo: string;
  estado?: string;
  dominio: string;
  created_at?: string;
  relevancia: number;
}

export default function SearchApp() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedDominios, setSelectedDominios] = useState<string[]>(['documentos', 'expedientes', 'presupuestos', 'contratos', 'licitaciones']);
  const [showFilters, setShowFilters] = useState(false);
  const [totalPorDominio, setTotalPorDominio] = useState<Record<string, number>>({});

  const buscar = useCallback(async () => {
    if (!query.trim()) {
      setResults([]);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const data: any = await megalodonClient.search.global(query, { dominios: selectedDominios });
      setResults(data.resultados || []);
      setTotalPorDominio(data.total_por_dominio || {});
    } catch (e: any) {
      // NO hay fallback a datos demo: si el backend no responde, se
      // muestra el error (mismo principio que compliance-dashboard).
      console.error('Error en búsqueda:', e);
      setError(e.message || 'Error de conexión con el backend');
      setResults([]);
      setTotalPorDominio({});
    } finally {
      setLoading(false);
    }
  }, [query, selectedDominios]);

  useEffect(() => {
    const timeout = setTimeout(() => {
      if (query.trim()) buscar();
    }, 300);
    return () => clearTimeout(timeout);
  }, [query, buscar]);

  const toggleDominio = (dominio: string) => {
    setSelectedDominios(prev =>
      prev.includes(dominio)
        ? prev.filter(d => d !== dominio)
        : [...prev, dominio]
    );
  };

  const getDominioIcon = (dominio: string) => {
    switch (dominio) {
      case 'documentos': return <FileText className="w-4 h-4" />;
      case 'expedientes': return <Folder className="w-4 h-4" />;
      case 'presupuestos': return <Calculator className="w-4 h-4" />;
      case 'contratos': return <Gavel className="w-4 h-4" />;
      case 'licitaciones': return <Award className="w-4 h-4" />;
      default: return <Search className="w-4 h-4" />;
    }
  };

  const getDominioColor = (dominio: string) => {
    const colores: Record<string, string> = {
      documentos: 'text-blue-400',
      expedientes: 'text-green-400',
      presupuestos: 'text-yellow-400',
      contratos: 'text-purple-400',
      licitaciones: 'text-orange-400',
    };
    return colores[dominio] || 'text-gray-400';
  };

  return (
    <div className="w-full h-full bg-[#0A0A0F] text-[#E8E4DC] flex flex-col">
      {/* Header */}
      <div className="px-6 py-4 border-b border-[#C9A84C]/20">
        <div className="flex items-center gap-3 mb-4">
          <Search className="w-5 h-5 text-[#C9A84C]" />
          <h1 className="text-lg font-semibold text-[#C9A84C]">Búsqueda Global</h1>
        </div>
        <div className="flex gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#8A8578]" />
            <input
              type="text"
              placeholder="Buscar en documentos, expedientes, presupuestos, contratos..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2.5 bg-[#1A1A24] border border-[#C9A84C]/20 rounded-lg text-sm text-[#E8E4DC] placeholder-[#8A8578] focus:outline-hidden focus:border-[#C9A84C]/50"
            />
            {query && (
              <button
                onClick={() => setQuery('')}
                className="absolute right-3 top-1/2 -translate-y-1/2"
              >
                <X className="w-4 h-4 text-[#8A8578] hover:text-[#E8E4DC]" />
              </button>
            )}
          </div>
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`px-4 py-2.5 border rounded-lg text-sm transition-colors ${
              showFilters
                ? 'bg-[#C9A84C]/20 border-[#C9A84C]/50 text-[#C9A84C]'
                : 'bg-[#1A1A24] border-[#C9A84C]/20 text-[#8A8578] hover:text-[#E8E4DC]'
            }`}
          >
            <Filter className="w-4 h-4" />
          </button>
        </div>

        {/* Filters */}
        {showFilters && (
          <div className="mt-3 flex flex-wrap gap-2">
            {['documentos', 'expedientes', 'presupuestos', 'contratos', 'licitaciones'].map((dominio) => (
              <button
                key={dominio}
                onClick={() => toggleDominio(dominio)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs transition-colors ${
                  selectedDominios.includes(dominio)
                    ? 'bg-[#C9A84C]/20 text-[#C9A84C] border border-[#C9A84C]/30'
                    : 'bg-[#1A1A24] text-[#8A8578] border border-[#C9A84C]/10'
                }`}
              >
                {getDominioIcon(dominio)}
                {dominio.charAt(0).toUpperCase() + dominio.slice(1)}
                {totalPorDominio[dominio] !== undefined && (
                  <span className="ml-1 px-1.5 py-0.5 bg-[#0A0A0F] rounded-full text-[10px]">
                    {totalPorDominio[dominio]}
                  </span>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Results */}
      <div className="flex-1 overflow-y-auto p-6">
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <div className="w-8 h-8 border-2 border-[#C9A84C]/30 border-t-[#C9A84C] rounded-full animate-spin" />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-full text-center gap-2">
            <p className="text-sm text-red-400">{error}</p>
            <p className="text-xs text-[#8A8578]">No se pudo consultar el backend. Intenta de nuevo.</p>
          </div>
        ) : results.length > 0 ? (
          <div className="space-y-3">
            {results.map((result) => (
              <div
                key={result.id}
                className="p-4 rounded-lg border border-[#C9A84C]/10 bg-[#12121A]/50 hover:border-[#C9A84C]/30 transition-colors cursor-pointer"
              >
                <div className="flex items-start gap-3">
                  <div className={`mt-0.5 ${getDominioColor(result.dominio)}`}>
                    {getDominioIcon(result.dominio)}
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-medium text-[#E8E4DC]">{result.titulo}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full bg-[#1A1A24] ${getDominioColor(result.dominio)}`}>
                        {result.dominio}
                      </span>
                      {result.estado && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-[#1A1A24] text-[#8A8578]">
                          {result.estado}
                        </span>
                      )}
                    </div>
                    {result.descripcion && (
                      <p className="text-xs text-[#8A8578] mb-1">{result.descripcion}</p>
                    )}
                    <div className="flex items-center gap-3 text-xs text-[#8A8578]">
                      {result.created_at && (
                        <span>{new Date(result.created_at).toLocaleDateString('es-MX')}</span>
                      )}
                      <span>Relevancia: {(result.relevancia * 100).toFixed(0)}%</span>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : query ? (
          <div className="flex flex-col items-center justify-center h-full text-[#8A8578]">
            <Search className="w-12 h-12 mb-4 opacity-30" />
            <p className="text-sm">No se encontraron resultados para "{query}"</p>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-[#8A8578]">
            <Search className="w-12 h-12 mb-4 opacity-30" />
            <p className="text-sm">Escribe para buscar en todos los dominios</p>
          </div>
        )}
      </div>
    </div>
  );
}
