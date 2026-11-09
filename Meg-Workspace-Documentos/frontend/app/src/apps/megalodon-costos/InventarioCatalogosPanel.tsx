import { useEffect, useState } from 'react';
import { megalodonClient } from '@/lib/api-client';
import type { InventarioCatalogos } from '@/lib/megalodon-client';

export function InventarioCatalogosPanel() {
  const [inventario, setInventario] = useState<InventarioCatalogos | null>(null);
  const [skip, setSkip] = useState(0);
  const [error, setError] = useState('');
  const [cargando, setCargando] = useState(true);
  useEffect(() => {
    let cancelado = false;
    setCargando(true); setError('');
    void megalodonClient.indicesCostos.inventario(skip).then(data => {
      if (!cancelado) setInventario(data);
    }).catch(e => {
      if (!cancelado) setError(e instanceof Error ? e.message : 'No se pudo consultar el inventario.');
    }).finally(() => { if (!cancelado) setCargando(false); });
    return () => { cancelado = true; };
  }, [skip]);

  return <details className="rounded border border-[#2A2A3E] p-3 text-xs">
    <summary className="cursor-pointer">Catálogos en la base conectada</summary>
    {cargando && <p role="status" className="mt-2">Consultando inventario…</p>}
    {error && <p role="alert" className="mt-2 text-[#F08080]">{error}</p>}
    {!cargando && !error && inventario && <div className="mt-3 space-y-3">
      <p>{inventario.total_conceptos.toLocaleString('es-MX')} conceptos · {inventario.total_insumos.toLocaleString('es-MX')} insumos · {inventario.total_fuentes} fuentes.</p>
      <p>{inventario.vinculos_activos_tenant} correspondencias de índice activas para tu organización. El estado activo de un catálogo requiere contrastar su revisión documental.</p>
      {inventario.total_fuentes === 0 && <p>No hay catálogos cargados en esta base.</p>}
      <div className="overflow-x-auto">
        <table className="w-full text-left"><thead><tr>
          <th className="pr-3">Fuente / vigencia</th><th className="pr-3">Conceptos activos / total</th>
          <th className="pr-3">Insumos activos / total</th><th>Materiales MXN sin IVA</th>
        </tr></thead><tbody>{inventario.fuentes.map(f => <tr key={f.id}>
          <td className="pr-3 py-2">{f.nombre} {f.activo ? '' : '(inactiva)'}<br />{f.vigencia_inicio} → {f.vigencia_fin} · {f.moneda || 'Moneda sin acreditar'}</td>
          <td className="pr-3">{f.conceptos_activos} / {f.conceptos}</td>
          <td className="pr-3">{f.insumos_activos} / {f.insumos}</td><td>{f.materiales_sin_iva_mxn}</td>
        </tr>)}</tbody></table>
      </div>
      <div className="flex gap-3">
        <button disabled={skip === 0} onClick={() => setSkip(s => Math.max(0, s - 50))}>Fuentes anteriores</button>
        <span>Página {skip / 50 + 1}</span>
        <button disabled={skip + 50 >= inventario.total_fuentes} onClick={() => setSkip(s => s + 50)}>Fuentes siguientes</button>
      </div>
    </div>}
  </details>;
}
