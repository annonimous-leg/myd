import { useEffect, useState } from 'react';
import { megalodonClient } from '@/lib/api-client';
import type { Partida, Presupuesto } from '@/lib/megalodon-client';

interface Concepto { id: string; clave: string; descripcion: string; unidad: string; tipo: string;
  precio_unitario: number; fuente: string; vigencia_inicio?: string | null; incluye_iva: boolean; }
const unidad = (value: string) => value.trim().toLowerCase().replace('³', '3').replace('²', '2');

export default function CatalogoPartidaPicker({ expedienteId, presupuestoId, partida, onSaved }: {
  expedienteId: string; presupuestoId: string; partida: Partida; onSaved: (presupuesto: Presupuesto) => void;
}) {
  const [query, setQuery] = useState('');
  const [items, setItems] = useState<Concepto[]>([]);
  const [selected, setSelected] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    setSelected(''); setItems([]); setLoading(true); setError('');
    const timer = setTimeout(() => {
      megalodonClient.catalogoAPU.listar({ q: query, tipo: 'CONCEPTO', limit: 50 }).then(result => {
        if (!active) return;
        const response = result as { items: Concepto[] };
        setItems(response.items.filter(item => unidad(item.unidad) === unidad(partida.unidad) && !item.incluye_iva));
      }).catch(e => { if (active) setError(e instanceof Error ? e.message : 'No se pudo buscar en el catálogo'); })
        .finally(() => { if (active) setLoading(false); });
    }, 250);
    return () => { active = false; clearTimeout(timer); };
  }, [query, expedienteId, partida.id, partida.unidad]);
  async function save() {
    if (!selected || busy) return;
    setBusy(true); setError('');
    try {
      onSaved(await megalodonClient.presupuestos.asignarCatalogoPartida(expedienteId, presupuestoId, partida.id, selected));
    } catch (e) { setError(e instanceof Error ? e.message : 'No se pudo asignar el concepto'); }
    finally { setBusy(false); }
  }
  return <div className="mt-2 space-y-1">
    <input aria-label={`Buscar concepto para partida ${partida.numero}`} value={query} onChange={e => setQuery(e.target.value)}
      placeholder="Buscar clave, descripción o fuente" disabled={busy} className="w-full rounded p-1 bg-(--surface-elevated)" />
    <select aria-label={`Concepto para partida ${partida.numero}`} value={selected} onChange={e => setSelected(e.target.value)}
      disabled={busy || loading} className="w-full rounded p-1 bg-(--surface-elevated)">
      <option value="">{loading ? 'Buscando…' : 'Selecciona un concepto revisado'}</option>
      {items.map(item => <option key={item.id} value={item.id}>{item.clave} · {item.descripcion} · {item.precio_unitario} / {item.unidad} · {item.fuente} · {item.vigencia_inicio || 'Vigencia sin registrar'}</option>)}
    </select>
    {!loading && !items.length && <p>No hay conceptos compatibles en estos resultados. Afina la búsqueda o importa tu catálogo.</p>}
    <button disabled={busy || !selected || loading} onClick={() => void save()} className="rounded border p-1 disabled:opacity-40">
      {busy ? 'Guardando…' : `Asignar concepto a partida ${partida.numero}`}
    </button>
    {error && <p role="alert" className="text-(--danger)">{error}</p>}
  </div>;
}
