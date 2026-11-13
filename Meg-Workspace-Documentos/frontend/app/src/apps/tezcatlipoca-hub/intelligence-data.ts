/** Domain-only helpers: no browser globals, external APIs, or synthetic observations. */
import type { ContextoGeoTez } from '../../lib/megalodon-client';

export type ObservationKind = 'earthquake' | 'aircraft' | 'ship';
export interface RegionalBounds {
  latMin: number;
  latMax: number;
  lonMin: number;
  lonMax: number;
}
export interface TezObservation {
  id: string;
  kind: ObservationKind;
  title: string;
  detail: string;
  source: string;
  lat: number;
  lon: number;
  observedAt: string | null;
}

export interface ProviderInfo {
  status?: string;
  last_success?: string | null;
  last_observation?: string | null;
  age_seconds?: number;
  coverage?: string;
  license?: string;
  attribution?: string;
  reason?: string;
}

export function regionalBounds(latText: string, lonText: string, radiusKm: number): RegionalBounds {
  const lat = latText.trim() ? Number(latText) : Number.NaN;
  const lon = lonText.trim() ? Number(lonText) : Number.NaN;
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) {
    throw new Error('Introduce una latitud y longitud válidas.');
  }
  if (!Number.isFinite(radiusKm) || radiusKm < 10 || radiusKm > 200) {
    throw new Error('Selecciona un radio entre 10 y 200 km.');
  }
  const latOffset = radiusKm / 111.32;
  const cos = Math.cos(lat * Math.PI / 180);
  if (cos < 0.05) throw new Error('Región próxima a los polos: reduce o cambia el radio.');
  const lonOffset = radiusKm / (111.32 * cos);
  if (lat - latOffset < -90 || lat + latOffset > 90 || lon - lonOffset < -180 || lon + lonOffset > 180) {
    throw new Error('La región cruza el límite de coordenadas; reduce el radio o mueve el centro.');
  }
  return {
    latMin: lat - latOffset, latMax: lat + latOffset,
    lonMin: lon - lonOffset, lonMax: lon + lonOffset,
  };
}

function coordinates(lat: unknown, lon: unknown): lat is number {
  return typeof lat === 'number' && typeof lon === 'number'
    && Number.isFinite(lat) && Number.isFinite(lon)
    && Math.abs(lat) <= 90 && Math.abs(lon) <= 180;
}

export function observationDate(value: unknown): string | null {
  if (typeof value !== 'string' && (typeof value !== 'number' || value <= 0)) return null;
  if (typeof value === 'string' && !value.trim()) return null;
  const epoch = new Date(value).getTime();
  return Number.isFinite(epoch) ? new Date(epoch).toISOString() : null;
}

export function observationsFromContext(context: ContextoGeoTez | null): TezObservation[] {
  if (!context) return [];
  const rows: TezObservation[] = [];
  for (const q of Array.isArray(context.earthquakes) ? context.earthquakes : []) {
    if (!coordinates(q.lat, q.lon)) continue;
    rows.push({
      id: 'q-' + String(q.id), kind: 'earthquake', title: q.place || 'Sismo',
      detail: Number.isFinite(q.magnitude) ? 'Magnitud ' + q.magnitude : 'Magnitud no informada',
      source: q.source || 'usgs', lat: q.lat, lon: q.lon, observedAt: observationDate(q.time),
    });
  }
  for (const a of Array.isArray(context.aircraft) ? context.aircraft : []) {
    if (!coordinates(a.lat, a.lon)) continue;
    rows.push({
      id: 'a-' + String(a.hex), kind: 'aircraft', title: a.callsign || a.hex || 'Aeronave',
      detail: a.hex || 'Sin identificador',
      source: a.source || 'Fuente no indicada', lat: a.lat, lon: a.lon, observedAt: observationDate(a.timestamp),
    });
  }
  for (const s of Array.isArray(context.ships) ? context.ships : []) {
    if (!coordinates(s.lat, s.lon)) continue;
    rows.push({
      id: 's-' + String(s.mmsi), kind: 'ship', title: s.name || s.mmsi || 'Embarcación',
      detail: s.mmsi || 'Sin MMSI',
      source: s.source || 'Fuente no indicada', lat: s.lat, lon: s.lon, observedAt: observationDate(s.timestamp),
    });
  }
  return rows;
}

export function providerStatus(info: ProviderInfo | undefined, queried: boolean): string {
  if (!queried) return 'Sin consultar';
  if (!info) return 'Proveedor sin estado';
  switch (info.status) {
    case 'available': return 'Datos recibidos';
    case 'connected': return 'Conectado; sin observaciones vigentes';
    case 'stale': return 'Datos desactualizados';
    case 'coverage_limited': return 'Cobertura limitada';
    case 'disabled_by_default': return 'Desactivado por licencia o configuración';
    case 'not_received': return 'Sin recepción registrada';
    case 'unavailable':
    case 'offline': return 'No disponible';
    case 'error': return 'Error de origen';
    case 'running': return 'Motor iniciado; consultar fuentes';
    default: return info.status ? 'Estado: ' + info.status : 'Estado no informado';
  }
}
