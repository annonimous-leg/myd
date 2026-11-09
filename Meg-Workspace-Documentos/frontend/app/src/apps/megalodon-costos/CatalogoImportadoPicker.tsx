import { useEffect, useState } from 'react';
import { megalodonClient } from '@/lib/api-client';
import type { CatalogoAPUOut } from '@/lib/megalodon-client';

export function CatalogoImportadoPicker({ onSelect }: {onSelect: (item: CatalogoAPUOut, cantidad: number) => void}) {
  const [q, setQ] = useState('');
  const [items, setItems] = useState<CatalogoAPUOut[]>([]);
  const [selected, setSelected] = useState('');
  const [quantity, setQuantity] = useState('1');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    setSelected(''); setItems([]); setLoading(true); setError('');
    const timer = setTimeout(() => {
      void megalodonClient.catalogoAPU.listar({q, tipo: 'CONCEPTO', limit: 100}).then(data => {
        if (active) setItems((data as {items: CatalogoAPUOut[]}).items.filter(item => item.origen && !item.incluye_iva));
      }).catch(e => { if (active) setError(e instanceof Error ? e.message : 'No se pudo buscar el catálogo'); })
        .finally(() => { if (active) setLoading(false); });
    }, 250);
    return () => { active = false; clearTimeout(timer); };
  }, [q]);
  const item = items.find(item => item.id === selected);
  const validQuantity = /^\d+(?:\.\d{1,4})?$/.test(quantity) && Number(quantity) > 0;
  return <section className="p-3 space-y-2 bg-[#1A1A26] text-xs" aria-label="Seleccionar precio de catálogo importado">
    <p>Selecciona un concepto y captura la cantidad medida. El precio y el APU se confirman desde su edición al guardar.</p>
    <label>Buscar en catálogos importados
      <input className="block w-full p-2 rounded bg-[#12121A]" value={q} onChange={e => setQ(e.target.value)} placeholder="Clave, descripción o fuente" />
    </label>
    <label>Concepto importado
      <select aria-label="Concepto importado" className="block w-full p-2 rounded bg-[#12121A]" value={selected} disabled={loading} onChange={e => setSelected(e.target.value)}>
        <option value="">{loading ? 'Buscando…' : 'Elige un concepto'}</option>
        {items.map(item => <option key={item.id} value={item.id}>{item.clave} · {item.descripcion} · {item.precio_unitario} / {item.unidad} · {item.vigencia_inicio}</option>)}
      </select>
    </label>
    {item && <p>{item.origen?.fuente.titulo} · página(s) {item.origen?.paginas.join(', ')}. Habilitado por revisión estructural; verifica las condiciones del proyecto.</p>}
    {!loading && !items.length && <p>No hay resultados habilitados. Afina la búsqueda o revisa las ediciones importadas y sus pendientes.</p>}
    <label>Cantidad medida {item?.unidad}
      <input className="block p-2 rounded bg-[#12121A]" type="number" min="0.0001" step="0.0001" value={quantity} onChange={e => setQuantity(e.target.value)} />
    </label>
    <button disabled={!item || !validQuantity || loading} className="rounded border p-2 disabled:opacity-40" onClick={() => { if (item) onSelect(item, Number(quantity)); }}>Agregar concepto al presupuesto</button>
    {error && <p role="alert">{error}</p>}
  </section>;
}
