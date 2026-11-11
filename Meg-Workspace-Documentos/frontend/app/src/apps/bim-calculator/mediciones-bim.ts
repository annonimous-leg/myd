import type { ElementoBIM } from '@/lib/megalodon-client';

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
    const requiereRevisionGeometrica = unidad === 'm3' && elemento.fuente_volumen === 'GEOMETRIA_CALCULADA';
    if (!requiereRevisionGeometrica && cantidad != null && Number.isFinite(cantidad) && cantidad > 0) return [];
    return [{elemento,unidad,requiereRevisionGeometrica}];
  });
}
