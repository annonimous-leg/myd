/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

/**
 * Mapa real (no estilizado) para Topografía & GIS.
 *
 * Tres capas base, las tres reales y sin API key:
 *  - "Calles" — OpenStreetMap (uso libre; para tráfico alto en producción,
 *    self-host de tiles o un proveedor con SLA, no golpear tile.openstreetmap.org
 *    directo — está en la nota al pie de este archivo).
 *  - "Satélite" — Esri World Imagery, resolución real de sitio (~1 m o mejor
 *    en la mayoría de zonas urbanas/industriales de México).
 *  - "NASA (tiempo real)" — GIBS (Global Imagery Browse Services), mosaico
 *    global MODIS Terra actualizado a diario. Resolución ~250 m/px: sirve
 *    para contexto planetario/clima, NO para precisión de sitio. Trae
 *    selector de fecha real (por defecto "ayer", ya que la cobertura global
 *    del día actual normalmente no está completa todavía).
 *
 * Los marcadores/contornos/polígono que recibe este componente ya deben
 * venir en lon/lat (EPSG:4326) — la transformación desde el CRS local del
 * levantamiento (UTM u otro) se hace en el componente padre llamando al
 * endpoint real megalodonClient.topografia.transformarCoordenadas(), no
 * aquí. Este componente no sabe nada de topografía, solo de mapas.
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import * as maplibregl from 'maplibre-gl';
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url';
import type { FeatureCollection, LineString } from 'geojson';
import 'maplibre-gl/dist/maplibre-gl.css';
import { Satellite, MapIcon, Orbit, Crosshair, Calendar } from 'lucide-react';

export interface MarcadorMapa {
  id: string;
  lon: number;
  lat: number;
  etiqueta?: string;
  elevacion?: number;
  tipo?: 'punto' | 'estacion' | 'bm';
}

export interface MapaRealProps {
  marcadores?: MarcadorMapa[];
  /** Cada entrada es una polilínea [lon,lat][] de una curva de nivel. */
  contornos?: { elevacion: number; linea: [number, number][] }[];
  /** Vértices [lon,lat][] de un polígono (p.ej. resultado de cierre poligonal). */
  poligono?: [number, number][];
  centroInicial?: [number, number];
  zoomInicial?: number;
  onMapClick?: (lon: number, lat: number) => void;
  /** Puntos que el usuario va marcando para una herramienta activa (perfil, poligonal). */
  seleccion?: [number, number][];
  alturaClase?: string;
}

type CapaBase = 'osm' | 'esri' | 'nasa';

function ayer(): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
}

const NASA_LAYER = 'MODIS_Terra_CorrectedReflectance_TrueColor';
const NASA_TILEMATRIX = 'GoogleMapsCompatible_Level9';
maplibregl.setWorkerUrl(maplibreWorkerUrl);
function urlNasa(fecha: string): string {
  return `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${NASA_LAYER}/default/${fecha}/${NASA_TILEMATRIX}/{z}/{y}/{x}.jpg`;
}

const ESTILO_BASE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: 'raster',
      tiles: ['https://a.tile.openstreetmap.org/{z}/{x}/{y}.png', 'https://b.tile.openstreetmap.org/{z}/{x}/{y}.png', 'https://c.tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      maxzoom: 19,
      attribution: '© OpenStreetMap contributors',
    },
    esri: {
      type: 'raster',
      tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
      tileSize: 256,
      maxzoom: 19,
      attribution: 'Esri, Maxar, Earthstar Geographics',
    },
    nasa: {
      type: 'raster',
      tiles: [urlNasa(ayer())],
      tileSize: 256,
      maxzoom: 9,
      attribution: 'NASA EOSDIS GIBS',
    },
    puntos: { type: 'geojson', data: { type: 'FeatureCollection', features: [] } },
    contornos: { type: 'geojson', data: { type: 'FeatureCollection', features: [] } },
    poligono: { type: 'geojson', data: { type: 'FeatureCollection', features: [] } },
    seleccion: { type: 'geojson', data: { type: 'FeatureCollection', features: [] } },
  },
  layers: [
    { id: 'osm-layer', type: 'raster', source: 'osm', layout: { visibility: 'visible' } },
    { id: 'esri-layer', type: 'raster', source: 'esri', layout: { visibility: 'none' } },
    { id: 'nasa-layer', type: 'raster', source: 'nasa', layout: { visibility: 'none' } },
    { id: 'contornos-layer', type: 'line', source: 'contornos', paint: { 'line-color': ['get', 'color'], 'line-width': ['case', ['get', 'maestra'], 1.6, 0.8], 'line-opacity': 0.85 } },
    { id: 'poligono-fill', type: 'fill', source: 'poligono', paint: { 'fill-color': '#C9A84C', 'fill-opacity': 0.08 } },
    { id: 'poligono-linea', type: 'line', source: 'poligono', paint: { 'line-color': '#C9A84C', 'line-width': 2 } },
    { id: 'seleccion-linea', type: 'line', source: 'seleccion', paint: { 'line-color': '#4A9E9E', 'line-width': 2, 'line-dasharray': [2, 1.5] } },
    { id: 'seleccion-puntos', type: 'circle', source: 'seleccion', paint: { 'circle-radius': 5, 'circle-color': '#4A9E9E', 'circle-stroke-width': 2, 'circle-stroke-color': '#030305' } },
    {
      id: 'puntos-layer', type: 'circle', source: 'puntos',
      paint: {
        'circle-radius': ['match', ['get', 'tipo'], 'estacion', 7, 'bm', 6, 5],
        'circle-color': ['match', ['get', 'tipo'], 'estacion', '#4A9E9E', 'bm', '#C9A84C', '#E8E4DC'],
        'circle-stroke-width': 2,
        'circle-stroke-color': '#030305',
      },
    },
    {
      id: 'puntos-labels', type: 'symbol', source: 'puntos',
      layout: { 'text-field': ['get', 'etiqueta'], 'text-size': 10, 'text-offset': [0, 1.3], 'text-anchor': 'top' },
      paint: { 'text-color': '#E8E4DC', 'text-halo-color': '#030305', 'text-halo-width': 1.4 },
    },
  ],
};

function lineaAGeoJSON(contornos: MapaRealProps['contornos']): FeatureCollection<LineString> {
  const elevaciones = (contornos || []).map((c) => c.elevacion);
  const min = Math.min(...elevaciones, 0);
  const max = Math.max(...elevaciones, 1);
  const rango = max - min || 1;
  return {
    type: 'FeatureCollection',
    features: (contornos || []).map((c, i) => {
      const t = (c.elevacion - min) / rango;
      // Rampa verde -> ámbar -> café, misma lógica que la superficie 3D.
      const color = t < 0.5
        ? `rgb(${Math.round(51 + t * 2 * (212 - 51))},${Math.round(140 + t * 2 * (149 - 140))},${Math.round(64 + t * 2 * (77 - 64))})`
        : `rgb(${Math.round(212 + (t - 0.5) * 2 * (140 - 212))},${Math.round(149 + (t - 0.5) * 2 * (89 - 149))},${Math.round(77 + (t - 0.5) * 2 * (51 - 77))})`;
      return {
        type: 'Feature',
        id: i,
        properties: { elevacion: c.elevacion, color, maestra: i % 5 === 0 },
        geometry: { type: 'LineString', coordinates: c.linea },
      };
    }),
  };
}

export default function MapaReal({
  marcadores = [], contornos = [], poligono = [], centroInicial, zoomInicial = 16, onMapClick, seleccion = [], alturaClase = 'h-full',
}: MapaRealProps) {
  const contenedorRef = useRef<HTMLDivElement>(null);
  const mapaRef = useRef<maplibregl.Map | null>(null);
  const [listo, setListo] = useState(false);
  const [capa, setCapa] = useState<CapaBase>('esri');
  const [fechaNasa, setFechaNasa] = useState(ayer());
  const [cursor, setCursor] = useState<{ lon: number; lat: number } | null>(null);
  const [zoomActual, setZoomActual] = useState(zoomInicial);

  const onMapClickRef = useRef(onMapClick);
  useEffect(() => { onMapClickRef.current = onMapClick; }, [onMapClick]);

  useEffect(() => {
    if (!contenedorRef.current || mapaRef.current) return;
    const mapa = new maplibregl.Map({
      container: contenedorRef.current,
      style: ESTILO_BASE,
      center: centroInicial || [-99.1332, 19.4326],
      zoom: zoomInicial,
      attributionControl: { compact: true },
    });
    mapa.addControl(new maplibregl.NavigationControl({ showCompass: true }), 'top-right');
    mapa.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');
    mapa.on('load', () => setListo(true));
    mapa.on('mousemove', (e) => setCursor({ lon: e.lngLat.lng, lat: e.lngLat.lat }));
    mapa.on('zoom', () => setZoomActual(mapa.getZoom()));
    mapa.on('click', (e) => onMapClickRef.current?.(e.lngLat.lng, e.lngLat.lat));
    mapaRef.current = mapa;
    return () => { mapa.remove(); mapaRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const centroLon = centroInicial?.[0];
  const centroLat = centroInicial?.[1];
  useEffect(() => {
    if (listo && centroLon !== undefined && centroLat !== undefined) {
      mapaRef.current?.jumpTo({ center: [centroLon, centroLat], zoom: zoomInicial });
    }
  }, [listo, centroLon, centroLat, zoomInicial]);

  useEffect(() => {
    const mapa = mapaRef.current;
    if (!mapa || !listo) return;
    (['osm', 'esri', 'nasa'] as const).forEach((id) => {
      mapa.setLayoutProperty(`${id}-layer`, 'visibility', id === capa ? 'visible' : 'none');
    });
  }, [capa, listo]);

  useEffect(() => {
    const mapa = mapaRef.current;
    if (!mapa || !listo) return;
    const source = mapa.getSource('nasa') as maplibregl.RasterTileSource | undefined;
    source?.setTiles([urlNasa(fechaNasa)]);
  }, [fechaNasa, listo]);

  useEffect(() => {
    const mapa = mapaRef.current;
    if (!mapa || !listo) return;
    const source = mapa.getSource('puntos') as maplibregl.GeoJSONSource | undefined;
    source?.setData({
      type: 'FeatureCollection',
      features: marcadores.map((m) => ({
        type: 'Feature',
        properties: { etiqueta: m.etiqueta || m.id, elevacion: m.elevacion, tipo: m.tipo || 'punto' },
        geometry: { type: 'Point', coordinates: [m.lon, m.lat] },
      })),
    });
  }, [marcadores, listo]);

  useEffect(() => {
    const mapa = mapaRef.current;
    if (!mapa || !listo) return;
    (mapa.getSource('contornos') as maplibregl.GeoJSONSource | undefined)?.setData(lineaAGeoJSON(contornos));
  }, [contornos, listo]);

  useEffect(() => {
    const mapa = mapaRef.current;
    if (!mapa || !listo) return;
    const cerrado = poligono.length > 2 ? [...poligono, poligono[0]] : poligono;
    const feature = poligono.length > 2
      ? { type: 'Feature' as const, properties: {}, geometry: { type: 'Polygon' as const, coordinates: [cerrado] } }
      : { type: 'Feature' as const, properties: {}, geometry: { type: 'LineString' as const, coordinates: cerrado } };
    (mapa.getSource('poligono') as maplibregl.GeoJSONSource | undefined)?.setData({
      type: 'FeatureCollection',
      features: poligono.length > 1 ? [feature] : [],
    });
  }, [poligono, listo]);

  useEffect(() => {
    const mapa = mapaRef.current;
    if (!mapa || !listo) return;
    (mapa.getSource('seleccion') as maplibregl.GeoJSONSource | undefined)?.setData({
      type: 'FeatureCollection',
      features: [
        ...(seleccion.length > 1 ? [{ type: 'Feature' as const, properties: {}, geometry: { type: 'LineString' as const, coordinates: seleccion } }] : []),
        ...seleccion.map((c) => ({ type: 'Feature' as const, properties: {}, geometry: { type: 'Point' as const, coordinates: c } })),
      ],
    });
  }, [seleccion, listo]);

  const centrarEnPuntos = useCallback(() => {
    const mapa = mapaRef.current;
    if (!mapa || marcadores.length === 0) return;
    const lons = marcadores.map((m) => m.lon);
    const lats = marcadores.map((m) => m.lat);
    mapa.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: 60, maxZoom: 19, duration: 600 });
  }, [marcadores]);

  return (
    <div className={`relative w-full ${alturaClase}`} style={{ background: '#05050a' }}>
      <div ref={contenedorRef} className="absolute inset-0" />

      <div className="absolute top-2 left-2 flex flex-col gap-1 rounded-lg p-1" style={{ background: 'rgba(10,10,15,0.85)', border: '1px solid var(--border-subtle)', backdropFilter: 'blur(6px)' }}>
        {([
          ['osm', 'Calles', MapIcon],
          ['esri', 'Satélite', Satellite],
          ['nasa', 'NASA', Orbit],
        ] as const).map(([id, label, Icon]) => (
          <button
            key={id}
            onClick={() => setCapa(id)}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[11px] font-medium"
            style={capa === id ? { background: 'var(--accent-gold)', color: 'var(--void)' } : { color: 'var(--text-secondary)' }}
          >
            <Icon size={12} /> {label}
          </button>
        ))}
        {capa === 'nasa' && (
          <div className="flex items-center gap-1.5 px-2 pt-1 mt-0.5" style={{ borderTop: '1px solid var(--border-subtle)' }}>
            <Calendar size={11} style={{ color: 'var(--text-muted)' }} />
            <input
              type="date"
              value={fechaNasa}
              max={ayer()}
              onChange={(e) => setFechaNasa(e.target.value)}
              className="text-[10px] bg-transparent outline-hidden"
              style={{ color: 'var(--text-secondary)', colorScheme: 'dark' }}
            />
          </div>
        )}
      </div>

      {marcadores.length > 0 && (
        <button
          onClick={centrarEnPuntos}
          title="Centrar en los puntos del levantamiento"
          className="absolute top-2 right-2 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-medium"
          style={{ background: 'rgba(10,10,15,0.85)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)', backdropFilter: 'blur(6px)' }}
        >
          <Crosshair size={12} /> Centrar
        </button>
      )}

      <div
        className="absolute bottom-10 left-2 right-2 flex items-center justify-between px-3 py-1.5 rounded-lg text-[10px] font-mono"
        style={{ background: 'rgba(10,10,15,0.85)', border: '1px solid var(--border-subtle)', color: 'var(--accent-cyan)', backdropFilter: 'blur(6px)' }}
      >
        <span className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: 'var(--accent-cyan)' }} />
          {cursor ? `${cursor.lat.toFixed(6)}°, ${cursor.lon.toFixed(6)}°` : 'mueve el cursor sobre el mapa'}
        </span>
        <span style={{ color: 'var(--text-muted)' }}>
          zoom {zoomActual.toFixed(1)} · {capa === 'nasa' ? `NASA GIBS · ${fechaNasa}` : capa === 'esri' ? 'Esri World Imagery' : 'OpenStreetMap'}
        </span>
      </div>
    </div>
  );
}

/**
 * NOTA DE PRODUCCIÓN — sobre las 3 fuentes de tiles usadas arriba:
 * Las tres son reales, públicas y no requieren API key, pero:
 *  - OpenStreetMap: su política de uso desalienta tráfico alto directo a
 *    tile.openstreetmap.org. Para producción con volumen real, cambiar las
 *    URLs por un proveedor con SLA (MapTiler, Stadia, etc. — solo cambia el
 *    arreglo `tiles` de la fuente `osm` arriba) o self-hostear.
 *  - Esri World Imagery: uso general gratuito está permitido por Esri para
 *    la mayoría de aplicaciones; revisar sus términos si el uso es masivo.
 *  - NASA GIBS: sin límite de key, pero es un mosaico global de ~250 m/px
 *    (no sirve para precisión de sitio, solo contexto). Ver comentario al
 *    inicio del archivo.
 */
