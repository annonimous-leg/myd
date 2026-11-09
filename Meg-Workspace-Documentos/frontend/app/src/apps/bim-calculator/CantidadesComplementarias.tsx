import type { ElementoBIM } from '@/lib/megalodon-client';

export type CapturaCantidad = { cantidad: string; referencia: string; unidad: string };

export function faltantesDeMedicion(
  elementos: ElementoBIM[],
  unidades: Record<string,string>,
  unidadesPorElemento: Record<string,string> = {},
) {
  return elementos.flatMap(elemento => {
    const unidad = (unidadesPorElemento[elemento.id] || unidades[elemento.tipo] ||
      (['IfcWall','IfcSlab','IfcRoof','IfcCovering'].includes(elemento.tipo) ? 'm2'
        : ['IfcDoor','IfcWindow'].includes(elemento.tipo) ? 'pza' : 'm3')).toLowerCase().trim();
    const cantidad = unidad === 'm3' ? elemento.volumen
      : ['m','ml'].includes(unidad) ? elemento.longitud : unidad === 'pza' ? 1 : null;
    if (cantidad != null && Number.isFinite(cantidad) && cantidad > 0) return [];
    return [{elemento,unidad}];
  });
}

export default function CantidadesComplementarias({faltantes,capturas,onChange,disabled}: {
  faltantes: ReturnType<typeof faltantesDeMedicion>; capturas: Record<string,CapturaCantidad>;
  onChange: (id:string,value:CapturaCantidad)=>void; disabled:boolean;
}) {
  if (!faltantes.length) return null;
  return <section className="p-2 space-y-3 rounded border border-(--border-subtle)" aria-label="Completar mediciones faltantes">
    <h3 className="text-xs font-semibold">Completar {faltantes.length} mediciones</h3>
    <p className="text-xs text-(--text-muted)">Lo medido se costea desde ahora. Puedes generar una versión parcial o completar cada faltante con una medición y su fuente. Las partidas en m² requieren revisar qué superficie pide el concepto. Las capturas quedan registradas en el presupuesto y conservan el IFC original.</p>
    {faltantes.map(({elemento,unidad}) => {
      const value = capturas[elemento.id]?.unidad === unidad ? capturas[elemento.id] : {cantidad:'',referencia:'',unidad};
      return <fieldset key={elemento.id} className="space-y-1" disabled={disabled}>
        <legend className="text-xs break-all">{elemento.nombre || elemento.tipo} · {elemento.global_id}</legend>
        <label className="block text-xs">Cantidad faltante ({unidad})
          <input type="number" min="0.0001" step="any" value={value.cantidad}
            onChange={e=>onChange(elemento.id,{...value,cantidad:e.target.value})}
            className="w-full p-2 rounded bg-(--surface-elevated)" />
        </label>
        <label className="block text-xs">Referencia de la medición
          <input value={value.referencia} maxLength={1000} placeholder="Plano, levantamiento o memoria de cálculo"
            onChange={e=>onChange(elemento.id,{...value,referencia:e.target.value})}
            className="w-full p-2 rounded bg-(--surface-elevated)" />
        </label>
      </fieldset>;
    })}
  </section>;
}
