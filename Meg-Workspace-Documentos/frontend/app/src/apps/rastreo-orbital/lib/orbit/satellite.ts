/**
 * Motor orbital local de producción para Tezcatlipoca.
 *
 * Consume TLE públicos (CelesTrak) y propaga órbitas con un modelo
 * determinista de dos cuerpos, manteniendo trazabilidad completa entre
 * datos de entrada, estado orbital y conversión ECI -> ECEF -> geodética.
 *
 * La intención operativa aquí no es simular con mocks ni depender de
 * paquetes externos frágiles del registry, sino entregar una base local
 * estable, auditable y reproducible para el rastreo orbital del sistema.
 */

export type Vec3 = { x: number; y: number; z: number }

export interface SatRec {
  satnum: number
  epochyr: number
  epochdays: number
  epochDate: Date
  inclination: number
  raan: number
  eccentricity: number
  argPerigee: number
  meanAnomaly: number
  meanMotion: number
  meanMotionRad: number
  semiMajorAxisKm: number
  bstar: number
  line1: string
  line2: string
}

export interface OrbitState {
  position: Vec3
  velocity: Vec3
}

const MU = 398600.4418 // km^3/s^2
const EARTH_RADIUS_KM = 6378.137
const EARTH_FLATTENING = 1 / 298.257223563
const EARTH_E2 = EARTH_FLATTENING * (2 - EARTH_FLATTENING)

function clamp(v: number, min: number, max: number): number {
  return Math.min(Math.max(v, min), max)
}

function deg2rad(v: number): number {
  return (v * Math.PI) / 180
}

function rad2deg(v: number): number {
  return (v * 180) / Math.PI
}

function normalizeAngle(v: number): number {
  const twoPi = Math.PI * 2
  let n = v % twoPi
  if (n < 0) n += twoPi
  return n
}

function parseExponentField(value: string): number {
  const s = value.trim()
  if (!s) return 0
  const mantissaRaw = s.slice(0, s.length - 2).trim()
  const exponentRaw = s.slice(-2).trim()
  const mantissa = mantissaRaw ? Number.parseFloat(mantissaRaw.replace(/^\+/, '')) : 0
  const exponent = Number.parseInt(exponentRaw || '0', 10)
  if (!Number.isFinite(mantissa) || !Number.isFinite(exponent)) return 0
  return mantissa * 10 ** exponent
}

function parseEpoch(year2: number, dayOfYear: number): Date {
  const fullYear = year2 < 57 ? 2000 + year2 : 1900 + year2
  const wholeDays = Math.floor(dayOfYear) - 1
  const fraction = dayOfYear - Math.floor(dayOfYear)
  const ms = Date.UTC(fullYear, 0, 1, 0, 0, 0, 0) + wholeDays * 86400000 + Math.round(fraction * 86400000)
  return new Date(ms)
}

function solveKepler(meanAnomaly: number, eccentricity: number): number {
  const M = normalizeAngle(meanAnomaly)
  let E = eccentricity < 0.8 ? M : Math.PI
  for (let i = 0; i < 15; i++) {
    const f = E - eccentricity * Math.sin(E) - M
    const fp = 1 - eccentricity * Math.cos(E)
    const delta = f / fp
    E -= delta
    if (Math.abs(delta) < 1e-12) break
  }
  return E
}

function eciToEcef(r: Vec3, gmst: number): Vec3 {
  const c = Math.cos(gmst)
  const s = Math.sin(gmst)
  return {
    x: c * r.x + s * r.y,
    y: -s * r.x + c * r.y,
    z: r.z,
  }
}

function ecefToGeodetic(r: Vec3): { longitude: number; latitude: number; height: number } {
  const x = r.x
  const y = r.y
  const z = r.z
  const lon = Math.atan2(y, x)
  const p = Math.sqrt(x * x + y * y)
  let lat = Math.atan2(z, p * (1 - EARTH_E2))
  let height = 0
  for (let i = 0; i < 8; i++) {
    const sinLat = Math.sin(lat)
    const N = EARTH_RADIUS_KM / Math.sqrt(1 - EARTH_E2 * sinLat * sinLat)
    height = p / Math.cos(lat) - N
    const newLat = Math.atan2(z, p * (1 - EARTH_E2 * (N / (N + height))))
    if (Math.abs(newLat - lat) < 1e-12) {
      lat = newLat
      break
    }
    lat = newLat
  }
  return { longitude: lon, latitude: lat, height }
}

export function twoline2satrec(l1: string, l2: string): SatRec {
  if (!l1 || !l2 || l1.length < 69 || l2.length < 69) {
    throw new Error('TLE inválido')
  }

  const satnum = Number.parseInt(l1.slice(2, 7).trim(), 10) || 0
  const epochyr = Number.parseInt(l1.slice(18, 20).trim(), 10) || 0
  const epochdays = Number.parseFloat(l1.slice(20, 32).trim())
  const bstar = parseExponentField(l1.slice(53, 61))

  const inclination = deg2rad(Number.parseFloat(l2.slice(8, 16).trim()))
  const raan = deg2rad(Number.parseFloat(l2.slice(17, 25).trim()))
  const eccentricity = Number.parseFloat(`0.${l2.slice(26, 33).trim()}`)
  const argPerigee = deg2rad(Number.parseFloat(l2.slice(34, 42).trim()))
  const meanAnomaly = deg2rad(Number.parseFloat(l2.slice(43, 51).trim()))
  const meanMotion = Number.parseFloat(l2.slice(52, 63).trim())
  if (!Number.isFinite(meanMotion) || meanMotion <= 0) {
    throw new Error('TLE sin mean motion válido')
  }
  const meanMotionRad = (meanMotion * 2 * Math.PI) / 86400
  const semiMajorAxisKm = Math.cbrt(MU / (meanMotionRad * meanMotionRad))

  return {
    satnum,
    epochyr,
    epochdays,
    epochDate: parseEpoch(epochyr, epochdays),
    inclination,
    raan,
    eccentricity: clamp(eccentricity, 0, 0.999999),
    argPerigee,
    meanAnomaly,
    meanMotion,
    meanMotionRad,
    semiMajorAxisKm,
    bstar,
    line1: l1,
    line2: l2,
  }
}

export function propagate(rec: SatRec, date: Date): OrbitState {
  const dt = (date.getTime() - rec.epochDate.getTime()) / 1000
  const a = rec.semiMajorAxisKm
  const e = rec.eccentricity
  const n = rec.meanMotionRad

  const M = rec.meanAnomaly + n * dt
  const E = solveKepler(M, e)

  const cosE = Math.cos(E)
  const sinE = Math.sin(E)
  const sqrt1me2 = Math.sqrt(Math.max(1 - e * e, 1e-12))
  const xOrb = a * (cosE - e)
  const yOrb = a * sqrt1me2 * sinE

  const p = a * (1 - e * e)
  const sqrtMuOverP = Math.sqrt(MU / p)
  const vxOrb = -sqrtMuOverP * sinE
  const vyOrb = sqrtMuOverP * sqrt1me2 * cosE

  const cosO = Math.cos(rec.raan)
  const sinO = Math.sin(rec.raan)
  const cosi = Math.cos(rec.inclination)
  const sini = Math.sin(rec.inclination)
  const cosw = Math.cos(rec.argPerigee)
  const sinw = Math.sin(rec.argPerigee)

  const r11 = cosO * cosw - sinO * sinw * cosi
  const r12 = -cosO * sinw - sinO * cosw * cosi
  const r21 = sinO * cosw + cosO * sinw * cosi
  const r22 = -sinO * sinw + cosO * cosw * cosi
  const r31 = sinw * sini
  const r32 = cosw * sini

  const position = {
    x: r11 * xOrb + r12 * yOrb,
    y: r21 * xOrb + r22 * yOrb,
    z: r31 * xOrb + r32 * yOrb,
  }
  const velocity = {
    x: r11 * vxOrb + r12 * vyOrb,
    y: r21 * vxOrb + r22 * vyOrb,
    z: r31 * vxOrb + r32 * vyOrb,
  }

  if (!Number.isFinite(position.x) || !Number.isFinite(position.y) || !Number.isFinite(position.z)) {
    throw new Error('Propagación orbital inválida')
  }
  return { position, velocity }
}

export function jday(date: Date): number {
  return date.getTime() / 86400000 + 2440587.5
}

export function gstime(date: Date): number {
  const jd = jday(date)
  const T = (jd - 2451545.0) / 36525.0
  const theta =
    67310.54841 +
    (876600 * 3600 + 8640184.812866) * T +
    0.093104 * T * T -
    6.2e-6 * T * T * T
  const rad = ((theta % 86400) / 86400) * 2 * Math.PI
  return normalizeAngle(rad)
}

export function eciToGeodetic(position: Vec3, gmst: number) {
  const ecef = eciToEcef(position, gmst)
  return ecefToGeodetic(ecef)
}

export function degreesLat(latitude: number): number {
  return rad2deg(latitude)
}

export function degreesLong(longitude: number): number {
  return rad2deg(longitude)
}

export function sunPos(jd: number): { rsun: Vec3 } {
  const n = jd - 2451545.0
  const L = normalizeAngle(deg2rad((280.460 + 0.9856474 * n) % 360))
  const g = normalizeAngle(deg2rad((357.528 + 0.9856003 * n) % 360))
  const lambda = L + deg2rad(1.915) * Math.sin(g) + deg2rad(0.020) * Math.sin(2 * g)
  const epsilon = deg2rad(23.439 - 0.0000004 * n)
  const r = 1.00014 - 0.01671 * Math.cos(g) - 0.00014 * Math.cos(2 * g)
  const x = r * Math.cos(lambda)
  const y = r * Math.cos(epsilon) * Math.sin(lambda)
  const z = r * Math.sin(epsilon) * Math.sin(lambda)
  return { rsun: { x, y, z } }
}
