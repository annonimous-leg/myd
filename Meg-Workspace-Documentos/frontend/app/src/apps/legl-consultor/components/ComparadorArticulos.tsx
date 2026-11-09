/**
 * Comparador de Artículos entre LOPSRM y LAASSP
 */
import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { GitCompare, Search, BookOpen, ArrowRightLeft } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';

interface ArticuloData {
  ley: string;
  ley_nombre: string;
  articulo: string;
  titulo: string;
  contenido: string;
  fase: string;
}

export default function ComparadorArticulos() {
  const [numero, setNumero] = useState('');
  const [cargando, setCargando] = useState(false);
  const [resultados, setResultados] = useState<ArticuloData[]>([]);
  const [historial, setHistorial] = useState<string[]>(['40', '42', '52', '55']);

  const comparar = async () => {
    if (!numero.trim()) return;
    setCargando(true);
    try {
      const [lopsrm, laassp] = await Promise.all([
        megalodonClient.legal.obtenerArticulo('lopsrm', numero).catch(() => null),
        megalodonClient.legal.obtenerArticulo('laassp', numero).catch(() => null),
      ]);
      const res = [lopsrm, laassp].filter(Boolean) as ArticuloData[];
      setResultados(res);
      if (!historial.includes(numero)) {
        setHistorial(prev => [numero, ...prev].slice(0, 8));
      }
    } catch (e) {
      console.error(e);
    } finally {
      setCargando(false);
    }
  };

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-2 mb-4">
        <GitCompare className="w-4 h-4 text-amber-400" />
        <h3 className="text-sm font-semibold text-zinc-200">Comparador de Artículos</h3>
      </div>

      <div className="flex gap-2 mb-4">
        <input
          type="text"
          value={numero}
          onChange={(e) => setNumero(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && comparar()}
          placeholder="Número de artículo (ej: 40)"
          className="flex-1 bg-zinc-800/60 border border-zinc-700 rounded-lg px-3 py-2 text-sm 
                   text-zinc-200 placeholder-zinc-600 focus:outline-hidden focus:border-amber-500/40"
        />
        <button
          onClick={comparar}
          disabled={cargando || !numero.trim()}
          className="px-3 py-2 rounded-lg bg-amber-500/15 border border-amber-500/30 text-amber-400 
                   hover:bg-amber-500/25 transition-colors disabled:opacity-30"
        >
          <Search className="w-4 h-4" />
        </button>
      </div>

      {/* Historial rápido */}
      <div className="flex flex-wrap gap-1.5 mb-4">
        {historial.map((h) => (
          <button
            key={h}
            onClick={() => { setNumero(h); comparar(); }}
            className="text-[10px] px-2 py-1 rounded-full bg-zinc-800/50 border border-zinc-700/50 
                     text-zinc-500 hover:text-zinc-300 hover:border-zinc-600 transition-colors"
          >
            Art. {h}
          </button>
        ))}
      </div>

      <AnimatePresence>
        {resultados.length > 0 && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="space-y-3 overflow-auto"
          >
            {resultados.map((art) => (
              <div
                key={art.ley}
                className={`p-3 rounded-xl border ${
                  art.ley === 'lopsrm' 
                    ? 'bg-blue-500/5 border-blue-500/20' 
                    : 'bg-emerald-500/5 border-emerald-500/20'
                }`}
              >
                <div className="flex items-center gap-2 mb-1.5">
                  <BookOpen className={`w-3.5 h-3.5 ${art.ley === 'lopsrm' ? 'text-blue-400' : 'text-emerald-400'}`} />
                  <span className={`text-[10px] font-bold uppercase tracking-wider ${art.ley === 'lopsrm' ? 'text-blue-400' : 'text-emerald-400'}`}>
                    {art.ley_nombre}
                  </span>
                  <span className="text-[10px] text-zinc-600 ml-auto">{art.fase}</span>
                </div>
                <p className="text-xs font-semibold text-zinc-200 mb-1">Art. {art.articulo} — {art.titulo}</p>
                <p className="text-[11px] text-zinc-400 leading-relaxed">{art.contenido}</p>
              </div>
            ))}

            {/* Diferencias destacadas */}
            {resultados.length === 2 && (
              <div className="p-3 rounded-xl bg-zinc-800/30 border border-zinc-700/50">
                <div className="flex items-center gap-2 mb-2">
                  <ArrowRightLeft className="w-3.5 h-3.5 text-amber-400" />
                  <span className="text-[10px] font-semibold text-amber-400 uppercase tracking-wider">Análisis Comparativo</span>
                </div>
                <p className="text-[11px] text-zinc-400 leading-relaxed">
                  Ambas leyes regulan el mismo artículo {numero} pero con enfoques diferentes: 
                  <span className="text-blue-400"> LOPSRM</span> se centra en obras públicas y servicios relacionados, 
                  mientras que <span className="text-emerald-400">LAASSP</span> abarca adquisiciones, arrendamientos y servicios del sector público en general.
                </p>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {cargando && (
        <div className="flex items-center justify-center py-8">
          <div className="animate-spin w-5 h-5 border-2 border-amber-500 border-t-transparent rounded-full" />
        </div>
      )}
    </div>
  );
}
