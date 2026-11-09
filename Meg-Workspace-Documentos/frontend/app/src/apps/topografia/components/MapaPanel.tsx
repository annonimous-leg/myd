/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

/**
 * Tab "Mapa": el único punto donde se conectan Levantamiento + Tezcatlipoca.
 * Toma los puntos reales del levantamiento activo (local X/Y en su CRS),
 * los transforma a lon/lat con el endpoint real transformarCoordenadas, y
 * con ese bbox real alimenta el feed de Tezcatlipoca — así "aeronaves/
 * barcos/sismos cerca" es cerca del sitio real, no un query global.
 */
import { useEffect, useState } from 'react';
import { Loader2, AlertCircle, MapPin } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';
import type { Levantamiento, PuntoTopografico } from '@/lib/megalodon-client';
import MapaReal, { type MarcadorMapa } from './MapaReal';
import TezcatlipocaFeedPanel from './TezcatlipocaFeedPanel';

export default function MapaPanel({ levantamiento }: { levantamiento: Levantamiento | null }) {
  const [marcadores, setMarcadores] = useState<MarcadorMapa[]>([]);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState('');
  const [bbox, setBbox] = useState<{ latMin: string; latMax: string; lonMin: string; lonMax: string } | undefined>();

  useEffect(() => {
    if (!levantamiento) { setMarcadores([]); setBbox(undefined); return; }
    let cancelado = false;
    (async () => {
      setCargando(true); setError(''); setMarcadores([]); setBbox(undefined);
      try {
        const puntos: PuntoTopografico[] = await megalodonClient.topografia.listarPuntos(levantamiento.id);
        if (puntos.length === 0) { if (!cancelado) { setMarcadores([]); setCargando(false); } return; }
        const crsOrigen = levantamiento.crs || `EPSG:${levantamiento.srid}`;
        const { puntos: geo } = await megalodonClient.topografia.transformarCoordenadas(
          puntos.map((p) => [p.x, p.y]), crsOrigen, 'EPSG:4326',
        );
        if (cancelado) return;
        const nuevos: MarcadorMapa[] = puntos.map((p, i) => ({
          id: p.id, lon: geo[i][0], lat: geo[i][1], etiqueta: p.identificador, elevacion: p.z,
          tipo: p.identificador?.toUpperCase().startsWith('BM') ? 'bm' : p.identificador?.toUpperCase().startsWith('ET') ? 'estacion' : 'punto',
        }));
        setMarcadores(nuevos);
        const lats = nuevos.map((m) => m.lat), lons = nuevos.map((m) => m.lon);
        setBbox({ latMin: String(Math.min(...lats)), latMax: String(Math.max(...lats)), lonMin: String(Math.min(...lons)), lonMax: String(Math.max(...lons)) });
      } catch (e) {
        if (!cancelado) setError(e instanceof Error ? e.message : 'No se pudo geo-referenciar el levantamiento (revisa que el CRS sea soportado por /topografia/geodesia/transformar)');
      } finally {
        if (!cancelado) setCargando(false);
      }
    })();
    return () => { cancelado = true; };
  }, [levantamiento]);

  if (!levantamiento) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-2 text-sm text-center" style={{ color: 'var(--text-muted)' }}>
        <MapPin className="w-8 h-8 opacity-40" /> Selecciona un levantamiento en la pestaña Levantamiento para ubicarlo en el mapa real.
      </div>
    );
  }

  const centro: [number, number] | undefined = marcadores.length > 0
    ? [marcadores.reduce((a, m) => a + m.lon, 0) / marcadores.length, marcadores.reduce((a, m) => a + m.lat, 0) / marcadores.length]
    : undefined;

  return (
    <div className="h-full flex">
      <div className="flex-1 relative min-w-0">
        <MapaReal marcadores={marcadores} centroInicial={centro} zoomInicial={marcadores.length > 0 ? 17 : 4} />
        {cargando && (
          <div className="absolute inset-0 flex items-center justify-center gap-2 text-sm" style={{ background: 'rgba(3,3,5,0.55)', color: 'var(--text-secondary)' }}>
            <Loader2 size={16} className="animate-spin" /> Geo-referenciando puntos del levantamiento…
          </div>
        )}
        {error && (
          <div className="absolute top-2 left-2 right-2 flex items-center gap-2 rounded-lg px-3 py-2 text-xs" style={{ background: 'rgba(184,74,74,0.15)', border: '1px solid var(--danger)44', color: 'var(--danger)' }}>
            <AlertCircle size={13} className="shrink-0" /> {error}
          </div>
        )}
        {!cargando && !error && marcadores.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center">
            <p className="text-sm text-center max-w-xs" style={{ color: 'var(--text-muted)' }}>Este levantamiento no tiene puntos importados todavía — súbelos en la pestaña Levantamiento.</p>
          </div>
        )}
      </div>
      <div className="w-72 shrink-0 p-2 overflow-y-auto" style={{ borderLeft: '1px solid var(--border-subtle)', background: 'var(--surface)' }}>
        <TezcatlipocaFeedPanel bbox={bbox} />
      </div>
    </div>
  );
}
