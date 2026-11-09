import { useEffect, useState } from 'react';
import { megalodonClient } from '@/lib/api-client';
import type { ConceptoLibro } from '@/lib/megalodon-client';

export function CatalogoLibroPicker({ onSelect }: { onSelect: (item: ConceptoLibro, quantity: number) => void }) {
  const [query, setQuery] = useState('');
  const [skip, setSkip] = useState(0);
  const [items, setItems] = useState<ConceptoLibro[]>([]);
  const [total, setTotal] = useState(0);
  const [quantity, setQuantity] = useState(1);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setItems([]);
    const timer = setTimeout(() => {
      megalodonClient.catalogoLibro.buscar(query, skip).then(result => {
        if (active) { setItems(result.items); setTotal(result.total); setError(''); }
      }).catch(e => { if (active) setError(e instanceof Error ? e.message : 'No se pudo cargar el catálogo'); })
        .finally(() => { if (active) setLoading(false); });
    }, 250);
    return () => { active = false; clearTimeout(timer); };
  }, [query, skip]);
  return <div className="p-3 border-b border-[#2A2A3E] space-y-2 text-xs text-[#E8E4DC]">
    <p>Precios del CSV · comprueba página, modelo y supuesto antes de seleccionar. Los importes originales se conservan como referencia; no se infieren precios ni desgloses.</p>
    <div className="flex gap-2">
      <input aria-label="Buscar en catálogo del libro" placeholder="Buscar en el libro…" value={query}
        onChange={e => { setQuery(e.target.value); setSkip(0); }} className="flex-1 bg-[#12121A] p-2 rounded" />
      <label>Cantidad de tu obra <input aria-label="Cantidad de tu obra" type="number" min="0.0001" step="0.0001" value={quantity}
        onChange={e => setQuantity(Number(e.target.value))} className="w-24 bg-[#12121A] p-2 rounded" /></label>
    </div>
    {error && <p role="alert" className="text-red-400">{error}</p>}
    {loading ? <p>Cargando catálogo…</p> : <div className="max-h-64 overflow-y-auto space-y-1">
      {items.map(item => <div key={item.id} className="flex items-center gap-3 p-2 bg-[#12121A] rounded">
        <div className="flex-1"><div>{item.descripcion}</div>
          <div className="text-[#8A8578]">Modelo {item.modelo_id} · página {item.pagina} · {item.precio_unitario ?? 'Sin precio'} / {item.unidad}{item.supuesto ? ` · ${item.supuesto}` : ''}</div>
          {item.bloqueo && <div className="text-amber-400">{item.bloqueo}</div>}
        </div>
        <button disabled={!item.utilizable || !Number.isFinite(quantity) || quantity <= 0}
          onClick={() => onSelect(item, quantity)} className="p-2 text-[#C9A84C] disabled:opacity-30">Agregar</button>
      </div>)}
      {!items.length && !error && <p>Sin resultados.</p>}
    </div>}
    <div className="flex gap-3 items-center">
      <button disabled={skip === 0 || loading} onClick={() => setSkip(Math.max(0, skip - 50))}>Anterior</button>
      <span>{total ? skip + 1 : 0}–{Math.min(skip + items.length, total)} de {total}</span>
      <button disabled={skip + 50 >= total || loading} onClick={() => setSkip(skip + 50)}>Siguiente</button>
    </div>
  </div>;
}
