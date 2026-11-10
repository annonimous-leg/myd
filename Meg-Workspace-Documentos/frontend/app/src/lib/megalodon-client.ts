/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

/**
 * Megalodon Client TypeScript v4
 * Cliente HTTP para el backend Megalodon CostOS
 */

export interface Token {
  access_token: string;
  token_type: string;
  refresh_token: string;
  expires_in: number;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
}

export interface DashboardStats {
  total_expedientes: number;
  expedientes_activos: number;
  expedientes_archivados: number;
  total_presupuestos: number;
  monto_total_comprometido: number;
  total_licitaciones: number;
  licitaciones_en_proceso: number;
  total_contratos: number;
  contratos_vigentes: number;
  total_proveedores: number;
  proveedores_activos: number;
  total_documentos: number;
  documentos_pendientes_firma: number;
}

export interface DashboardActivityItem {
  id: string;
  accion: string;
  entidad: string;
  usuario: string;
  fecha: string | null;
}

export interface DashboardResponse {
  stats: DashboardStats;
  kpis: { label: string; value: number; change_pct: number; trend: string }[];
  recent_activity: DashboardActivityItem[];
}

export interface HealthResponse {
  status: string;
  version: string;
  environment: string;
}

export interface ReadinessResponse {
  status: "ready" | "not_ready";
  database: boolean;
  redis: boolean;
  tezcatlipoca: boolean;
  ready: boolean;
  optional_dependencies: Record<string, string>;
}

export interface Expediente {
  id: string;
  identificador: string;
  titulo: string;
  estado: string;
  monto_contrato?: number;
  created_at: string;
  updated_at?: string;
  creado_por_id?: string;
  actualizado_por_id?: string;
}

// ── Documentos / CDE ────────────────────────────────────────────────────

export interface DocumentoCDE {
  id: string;
  nombre: string;
  descripcion?: string;
  tipo: string;
  estado: "BORRADOR" | "EN_REVISION" | "APROBADO" | "PUBLICADO" | "ARCHIVADO" | "OBSOLETO";
  version: number;
  expediente_id?: string;
  contenido_url?: string;
  hash_sha256?: string;
  firmado?: boolean;
  creado_por_id?: string;
  created_at?: string;
  metadatos?: Record<string, any>;
}

export interface WorkspaceDocumentSummary {
  id: string;
  artifact_code: string;
  name: string;
  status: string;
  version: number;
  media_type?: string;
}

export interface WorkspaceDocumentDetail extends WorkspaceDocumentSummary {
  media_type: string;
  content_text: string;
  content_model: Record<string, unknown>;
  row_version: number;
  locked: boolean;
  human_modified: boolean;
}

export interface WorkspaceDocumentRevision {
  version: number;
  operation: string;
  human_modified: boolean;
  content_text: string;
  created_at: string;
}

export interface WorkspaceEditor {
  id: string;
  version: number;
  row_version: number;
  locked: boolean;
  fields: { path: string; label: string; value: string; max_length: number; read_only: boolean }[];
  file_available: boolean;
  media_type: string;
  sha256: string | null;
  render_format: 'docx' | 'xlsx' | 'pdf';
  template_token: string | null;
}

export interface DocumentoDuplicado {
  documento_original_id: string;
  documento_duplicado_id: string;
  nombre: string;
  tipo: string;
  similitud: number;
}

export interface BusquedaDocumentosResultado {
  total: number;
  skip: number;
  limit: number;
  resultados: Array<{
    id: string;
    nombre: string;
    tipo: string;
    estado: string;
    version: number;
    expediente_id: string | null;
    creado_por_id: string | null;
    created_at: string | null;
    metadatos: Record<string, any> | null;
  }>;
}

export interface VersionDocumento {
  id: string;
  version: number;
  estado: string;
  contenido_url?: string;
  created_at?: string;
  creado_por_id?: string;
}

export interface EstadisticasDocumentales {
  total_documentos: number;
  total_versiones: number;
  por_tipo: Record<string, number>;
  por_estado: Record<string, number>;
  promedio_versiones: number;
}

export const TIPOS_DOCUMENTO = [
  "CONVOCATORIA", "BASES", "ANEXO_TECNICO", "ACTA", "FALLA", "CONTRATO",
  "ESTIMACION", "FACTURA", "PLANO", "REPORTE_FOTOGRAFICO", "OFICIO",
  "DICTAMEN", "RESOLUCION", "BIM_IFC", "BIM_BCF", "BIM_IDS", "OTRO",
] as const;

export const ESTADOS_DOCUMENTO = [
  "BORRADOR", "EN_REVISION", "APROBADO", "PUBLICADO", "ARCHIVADO", "OBSOLETO",
] as const;

// ── Compliance ──────────────────────────────────────────────────────────

export interface ReglaCumplimiento {
  id: string;
  nombre: string;
  descripcion?: string;
  tipo_procedimiento: string;
  etapa: string;
  obligatorio: boolean;
  activa: boolean;
  condicion_evaluacion?: string;
  created_at: string;
}

export interface ReglaCumplimientoInput {
  nombre: string;
  descripcion?: string;
  tipo_procedimiento: string;
  etapa: string;
  requisitos?: Record<string, any>;
  obligatorio?: boolean;
  activa?: boolean;
  condicion_evaluacion?: string;
}

export interface Inconformidad {
  id: string;
  expediente_id: string;
  licitacion_id?: string;
  contrato_id?: string;
  titulo: string;
  descripcion: string;
  // CORREGIDO (contra-auditoría V9): el backend ya expone estos 4 campos
  // desde la corrección de F-02 (ver InconformidadOut en
  // schemas/compliance.py) pero esta interfaz se había quedado con el
  // contrato viejo -- el frontend no podía ni tipar lo que el backend ya
  // mandaba.
  severidad?: "BAJA" | "MEDIA" | "ALTA" | "CRITICA";
  regla_id?: string;
  asignado_a?: string;
  fecha_limite?: string;
  estado: "REGISTRADA" | "EN_ANALISIS" | "RESPONDIDA" | "RESUELTA" | "ARCHIVADA";
  evidencia?: Record<string, any>;
  respuesta?: string;
  resolucion?: string;
  dictamen?: string;
  fecha_dictamen?: string;
  created_at: string;
}

export interface InconformidadInput {
  expediente_id: string;
  licitacion_id?: string;
  contrato_id?: string;
  titulo: string;
  descripcion: string;
  severidad?: "BAJA" | "MEDIA" | "ALTA" | "CRITICA";
  regla_id?: string;
  asignado_a?: string;
  fecha_limite?: string;
  evidencia?: Record<string, any>;
}

export interface Sancion {
  id: string;
  proveedor_id: string;
  expediente_id?: string;
  licitacion_id?: string;
  tipo: "INHABILITACION" | "MULTA" | "AMONESTACION" | "DESTITUCION";
  motivo: string;
  monto_multa?: number;
  expediente_sancionador?: string;
  hechos?: string;
  audiencia_fecha?: string;
  resolucion?: string;
  vigencia_inicio?: string;
  vigencia_fin?: string;
  estado: string;
  created_at: string;
}

export interface SancionInput {
  proveedor_id: string;
  expediente_id?: string;
  licitacion_id?: string;
  tipo: "INHABILITACION" | "MULTA" | "AMONESTACION" | "DESTITUCION";
  motivo: string;
  monto_multa?: number;
  expediente_sancionador?: string;
  hechos?: string;
  audiencia_fecha?: string;
  resolucion?: string;
  vigencia_inicio?: string;
  vigencia_fin?: string;
}

export interface EvaluacionComplianceResultado {
  expediente_id: string;
  total_reglas: number;
  cumplidas: number;
  incumplidas: number;
  score: number;
  detalle_cumplidas: Array<{ regla_id: string; nombre: string }>;
  detalle_incumplidas: Array<{ regla_id: string; nombre: string; obligatorio: boolean; motivo: string }>;
}

export const TIPOS_PROCEDIMIENTO_COMPLIANCE = [
  "LICITACION_PUBLICA", "INVITACION_RESTRINGIDA", "ADJUDICACION_DIRECTA",
] as const;

export const ETAPAS_COMPLIANCE = [
  "PLANEACION", "CONVOCATORIA", "PROPOSICIONES", "EVALUACION", "FALLO", "CONTRATO", "EJECUCION", "FINIQUITO",
] as const;

export const TIPOS_SANCION_COMPLIANCE = [
  "INHABILITACION", "MULTA", "AMONESTACION", "DESTITUCION",
] as const;

export const ESTADOS_INCONFORMIDAD = [
  "REGISTRADA", "EN_ANALISIS", "RESPONDIDA", "RESUELTA", "ARCHIVADA",
] as const;

// ═══════════════════════════════════════════════════════════════════════
// FASE 2 — CONTRATOS: dominio completo
// Antes todo el namespace `contratos` estaba tipado como `any` (ver más
// abajo). Se define aquí en forma real, espejando 1:1 los schemas Pydantic
// de backend/app/schemas/contrato.py, para que errores de forma se vean en
// compilación y no en producción -- mismo criterio ya aplicado a compliance.
// ═══════════════════════════════════════════════════════════════════════

export const ESTADOS_CONTRATO = [
  "EN_FIRMA", "VIGENTE", "EN_MODIFICACION", "SUSPENDIDO", "TERMINADO", "RESCINDIDO", "CERRADO",
] as const;

// Espejo exacto de ContratoService.TRANSICIONES (backend). Vive aquí para
// que la UI sepa qué botones de transición ofrecer sin una llamada extra;
// el backend sigue siendo quien valida de verdad en cada POST /transicionar.
export const TRANSICIONES_CONTRATO: Record<string, readonly string[]> = {
  EN_FIRMA: ["VIGENTE", "CERRADO"],
  VIGENTE: ["EN_MODIFICACION", "SUSPENDIDO", "TERMINADO", "RESCINDIDO"],
  EN_MODIFICACION: ["VIGENTE", "SUSPENDIDO", "RESCINDIDO"],
  SUSPENDIDO: ["VIGENTE", "RESCINDIDO"],
  TERMINADO: ["CERRADO"],
  RESCINDIDO: ["CERRADO"],
  CERRADO: [],
};

export const TIPOS_GARANTIA = ["CUMPLIMIENTO", "ANTICIPO", "VICIOS_OCULTOS", "ESTABILIDAD"] as const;
export const TIPOS_MODIFICACION = ["PLAZO", "MONTO", "ALCANCE", "PRECIO_UNITARIO"] as const;
export const TIPOS_PENALIZACION = ["ATRASO", "INCUMPLIMIENTO", "CALIDAD", "SEGURIDAD"] as const;

export interface Contrato {
  id: string;
  expediente_id: string;
  licitacion_id?: string;
  proveedor_id: string;
  numero_contrato: string;
  estado: typeof ESTADOS_CONTRATO[number];
  objeto: string;
  monto_total: number;
  monto_original?: number;
  plazo_dias: number;
  plazo_original?: number;
  fecha_firma?: string;
  fecha_inicio?: string;
  fecha_termino?: string;
  fecha_termino_original?: string;
  anticipo_otorgado: number;
  avance_fisico: number;
  avance_financiero: number;
  fecha_finiquito?: string;
  monto_finiquito?: number;
  created_at: string;
  updated_at: string;
}

export interface ContratoInput {
  expediente_id: string;
  licitacion_id?: string;
  proveedor_id: string;
  numero_contrato: string;
  objeto: string;
  monto_total: number;
  plazo_dias: number;
  fecha_firma?: string;
  fecha_inicio?: string;
  fecha_termino?: string;
  clausulas?: Record<string, any>;
  obligaciones?: Record<string, any>;
}

export interface Modificatorio {
  id: string;
  contrato_id: string;
  numero: string;
  tipo: typeof TIPOS_MODIFICACION[number];
  descripcion?: string;
  monto_anterior?: number;
  monto_nuevo?: number;
  plazo_anterior?: number;
  plazo_nuevo?: number;
  justificacion?: string;
  fecha_aprobacion?: string;
  created_at: string;
}

export interface ModificatorioInput {
  numero: string;
  tipo: typeof TIPOS_MODIFICACION[number];
  descripcion?: string;
  monto_anterior?: number;
  monto_nuevo?: number;
  plazo_anterior?: number;
  plazo_nuevo?: number;
  justificacion?: string;
}

export interface Garantia {
  id: string;
  contrato_id: string;
  tipo: typeof TIPOS_GARANTIA[number];
  monto: number;
  institucion?: string;
  numero_poliza?: string;
  vigencia_inicio?: string;
  vigencia_fin?: string;
  activa: boolean;
  liberada: boolean;
  ejecutada: boolean;
  fecha_liberacion?: string;
  created_at: string;
}

export interface GarantiaInput {
  tipo: typeof TIPOS_GARANTIA[number];
  monto: number;
  institucion?: string;
  numero_poliza?: string;
  vigencia_inicio?: string;
  vigencia_fin?: string;
}

export interface AlertaGarantia {
  garantia_id: string;
  tipo: string;
  numero_poliza?: string;
  vigencia_inicio?: string;
  vigencia_fin?: string;
  dias_restantes: number;
  estado: "VENCIDA" | "PROXIMA_A_VENCER" | "VIGENTE";
  contrato_id: string;
}

export interface Entregable {
  id: string;
  contrato_id: string;
  numero_estimacion: number;
  periodo_inicio?: string;
  periodo_fin?: string;
  monto_ejecutado: number;
  avance_fisico: number;
  avance_financiero: number;
  aprobado: boolean;
  fecha_aprobacion?: string;
  created_at: string;
}

export interface EntregableInput {
  numero_estimacion: number;
  periodo_inicio?: string;
  periodo_fin?: string;
  monto_ejecutado?: number;
  avance_fisico: number;
  avance_financiero?: number;
}

export interface Penalizacion {
  id: string;
  contrato_id: string;
  tipo: typeof TIPOS_PENALIZACION[number];
  monto: number;
  dias_atraso?: number;
  descripcion: string;
  tope_legal: number;
  dentro_tope: boolean;
  aplicada: boolean;
  fecha_aplicacion?: string;
  created_at: string;
}

export interface PenalizacionInput {
  tipo: typeof TIPOS_PENALIZACION[number];
  monto: number;
  dias_atraso?: number;
  descripcion: string;
  tope_legal: number;
}

export interface ResumenContrato {
  contrato_id: string;
  numero_contrato: string;
  estado: string;
  objeto: string;
  monto_original: number;
  monto_total: number;
  monto_modificaciones: number;
  monto_ejecutado: number;
  monto_pendiente: number;
  monto_penalizaciones: number;
  plazo_original: number | null;
  plazo_actual: number;
  plazo_modificaciones: number;
  total_modificatorios: number;
  total_garantias: number;
  total_entregables: number;
  total_penalizaciones: number;
  alertas_garantias: AlertaGarantia[];
}

export interface PuntoCurvaS {
  fecha: string;
  avance_plan_pct: number;
  avance_real_pct: number;
  costo_plan: number;
  costo_real: number;
  dias_transcurridos: number;
}

export interface RutaCriticaInfo {
  actividades: string[];
  duracion: number;
  fecha_inicio: string | null;
  fecha_fin: string | null;
}

export interface AeronaveTez {
  hex: string; callsign: string; lat: number; lon: number;
  altitude: number | null; track: number | null; speed: number | null; source: string;
  timestamp?: string | null;
}
export interface EmbarcacionTez {
  mmsi: string; name: string; lat: number; lon: number;
  sog: number | null; cog: number | null; source: string;
  timestamp?: string | null;
}
export interface SismoTez {
  id: string; lat: number; lon: number; magnitude: number;
  place: string; time: string | number | null; source: string;
}
export interface ContextoGeoTez {
  tenant_id: string | null;
  user_id: string | null;
  timestamp: string;
  bbox: [number, number, number, number];
  sources: {
    gnss: { status: string };
    adsb_exchange: { status: string };
    adsb_lol?: { status: string; last_success?: string | null; coverage?: string; license?: string; attribution?: string };
    ais: { status: string };
    usgs: { status: string };
    telemetry: { status: string; sources: string[]; metrics: Record<string, unknown> };
  };
  aircraft: AeronaveTez[];
  ships: EmbarcacionTez[];
  earthquakes: SismoTez[];
}

export interface ModeloBIM {
  id: string;
  identificador: string;
  nombre: string;
  descripcion?: string;
  expediente_id: string;
  estado_procesamiento: "PENDIENTE" | "EN_PROCESO" | "COMPLETADO" | "ERROR";
  num_elementos: number;
  creado_por_id?: string;
  /** Nombres de IfcBuildingStorey ordenados de abajo hacia arriba --
   * úsalo para armar el selector de nivel sin tener que pedir todos los
   * elementos primero. */
  niveles?: string[];
  version_ifc?: string;
  error_procesamiento?: string;
}

export interface ElementoBIM {
  id: string;
  modelo_id: string;
  global_id: string;
  tipo: string;
  nombre?: string;
  volumen?: number;
  area?: number;
  longitud?: number;
  /** De dónde salió el dato: "QTO_IFC" (confiable, viene del propio IFC)
   * o "GEOMETRIA_CALCULADA" (aproximado, calculado desde la malla). */
  fuente_volumen: "QTO_IFC" | "GEOMETRIA_CALCULADA" | "NO_DISPONIBLE";
  fuente_area: "QTO_IFC" | "GEOMETRIA_CALCULADA" | "NO_DISPONIBLE";
  /** Nombre del IfcBuildingStorey que lo contiene, si el IFC lo define. */
  nivel?: string;
  /** Agrupación de trabajo para 4D, editable vía zonas4d() -- independiente
   * de `nivel` (que viene fijo del IFC). Si no se asigna, generar4D5D()
   * agrupa por `nivel`. */
  zona_4d?: string;
  /** [minX, minY, minZ, maxX, maxY, maxZ] en metros, coords de mundo. */
  bbox?: [number, number, number, number, number, number];
  partida_id?: string;
  /** Solo viene poblado si se pidió incluirMalla=true al listar. */
  malla_vertices?: number[];
  malla_caras?: number[];
}

export interface AnalisisClash {
  id: string;
  modelo_id: string;
  tolerancia_m: number;
  // Comparte el enum EstadoProceso con ModeloBIM.estado_procesamiento
  // (antes eran dos enums paralelos con nombres de valor distintos).
  estado: "PENDIENTE" | "EN_PROCESO" | "COMPLETADO" | "ERROR";
  num_pares_evaluados: number;
  num_clashes_duros: number;
  num_clashes_blandos: number;
  tiempo_calculo_ms?: number;
  error?: string;
  creado_por_id?: string;
}

export interface GeneracionBIM4D5D {
  id: string;
  modelo_id: string;
  expediente_id: string;
  programa_id?: string;
  estado: "PENDIENTE" | "EN_PROCESO" | "COMPLETADO" | "ERROR";
  error?: string;
  agrupar_por: string;
  dias_por_defecto: number;
  num_actividades_generadas?: number;
}

export interface ConceptoLibro {
  id: string;
  descripcion: string;
  unidad: string;
  precio_unitario: string | null;
  modelo_id: string;
  pagina: string;
  supuesto: string;
  utilizable: boolean;
  bloqueo: string | null;
  fuente: string;
  sha256: string;
  fila_csv: number;
}

export interface CatalogoAPUOut {
  id: string;
  clave: string;
  descripcion: string;
  tipo: string;
  unidad: string;
  precio_unitario: number;
  fuente: string;
  fuente_visible?: string;
  zona_economica?: string;
  estado?: string;
  incluye_iva: boolean;
  vigencia_inicio?: string | null;
  origen?: { importacion_id: string; revision: string; fuente: { titulo: string; sha256: string }; paginas: string[] } | null;
}

export interface CatalogoImportacionOut {
  id: string; paquete_sha256: string; fuentes: string[];
  fuentes_visibles?: string[];
  resumen: { registros: number; estados: Record<string, number>; cuarentena_motivos: Record<string, number>; proyecciones_costeo: number; fuentes_visibles?: Record<string, string> };
}
export interface CatalogoRegistroOut {
  id: string; tabla: string; fuente_id: string; entidad_id: string; estado: string; motivos: string[]; original: Record<string, string>; sha256: string;
}

export interface ClashResult {
  id: string;
  analisis_id: string;
  elemento_a_id: string;
  elemento_b_id: string;
  tipo_a: string;
  tipo_b: string;
  /** DURO: las mallas se traslapan de verdad. BLANDO: no se tocan pero
   * están más cerca que la tolerancia usada en el análisis. */
  severidad: "DURO" | "BLANDO";
  distancia_m: number;
  /** Volumen de la intersección de los dos AABB -- aproximado, NO un
   * booleano exacto de las mallas. Útil para priorizar severidad. */
  volumen_aproximado_m3?: number;
  punto_cercano_a: [number, number, number];
  punto_cercano_b: [number, number, number];
  /** Hasta 30 triángulos por lado [[x,y,z]x3, ...], listos para
   * resaltarse en Three.js sin pedir la malla completa del elemento. */
  triangulos_a?: number[][][];
  triangulos_b?: number[][][];
  estado: "NUEVO" | "REVISADO" | "RESUELTO" | "IGNORADO";
}

export interface FiscalInput {
  opinion_sat_sentido?: string;
  opinion_sat_fecha?: string; // YYYY-MM-DD
  opinion_imss_sentido?: string;
  opinion_infonavit_sentido?: string;
}

export interface AnalisisFSRInput {
  tp_dias_pagados?: number;
  tl_dias_laborados?: number;
  ps_fraccion_imss_infonavit?: number;
  fsr_calculado_por_licitante?: number;
}

export interface AnalisisMaquinariaInput {
  codigo_equipo?: string;
  cargo_combustible?: number;
  precio_litro_combustible_declarado?: number;
  cargo_operacion?: number;
  costo_horario_total?: number;
  total_cargos_fijos?: number;
  cargo_lubricantes?: number;
  horas_uso_anual?: number;
  requiere_combustible?: boolean;
}

export interface AnalisisSobrecostosInput {
  pct_indirecto_oficina?: number;
  pct_indirecto_campo?: number;
  pct_utilidad?: number;
  pct_financiamiento?: number;
  pct_cargos_adicionales?: number;
  factor_sobrecosto_total_declarado?: number;
  tasa_interes_utilizada?: number;
}

export interface PropuestaLicitacion {
  rfc_empresa?: string;
  fiscal?: FiscalInput;
  administrativo?: { efirma_valida?: boolean };
  economico?: {
    analisis_fsr?: AnalisisFSRInput;
    analisis_maquinaria?: AnalisisMaquinariaInput;
    analisis_sobrecostos?: AnalisisSobrecostosInput;
  };
  tecnico?: { incongruencias_detectadas?: string[] };
  garantias?: Array<{ tipo: string; monto?: number }>;
  fecha_fallo?: string;
  requisitos_participacion?: string[];
}

export interface ResultadoRegla {
  id_regla: string;
  seccion: string;
  estatus: 'PASA' | 'FALLA' | 'NO_APLICA';
  valor_detectado: string;
  valor_esperado: string;
  evidencia: string;
}

export interface ValidacionPropuesta {
  id: string;
  expediente_id: string;
  rfc_empresa?: string;
  estado: 'SOLVENTE' | 'DESCALIFICADO';
  bitacora_evaluacion: ResultadoRegla[];
  created_at?: string;
  creado_por_id?: string;
}

export interface Levantamiento {
  id: string;
  expediente_id: string;
  identificador: string;
  nombre: string;
  descripcion?: string;
  crs: string;
  srid: number;
  creado_por_id?: string;
}

export interface PuntoTopografico {
  id: string;
  identificador: string;
  etiqueta?: string;
  x: number;
  y: number;
  z?: number;
}

export interface SuperficieTIN {
  id: string;
  /** Denormalizado (además de levantamiento_id) para no tener que
   * caminar superficie->levantamiento->expediente al validar pertenencia. */
  expediente_id: string;
  levantamiento_id: string;
  nombre: string;
  tipo: "EXISTENTE" | "PROYECTO";
  /** [x1,y1,z1, x2,y2,z2, ...] en metros -- mismo formato que la malla
   * de ElementoBIM, listo para THREE.BufferGeometry. */
  malla_vertices: number[];
  malla_caras: number[];
  area_plan_m2: number;
  area_superficie_m2: number;
  elevacion_min: number;
  elevacion_max: number;
  elevacion_media: number;
  pendiente_media_pct: number;
  num_puntos: number;
  num_triangulos: number;
  creado_por_id?: string;
}

export interface CoberturaTopografia {
  completa: boolean;
  area_existente_m2: number;
  area_proyecto_m2: number;
  area_comun_m2: number;
  area_existente_pendiente_m2: number;
  area_proyecto_pendiente_m2: number;
}

export interface EvidenciaTopografia {
  version: number;
  calculo_id: string;
  sha256: string;
  cobertura: CoberturaTopografia;
  existente: { superficie_id: string; levantamiento_id: string; crs: string; malla_sha256: string };
  proyecto: EvidenciaTopografia['existente'] | null;
}

export interface CalculoVolumen {
  id: string;
  /** Denormalizado, mismo motivo que en SuperficieTIN. */
  expediente_id: string;
  superficie_existente_id: string;
  superficie_proyecto_id?: string;
  elevacion_referencia?: number;
  volumen_corte_m3: number;
  volumen_terraplen_m3: number;
  volumen_neto_m3: number;
  area_analizada_m2: number;
  evidencia?: EvidenciaTopografia | null;
  creado_por_id?: string;
}

export interface PuntoPerfil {
  cadenamiento: number;
  x: number;
  y: number;
  elevacion: number;
}

export interface ResultadoCierrePoligonal {
  error_cierre_m: number;
  perimetro_m: number;
  precision_relativa: string;
  dentro_tolerancia: boolean;
}

export interface Programa {
  id: string;
  identificador: string;
  nombre: string;
  descripcion?: string;
  expediente_id: string;
  fecha_inicio_plan: string;
  fecha_fin_plan?: string;
  duracion_plan_dias: number;
  // Antes era `string` libre -- el backend no tenía Enum tampoco.
  estado: "PLANIFICADO" | "EN_EJECUCION" | "PAUSADO" | "COMPLETADO" | "CANCELADO";
  creado_por_id?: string;
}

export interface Actividad {
  id: string;
  identificador: string;
  nombre: string;
  descripcion?: string;
  wbs_codigo: string;
  wbs_nivel: number;
  duracion: number;
  tipo: string;
  costo_presupuestado: number;
  costo_real: number;
  porcentaje_avance: number;
  inicio_temprano?: string;
  fin_temprano?: string;
  inicio_tardio?: string;
  fin_tardio?: string;
  holgura_total: number;
  holgura_libre: number;
  en_ruta_critica: boolean;
  predecesoras?: string[];
  dependencias_tipo?: Record<string, string>;
}

export interface ActividadInput {
  id: string;
  nombre: string;
  descripcion?: string;
  wbs_codigo?: string;
  wbs_nivel?: number;
  duracion: number;
  duracion_optimista?: number;
  duracion_probable?: number;
  duracion_pesimista?: number;
  tipo?: string;
  costo_presupuestado?: number;
  costo_real?: number;
  porcentaje_avance?: number;
  predecesoras?: string[];
  dependencias_tipo?: Record<string, string>;
  metadatos?: Record<string, any>;
}

export interface ResultadoCPM {
  duracion_total: number;
  ruta_critica: {
    actividades: string[];
    duracion: number;
    fecha_inicio: string | null;
    fecha_fin: string | null;
  };
  actividades: Record<string, {
    nombre: string;
    duracion: number;
    inicio_temprano: string | null;
    fin_temprano: string | null;
    inicio_tardio: string | null;
    fin_tardio: string | null;
    holgura_total?: number;
    en_ruta_critica?: boolean;
  }>;
}

export interface ResultadoPERT {
  duracion_esperada: number;
  varianza_total: number;
  desviacion_estandar: number;
  probabilidad_terminar_a_tiempo: number;
  fecha_probable_terminacion: string | null;
  percentiles: Record<string, number>;
}

export interface ResultadoEVM {
  pv: number; // Planned Value
  ev: number; // Earned Value
  ac: number; // Actual Cost
  sv: number; // Schedule Variance
  cv: number; // Cost Variance
  spi: number; // Schedule Performance Index
  cpi: number; // Cost Performance Index
  eac: number; // Estimate at Completion
  etc: number; // Estimate to Complete
  vac: number; // Variance at Completion
  tcpi: number;
  interpretacion: {
    cronograma: 'ADELANTADO' | 'ATRASADO' | 'A_TIEMPO';
    costo: 'BAJO_PRESUPUESTO' | 'SOBRE_PRESUPUESTO' | 'A_PRESUPUESTO';
  };
}

export interface InsumoPresupuesto {
  id: string;
  clave: string;
  descripcion: string;
  tipo: string;
  unidad: string;
  cantidad: number;
  precio_unitario: number;
  importe: number;
  rendimiento: number;
  actualizacion_precio?: ActualizacionPrecioSnapshot | null;
}

export interface SolicitudActualizacionPrecio {
  vinculo_id: string;
  observacion_base_id: string;
  observacion_destino_id: string;
}

export class MegalodonApiError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
    this.name = 'MegalodonApiError';
  }
}

export interface EvidenciaIndice {
  url: string;
  sha256: string;
  localizador: string;
}

export interface InventarioCatalogos {
  total_fuentes: number;
  total_conceptos: number;
  total_insumos: number;
  vinculos_activos_tenant: number;
  revision_documental_certificada: false;
  fuentes: Array<{
    id: string; nombre: string; nombre_visible?: string; activo: boolean; moneda: string | null;
    vigencia_inicio: string; vigencia_fin: string;
    conceptos: number; conceptos_activos: number;
    insumos: number; insumos_activos: number; materiales_sin_iva_mxn: number;
  }>;
}

export interface CoberturaCorpus {
  sha256: string;
  total_articulos_consultables: number;
  vigencia_certificada: false;
  alcance: string;
  documentos_sin_articulos: string[];
  documentos: Array<{
    nombre: string; articulos_segmentados: number; articulos_consultables: number;
    conteo_declarado: number; conteo_declarado_coincide: boolean;
    numeros_no_segmentados: number[];
  }>;
}

export interface ObservacionIndice {
  id: string;
  serie_id: string;
  mes: string;
  valor: string;
  publicado_el: string;
  documento_sha256: string;
  evidencia: EvidenciaIndice;
  revision_captura: number;
}

export interface VinculoIndice {
  id: string;
  serie_id: string;
  mes_base: string;
  precio_original: string;
  fundamento: string;
  insumo_original: { clave: string; descripcion: string; unidad: string; tipo: string; moneda: string };
}

export interface ActualizacionPrecioSnapshot {
  version: 1;
  tipo: 'ESTIMACION_OBSERVADA';
  precio_original: string;
  precio_actualizado: string;
  sha256: string;
  vinculo: VinculoIndice;
  serie: { id: string; codigo: string; nombre: string; region: string };
  base: ObservacionIndice;
  destino: ObservacionIndice;
}

export interface ConceptoPresupuesto {
  id: string;
  clave: string;
  descripcion: string;
  unidad: string;
  cantidad: number;
  costo_directo_unitario: number;
  insumos: InsumoPresupuesto[];
}

export interface Partida {
  id: string;
  numero: number;
  descripcion: string;
  unidad: string;
  cantidad: number;
  precio_unitario: number;
  importe: number;
  metadatos?: {
    catalogo_asignado?: { catalogo_id: string; descripcion: string; fuente: string;
      vigencia_inicio: string | null; precio_observado: string; precio_aplicado: string };
    [key: string]: unknown;
  };
  conceptos: ConceptoPresupuesto[];
}

export interface Presupuesto {
  id: string;
  identificador: string;
  nombre: string;
  descripcion?: string;
  expediente_id: string;
  // No existía ningún campo de estado -- se agregó en esta ronda de
  // unificación del modelo de datos.
  estado: "BORRADOR" | "CALCULADO" | "VALIDADO" | "RECHAZADO" | "APROBADO";
  monto_directo: number;
  monto_indirecto: number;
  monto_financiamiento: number;
  monto_utilidad: number;
  monto_riesgo?: number | null;
  monto_cargos_adicionales: number;
  monto_impuesto: number;
  monto_total: number;
  moneda: string;
  factor_indirecto: number;
  factor_financiamiento: number;
  factor_utilidad: number;
  factor_cargos_adicionales: number;
  factor_impuesto: number;
  factor_riesgo?: number | null;
  metadatos?: {
    parametros_costeo?: ParametrosCosteoSnapshot;
    topografia_cobertura?: CoberturaTopografia;
    topografia_evidencia?: EvidenciaTopografia;
    bim_cobertura?: { completa: boolean; elementos_totales: number; elementos_medidos: number;
      elementos_pendientes: string[]; capturas: Array<{ elemento_id: string; unidad: string;
        cantidad: number; referencia: string; usuario_id: string; capturado_en: string }> };
    [key: string]: unknown;
  } | null;
  zona_economica: string;
  // FIX auditoría BIM/mapear-partidas 2026-09-14: el backend
  // (PresupuestoOut en app/api/v1/presupuestos.py) ya incluía las
  // partidas anidadas con sus conceptos/insumos; este tipo TS no las
  // declaraba, así que cualquier código que quisiera usarlas para armar
  // un selector de partidas (ej. mapear elemento BIM -> partida real) no
  // tenía forma de saber que existían sin leer el backend directamente.
  partidas: Partida[];
  created_at?: string;
  creado_por_id?: string;
}

export interface ParametrosCosteoInput {
  factor_indirecto: number;
  factor_financiamiento?: number;
  factor_utilidad: number;
  factor_cargos_adicionales?: number;
  factor_impuesto: number;
  factor_riesgo: number;
  fuente: "CAPTURA_USUARIO" | "CONTRATO" | "PERFIL_TENANT" | "CONVOCATORIA" | "TENDER_SNAPSHOT";
  referencia: string;
  vigencia?: string;
  jurisdiccion?: string;
  evidencia?: Record<string, unknown>;
}

export type ParametrosCosteoSnapshot = Omit<ParametrosCosteoInput, "vigencia" | "jurisdiccion" | "evidencia"> & {
  sha256: string;
  vigencia?: string | null;
  jurisdiccion?: string | null;
  evidencia: Record<string, unknown>;
};

export interface ResultadoJuridico {
  procedimiento: "ADJUDICACION_DIRECTA" | "INVITACION_TRES" | "LICITACION_PUBLICA" | "SIN_DETERMINAR";
  tipo_contratacion: string;
  jurisdiccion?: string;
  ejercicio_fiscal?: number;
  marcos_legales: Array<{
    ley: string;
    articulos: string[];
    reglamento?: string;
  }>;
  requisitos: Array<{
    codigo: string;
    descripcion: string;
    obligatorio: boolean;
  }>;
  umbrales: Record<string, number | null>;
  observaciones: string[];
  valido: boolean;
  /** false = no hay umbral cargado (SIN_DETERMINAR) para esta
   * jurisdicción/año, o el umbral es solo "candidato" (ver es_candidato). */
  datos_verificados: boolean;
  /** true = el umbral usado fue citado por investigación pero sin
   * confirmar contra la fuente oficial primaria -- mostrar advertencia
   * visible al usuario, no usar como única base de una decisión real. */
  es_candidato?: boolean;
  fuente_umbral?: string;
}

// ─── Validadores de propuesta de licitación (app/api/v1/validadores.py) ───
// Espejo exacto del payload que espera POST /{expediente_id}/evaluar-completo.

export interface PropuestaLicitacionData {
  rfc_empresa?: string;
  fiscal?: {
    opinion_sat_sentido?: string;
    opinion_sat_fecha?: string; // YYYY-MM-DD
    opinion_imss_sentido?: string;
    opinion_infonavit_sentido?: string;
  };
  administrativo?: { efirma_valida?: boolean };
  economico?: {
    analisis_fsr?: {
      tp_dias_pagados?: number;
      tl_dias_laborados?: number;
      ps_fraccion_imss_infonavit?: number;
      fsr_calculado_por_licitante?: number;
    };
    analisis_maquinaria?: {
      codigo_equipo?: string;
      cargo_combustible?: number;
      precio_litro_combustible_declarado?: number;
      cargo_operacion?: number;
      costo_horario_total?: number;
      total_cargos_fijos?: number;
      cargo_lubricantes?: number;
      horas_uso_anual?: number;
      requiere_combustible?: boolean;
    };
    analisis_sobrecostos?: {
      pct_indirecto_oficina?: number;
      pct_indirecto_campo?: number;
      pct_utilidad?: number;
      pct_financiamiento?: number;
      pct_cargos_adicionales?: number;
      factor_sobrecosto_total_declarado?: number;
      tasa_interes_utilizada?: number;
    };
  };
  tecnico?: { incongruencias_detectadas?: string[] };
  garantias?: Array<{ tipo: string; monto?: number }>;
  fecha_fallo?: string;
  requisitos_participacion?: string[];
}

export interface ResultadoReglaValidador {
  id_regla: string;
  seccion: string;
  estatus: "PASA" | "FALLA" | "NO_APLICA";
  valor_detectado: string;
  valor_esperado: string;
  evidencia: string;
}

export interface ValidacionResultado {
  id: string;
  expediente_id: string;
  proposicion_id?: string;
  rfc_empresa?: string;
  estado: string;
  bitacora_evaluacion: ResultadoReglaValidador[];
  created_at?: string;
}

export interface ResultadoMonteCarlo {
  media: number;
  mediana: number;
  desviacion: number;
  minimo: number;
  maximo: number;
  percentil_5: number;
  percentil_95: number;
  prob_exceder_presupuesto: number;
  ic_95: [number, number];
}

export interface MetradoOCR {
  concepto: string;
  descripcion: string;
  unidad: string;
  cantidad: number;
  confianza: number;
  pagina: number;
  texto_original: string;
}

export interface TaskStatus {
  task_id: string;
  status: string;
  result?: any;
  error?: string;
}

export interface WebSocketMessage {
  type: "progress" | "complete" | "status" | "pong" | "error";
  task_id?: string;
  progress?: number;
  status?: string;
  result?: any;
  error?: string;
  message?: string;
  timestamp?: number;
}

export type SolicitudPlanoBIM = { titulo: string } & (
  | { tipo: "PLAN"; parametros: { elevacion_m: number } }
  | { tipo: "SECTION"; parametros: { origen_m: [number, number, number]; normal: [number, number, number] } }
  | { tipo: "ELEVATION"; parametros: { direccion_vista: [number, number, number]; mostrar_ocultas?: boolean } }
);

export class MegalodonClient {
  private baseUrl: string;
  private token: string | null = null;
  private ws: WebSocket | null = null;
  private wsCallbacks: Map<string, ((msg: WebSocketMessage) => void)[]> = new Map();

  constructor(baseUrl: string = "http://localhost:8000") {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  setToken(token: string) {
    this.token = token;
  }

  private sessionRefresh: Promise<void> | null = null;

  private async fetchWithSession(url: string, config: RequestInit): Promise<Response> {
    const response = await fetch(url, config);
    const path = url.slice(this.baseUrl.length);
    const sessionRoute = path.startsWith('/api/v1/auth/') && path !== '/api/v1/auth/me';
    if (response.status !== 401 || this.token || sessionRoute) return response;
    if (!this.sessionRefresh) {
      this.sessionRefresh = this.auth.refresh().then(() => undefined).finally(() => {
        this.sessionRefresh = null;
      });
    }
    try { await this.sessionRefresh; } catch { return response; }
    return fetch(url, config);
  }

  private async requestRoot<T>(path: string): Promise<T> {
    const headers: Record<string, string> = {};
    if (this.token) headers.Authorization = `Bearer ${this.token}`;
    const response = await this.fetchWithSession(`${this.baseUrl}${path}`, {
      method: "GET",
      headers,
      credentials: "include",
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: `HTTP ${response.status}: ${response.statusText}` }));
      throw new Error(error.detail || error.message || `HTTP ${response.status}`);
    }
    return response.json() as Promise<T>;
  }

  private async requestTez<T>(
    method: string,
    path: string,
    body?: any,
    options: RequestInit = {},
  ): Promise<T> {
    const url = `${this.baseUrl}/api/tezcatlipoca${path}`;
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...((options.headers as Record<string, string>) || {}),
    };
    if (this.token) headers["Authorization"] = `Bearer ${this.token}`;
    const config: RequestInit = { method, headers, credentials: "include", ...options };
    if (body !== undefined && !(body instanceof FormData) && !(body instanceof URLSearchParams)) {
      config.body = JSON.stringify(body);
    } else if (body) {
      config.body = body;
      if (!(body instanceof URLSearchParams)) delete headers["Content-Type"];
    }
    const response = await this.fetchWithSession(url, config);
    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: `HTTP ${response.status}: ${response.statusText}` }));
      throw new Error(error.detail || error.message || `HTTP ${response.status}`);
    }
    if (response.status === 204) return undefined as T;
    return response.json();
  }

  private async request<T>(
    method: string,
    path: string,
    body?: any,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}/api/v1${path}`;
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...((options.headers as Record<string, string>) || {}),
    };

    if (this.token) {
      headers["Authorization"] = `Bearer ${this.token}`;
    }

    const config: RequestInit = {
      ...options,
      method,
      headers,
      credentials: 'include',
    };

    if (body && !(body instanceof FormData) && !(body instanceof URLSearchParams)) {
      config.body = JSON.stringify(body);
    } else if (body) {
      // FormData y URLSearchParams se mandan tal cual.
      // BUG ORIGINAL: URLSearchParams (usado por auth.login) no estaba
      // contemplado aquí, así que caía en la rama de JSON.stringify().
      // JSON.stringify(new URLSearchParams(...)) da "{}" (no tiene
      // propiedades enumerables propias), así que el login SIEMPRE
      // mandaba un body vacío y nunca podía autenticar a nadie.
      config.body = body;
      if (!(body instanceof URLSearchParams)) {
        delete headers["Content-Type"];
      }
    }

    const response = await this.fetchWithSession(url, config);

    if (!response.ok) {
      const error = await response.json().catch(() => ({
        message: `HTTP ${response.status}: ${response.statusText}`,
      }));
      throw new MegalodonApiError(error.message || `HTTP ${response.status}`, response.status);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return response.json();
  }

  health = {
    live: async (): Promise<HealthResponse> => this.requestRoot<HealthResponse>("/health"),
    ready: async (): Promise<ReadinessResponse> => this.requestRoot<ReadinessResponse>("/ready"),
  };

  auth = {
    login: async (username: string, password: string): Promise<{ expires_in: number }> => {
      this.setToken("");
      const formData = new URLSearchParams({ username, password });
      return this.request("POST", "/auth/session/login", formData, {
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      });
    },

    register: async (data: {
      email: string;
      password: string;
      full_name: string;
      company_name: string;
      company_slug?: string;
      company_rfc?: string;
    }): Promise<User> => {
      return this.request<User>("POST", "/auth/register", data);
    },

    refresh: async (): Promise<{ expires_in: number }> => {
      return this.request("POST", "/auth/session/refresh");
    },

    logout: async (): Promise<void> => {
      if (this.sessionRefresh) await this.sessionRefresh.catch(() => undefined);
      await this.request<void>("POST", "/auth/logout");
      this.setToken("");
    },

    me: async (): Promise<User> => {
      return this.request<User>("GET", "/auth/me");
    },
  };

  dashboard = {
    stats: async (): Promise<DashboardResponse> => {
      return this.request<DashboardResponse>("GET", "/dashboard/stats");
    },
  };

  expedientes = {
    list: async (params?: {
      skip?: number;
      limit?: number;
      estado?: string;
      query?: string;
    }): Promise<Expediente[]> => {
      const searchParams = new URLSearchParams();
      if (params?.skip) searchParams.append("skip", String(params.skip));
      if (params?.limit) searchParams.append("limit", String(params.limit));
      if (params?.estado) searchParams.append("estado", params.estado);
      if (params?.query) searchParams.append("query", params.query);
      return this.request<Expediente[]>("GET", `/expedientes?${searchParams}`);
    },

    get: async (id: string): Promise<Expediente> => {
      return this.request<Expediente>("GET", `/expedientes/${id}`);
    },

    create: async (data: {
      titulo: string;
      organo: string;
      unidad_administrativa: string;
      serie_documental: string;
      subserie_documental: string;
      descripcion?: string;
      proyecto_nombre?: string;
      ubicacion_obra?: string;
      monto_contrato?: number;
      plazo_dias?: number;
      tipo_contrato?: string;
      responsable_tecnico?: string;
      responsable_ejecutivo?: string;
    }): Promise<Expediente> => {
      return this.request<Expediente>("POST", "/expedientes", data);
    },

    cambiarEstado: async (id: string, estado: string, observacion?: string): Promise<Expediente> => {
      return this.request<Expediente>("PATCH", `/expedientes/${id}/estado?estado=${estado}`, { observacion });
    },

    subirDocumento: async (id: string, file: File, tipo_documental: string, cifrar: boolean = false): Promise<any> => {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("tipo_documental", tipo_documental);
      formData.append("cifrar", String(cifrar));
      return this.request<any>("POST", `/expedientes/${id}/documentos`, formData);
    },

    listarDocumentos: async (id: string, skip = 0): Promise<Array<{
      id: string; nombre: string; tipo_documental: string; row_version: number;
    }>> => this.request("GET", `/expedientes/${id}/documentos?skip=${skip}&limit=100`),

    /** Antes no existía -- el backend nunca exponía cómo bajar un
     * documento ya subido. Regresa el blob listo para descargar o mostrar. */
    descargarDocumento: async (expedienteId: string, documentoId: string): Promise<Blob> => {
      const response = await fetch(
        `${this.baseUrl}/api/v1/expedientes/${expedienteId}/documentos/${documentoId}/descarga`,
        {
          headers: this.token ? { Authorization: `Bearer ${this.token}` } : {},
          credentials: 'include',
        }
      );
      if (!response.ok) throw new Error("Error al descargar documento");
      return response.blob();
    },
  };

  catalogoLibro = {
    buscar: (q: string, skip = 0): Promise<{total: number; items: ConceptoLibro[]}> =>
      this.request("GET", `/catalogo-libro?${new URLSearchParams({q, skip: String(skip), limit: '50'})}`),
  };

  indicesCostos = {
    inventario: (skip = 0): Promise<InventarioCatalogos> =>
      this.request('GET', `/indices-costos/inventario?skip=${skip}&limit=50`),
    vinculos: (skip = 0): Promise<VinculoIndice[]> =>
      this.request('GET', `/indices-costos/vinculos?skip=${skip}&limit=50`),
    observaciones: (serieId: string, skip = 0): Promise<ObservacionIndice[]> =>
      this.request('GET', `/indices-costos/observaciones?${new URLSearchParams({ serie_id: serieId, skip: String(skip), limit: '500' })}`),
    calcular: (solicitud: SolicitudActualizacionPrecio): Promise<ActualizacionPrecioSnapshot> =>
      this.request('POST', '/indices-costos/calcular', solicitud),
    seleccionarPublicacion: (vinculoId: string, fechaCorte: string): Promise<{
      fecha_corte: string; solicitud: SolicitudActualizacionPrecio;
      snapshot: ActualizacionPrecioSnapshot; variacion_porcentaje: string;
    }> => this.request('POST', '/indices-costos/seleccionar-publicacion', {
      vinculo_id: vinculoId, fecha_corte: fechaCorte,
    }),
  };

  presupuestos = {
    crearRevision: (expedienteId: string, presupuestoId: string, motivo: string): Promise<Presupuesto> =>
      this.request('POST', `/presupuestos/${expedienteId}/presupuestos/${presupuestoId}/revisiones`, { motivo }),
    actualizarCantidad: (expedienteId: string, presupuestoId: string, partidaId: string, cantidad: number): Promise<Presupuesto> =>
      this.request('PATCH', `/presupuestos/${expedienteId}/presupuestos/${presupuestoId}/partidas/${partidaId}`, { cantidad }),
    eliminarPartida: (expedienteId: string, presupuestoId: string, partidaId: string): Promise<Presupuesto> =>
      this.request('DELETE', `/presupuestos/${expedienteId}/presupuestos/${presupuestoId}/partidas/${partidaId}`),
    create: async (expedienteId: string, data: {
      nombre: string;
      descripcion?: string;
      partidas: Array<{
        catalogo_apu_id?: string;
        catalogo_libro_id?: string;
        numero: number;
        descripcion: string;
        unidad: string;
        cantidad: number;
        /** Solo requerido si la partida NO trae `conceptos` (caso
         * tabulador: precio ya resuelto de un catálogo oficial). Si trae
         * `conceptos`, el precio se calcula en el backend y este campo
         * se ignora. */
        precio_unitario?: number;
        /** Insumos sueltos a nivel partida (atajo para un solo concepto
         * implícito). No se usa si ya mandas `conceptos`. */
        insumos?: any[];
        /** APU real: cada concepto trae SUS PROPIOS insumos anidados. */
        conceptos?: Array<{
          clave: string;
          descripcion: string;
          unidad: string;
          cantidad?: number;
          insumos: Array<{
            clave: string;
            descripcion: string;
            tipo: "MATERIAL" | "MANO_OBRA" | "EQUIPO" | "SUBCONTRATO" | "HERRAMIENTA";
            unidad: string;
            cantidad: number;
            precio_unitario: number;
            rendimiento?: number;
          }>;
        }>;
      }>;
      parametros_costeo: ParametrosCosteoInput;
      zona_economica?: string;
    }): Promise<Presupuesto> => {
      return this.request<Presupuesto>("POST", `/presupuestos/${expedienteId}/presupuestos`, data);
    },

    list: async (expedienteId: string): Promise<Presupuesto[]> => {
      return this.request<Presupuesto[]>("GET", `/presupuestos/${expedienteId}/presupuestos`);
    },

    recalcular: async (expedienteId: string, presupuestoId: string): Promise<Presupuesto> => {
      return this.request<Presupuesto>("POST", `/presupuestos/${expedienteId}/presupuestos/${presupuestoId}/recalcular`);
    },
    asignarCatalogoPartida: async (expedienteId: string, presupuestoId: string, partidaId: string, catalogoId: string): Promise<Presupuesto> => {
      return this.request<Presupuesto>('PUT', `/presupuestos/${expedienteId}/presupuestos/${presupuestoId}/partidas/${partidaId}/catalogo`,
        { catalogo_apu_id: catalogoId });
    },

    actualizarParametrosCosteo: async (
      expedienteId: string, presupuestoId: string, parametrosCosteo: ParametrosCosteoInput,
    ): Promise<Presupuesto> => {
      return this.request<Presupuesto>(
        "PUT",
        `/presupuestos/${expedienteId}/presupuestos/${presupuestoId}/parametros-costeo`,
        { parametros_costeo: parametrosCosteo },
      );
    },

    /** No existía ningún mecanismo para marcar un presupuesto como
     * validado/aprobado/rechazado -- el campo `estado` tampoco existía
     * antes de esta ronda de unificación del modelo de datos. Transiciones
     * válidas: BORRADOR->CALCULADO->VALIDADO->APROBADO, con RECHAZADO
     * desde CALCULADO o VALIDADO. */
    cambiarEstado: async (
      expedienteId: string, presupuestoId: string,
      estado: "BORRADOR" | "CALCULADO" | "VALIDADO" | "RECHAZADO" | "APROBADO",
    ): Promise<Presupuesto> => {
      return this.request<Presupuesto>(
        "PATCH",
        `/presupuestos/${expedienteId}/presupuestos/${presupuestoId}/estado`,
        { estado },
      );
    },

    exportExcel: async (expedienteId: string, presupuestoId: string): Promise<Blob> => {
      const response = await fetch(
        `${this.baseUrl}/api/v1/presupuestos/${expedienteId}/presupuestos/${presupuestoId}/excel`,
        {
          headers: this.token ? { Authorization: `Bearer ${this.token}` } : {},
          credentials: 'include',
        }
      );
      if (!response.ok) throw new Error("Error al descargar Excel");
      return response.blob();
    },

    exportPdf: async (expedienteId: string, presupuestoId: string): Promise<Blob> => {
      const response = await fetch(
        `${this.baseUrl}/api/v1/presupuestos/${expedienteId}/presupuestos/${presupuestoId}/pdf`,
        {
          headers: this.token ? { Authorization: `Bearer ${this.token}` } : {},
          credentials: 'include',
        }
      );
      if (!response.ok) throw new Error("Error al descargar PDF");
      return response.blob();
    },

    validarSobrecostos: async (expedienteId: string, presupuestoId: string, presupuestoBaseId: string): Promise<any> => {
      return this.request<any>("POST", `/presupuestos/${expedienteId}/presupuestos/${presupuestoId}/validar-sobrecostos?presupuesto_base_id=${presupuestoBaseId}`);
    },
  };

  private drawingPath(expedienteId: string, modelId: string) {
    return `/bim/${encodeURIComponent(expedienteId)}/modelos/${encodeURIComponent(modelId)}/dibujos`;
  }

  bim = {
    listarPlanos: (expedienteId: string, modelId: string) =>
      this.request<{
        id: string; titulo: string; tipo: SolicitudPlanoBIM["tipo"]; estado: string;
        formatos: string[]; error?: string; source_model_updated_at: string; obsoleto: boolean;
        metadatos?: { visibility_mode?: string } | null;
      }[]>(
        "GET", this.drawingPath(expedienteId, modelId),
      ),

    generarPlano: (expedienteId: string, modelId: string, solicitud: SolicitudPlanoBIM) =>
      this.request("POST", this.drawingPath(expedienteId, modelId), {
        ...solicitud, formatos: ["PDF", "SVG", "DXF"],
      }),

    descargarPlano: async (expedienteId: string, modelId: string, drawingId: string, formato: "PDF" | "SVG" | "DXF") => {
      const path = `${this.drawingPath(expedienteId, modelId)}/${encodeURIComponent(drawingId)}/descarga?formato=${formato}`;
      const headers: Record<string, string> = {};
      if (this.token) headers.Authorization = `Bearer ${this.token}`;
      const response = await this.fetchWithSession(`${this.baseUrl}/api/v1${path}`, { headers, credentials: "include" });
      if (!response.ok) throw new Error(`No se pudo descargar el plano (HTTP ${response.status})`);
      if (response.headers.get("content-type")?.includes("application/json")) {
        const result = await response.json() as { url: string };
        return { url: result.url };
      }
      return { blob: await response.blob() };
    },

    reprocesarModelo: async (expedienteId: string, modeloId: string): Promise<ModeloBIM> =>
      this.request('POST', `/bim/${expedienteId}/modelos/${modeloId}/reprocesar`, {tipos_elementos:null, extraer_malla:true}),
    listarTrabajos: async (expedienteId: string, modeloId: string): Promise<Array<{
      id: string; tipo: string; entidad_id: string; estado: string; intentos: number; mensaje: string | null;
    }>> => this.request('GET', `/bim/${expedienteId}/modelos/${modeloId}/trabajos`),
    reintentarTrabajo: async (expedienteId: string, modeloId: string, trabajoId: string) =>
      this.request('POST', `/bim/${expedienteId}/modelos/${modeloId}/trabajos/${trabajoId}/reintentar`),
    listarGeneraciones: async (expedienteId: string, modeloId: string): Promise<GeneracionBIM4D5D[]> =>
      this.request('GET', `/bim/${expedienteId}/modelos/${modeloId}/generaciones-4d5d`),
    /** Modelos de un expediente, más reciente primero -- para elegir cuál
     * mostrar sin tener que ya saber su modelo_id de antemano. */
    listarModelos: async (expedienteId: string): Promise<ModeloBIM[]> => {
      return this.request<ModeloBIM[]>("GET", `/bim/${expedienteId}/modelos`);
    },

    /** Registra el modelo (sube el IFC a Supabase Storage) y encola la
     * extracción de cantidades (Qto del IFC + respaldo geométrico) y la
     * malla para renderizar en Three.js. Vuelve con
     * estado_procesamiento="EN_PROCESO" -- hay que hacer polling con
     * obtenerModelo() hasta COMPLETADO o ERROR antes de pedir elementos. */
    subirModelo: async (
      expedienteId: string,
      file: File,
      opciones: {
        nombre: string;
        descripcion?: string;
        tiposElementos?: string[]; // ej. ["IfcWall", "IfcSlab"]
        extraerMalla?: boolean;
      },
    ): Promise<ModeloBIM> => {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("nombre", opciones.nombre);
      if (opciones.descripcion) formData.append("descripcion", opciones.descripcion);
      if (opciones.tiposElementos) formData.append("tipos_elementos", opciones.tiposElementos.join(","));
      formData.append("extraer_malla", String(opciones.extraerMalla ?? true));
      return this.request<ModeloBIM>("POST", `/bim/${expedienteId}/modelos`, formData);
    },

    /** Hace polling a obtenerModelo() hasta que estado_procesamiento sea
     * COMPLETADO o ERROR (o se agoten los intentos). Usar justo después
     * de subirModelo() en vez de asumir que ya quedó listo. */
    esperarProcesamiento: async (
      expedienteId: string,
      modeloId: string,
      opciones?: { intervaloMs?: number; maxIntentos?: number },
    ): Promise<ModeloBIM> => {
      const intervaloMs = opciones?.intervaloMs ?? 2000;
      const maxIntentos = opciones?.maxIntentos ?? 150; // ~5 min a 2s
      for (let i = 0; i < maxIntentos; i++) {
        const modelo = await this.bim.obtenerModelo(expedienteId, modeloId);
        if (modelo.estado_procesamiento === "COMPLETADO" || modelo.estado_procesamiento === "ERROR") {
          return modelo;
        }
        await new Promise((resolve) => setTimeout(resolve, intervaloMs));
      }
      throw new Error(`Tiempo de espera agotado procesando el modelo ${modeloId}`);
    },

    obtenerModelo: async (expedienteId: string, modeloId: string): Promise<ModeloBIM> => {
      return this.request<ModeloBIM>("GET", `/bim/${expedienteId}/modelos/${modeloId}`);
    },

    /** incluirMalla=true trae vértices/caras (pesado) -- solo pedirlo
     * cuando el visor 3D los va a usar de verdad. */
    listarElementos: async (
      expedienteId: string,
      modeloId: string,
      opciones?: { tipo?: string; nivel?: string; incluirMalla?: boolean; limit?: number; offset?: number },
    ): Promise<ElementoBIM[]> => {
      const params = new URLSearchParams();
      if (opciones?.tipo) params.set("tipo", opciones.tipo);
      if (opciones?.nivel) params.set("nivel", opciones.nivel);
      if (opciones?.incluirMalla) params.set("incluir_malla", "true");
      if (opciones?.limit) params.set("limit", String(opciones.limit));
      if (opciones?.offset) params.set("offset", String(opciones.offset));
      const qs = params.toString();
      return this.request<ElementoBIM[]>("GET", `/bim/${expedienteId}/modelos/${modeloId}/elementos${qs ? `?${qs}` : ""}`);
    },

    mapearAPartidas: async (
      expedienteId: string,
      modeloId: string,
      mapeos: Array<{ elemento_id: string; partida_id: string }>,
    ): Promise<{ elementos_actualizados: number }> => {
      return this.request("POST", `/bim/${expedienteId}/modelos/${modeloId}/mapear-partidas`, mapeos);
    },

    generarPresupuesto: async (
      expedienteId: string,
      modeloId: string,
      data: {
        nombre?: string;
        parametros_costeo: ParametrosCosteoInput;
        /** Atajo por IfcType y overrides por elemento. El override
         * puntual permite APUs distintos para elementos del mismo tipo. */
        mapeo_catalogo?: Record<string, string>;
        mapeo_elementos?: Record<string, string>;
        cantidades_complementarias?: Array<{ elemento_id: string; unidad: string; cantidad: number; referencia: string }>;
      },
    ): Promise<Presupuesto> => {
      return this.request<Presupuesto>(
        "POST",
        `/bim/${expedienteId}/modelos/${modeloId}/generar-presupuesto`,
        data,
      );
    },

    /** Asigna zona_4d a elementos en lote -- agrupación de trabajo
     * editable para el cronograma 4D (ver ElementoBIM.zona_4d). Sin
     * esto, generar4D5D() agrupa por `nivel`. */
    asignarZonas4d: async (
      expedienteId: string,
      modeloId: string,
      asignaciones: Array<{ elemento_id: string; zona_4d: string }>,
    ): Promise<{ elementos_actualizados: number }> => {
      return this.request("POST", `/bim/${expedienteId}/modelos/${modeloId}/zonas-4d`, asignaciones);
    },

    /** Encola la generación de un ProgramaObra 4D desde el modelo BIM
     * (una actividad por zona×tipo, sin predecesoras -- eso se ajusta
     * después con criterio del programador, en la app de programación).
     * Devuelve de inmediato el registro de seguimiento; hay que hacer
     * polling con obtenerGeneracion4D5D() hasta COMPLETADO o ERROR. */
    generar4D5D: async (
      expedienteId: string,
      modeloId: string,
      data: { fecha_inicio: string; dias_por_defecto?: number; nombre_programa?: string },
    ): Promise<GeneracionBIM4D5D> => {
      return this.request<GeneracionBIM4D5D>(
        "POST",
        `/bim/${expedienteId}/modelos/${modeloId}/generar-4d5d`,
        data,
      );
    },

    obtenerGeneracion4D5D: async (expedienteId: string, generacionId: string): Promise<GeneracionBIM4D5D> => {
      return this.request<GeneracionBIM4D5D>("GET", `/bim/${expedienteId}/generaciones-4d5d/${generacionId}`);
    },

    /** Hace polling a obtenerGeneracion4D5D() hasta COMPLETADO o ERROR. */
    esperarGeneracion4D5D: async (
      expedienteId: string,
      generacionId: string,
      opciones?: { intervaloMs?: number; maxIntentos?: number },
    ): Promise<GeneracionBIM4D5D> => {
      const intervaloMs = opciones?.intervaloMs ?? 2000;
      const maxIntentos = opciones?.maxIntentos ?? 300; // ~10 min a 2s
      for (let i = 0; i < maxIntentos; i++) {
        const gen = await this.bim.obtenerGeneracion4D5D(expedienteId, generacionId);
        if (gen.estado === "COMPLETADO" || gen.estado === "ERROR") {
          return gen;
        }
        await new Promise((resolve) => setTimeout(resolve, intervaloMs));
      }
      throw new Error(`Tiempo de espera agotado en la generación 4D/5D ${generacionId}`);
    },

    /** URL firmada temporal (expira, no cachear) para bajar el IFC
     * original directo de Supabase Storage sin pasar por el backend. */
    descargarModeloUrl: async (
      expedienteId: string,
      modeloId: string,
    ): Promise<{ url: string; expira_en_segundos: number }> => {
      return this.request("GET", `/bim/${expedienteId}/modelos/${modeloId}/descarga`);
    },

    /** Corre clash detection real entre todos los elementos del modelo.
     * tolerancia_m=0 solo marca traslape real ("duro"); >0 también
     * marca pares más cerca que esa distancia sin tocarse ("blando",
     * típico para reglas de clearance MEP vs estructura). Síncrono --
     * puede tardar en modelos grandes, ver nota en el backend. */
    correrClashDetection: async (
      expedienteId: string,
      modeloId: string,
      opciones?: { toleranciaM?: number; tiposIncluidos?: string[]; tiposExcluidos?: string[] },
    ): Promise<AnalisisClash> => {
      return this.request<AnalisisClash>(
        "POST",
        `/bim/${expedienteId}/modelos/${modeloId}/clash-detection`,
        {
          tolerancia_m: opciones?.toleranciaM ?? 0.0,
          tipos_incluidos: opciones?.tiposIncluidos ?? null,
          tipos_excluidos: opciones?.tiposExcluidos ?? null,
        },
      );
    },

    obtenerAnalisisClash: async (
      expedienteId: string,
      modeloId: string,
      analisisId: string,
    ): Promise<AnalisisClash> => {
      return this.request<AnalisisClash>(
        "GET",
        `/bim/${expedienteId}/modelos/${modeloId}/clash-detection/${analisisId}`,
      );
    },

    /** severidad: "DURO" | "BLANDO". estado: "NUEVO" | "REVISADO" |
     * "RESUELTO" | "IGNORADO". Regresa DURO primero, luego por fecha. */
    listarResultadosClash: async (
      expedienteId: string,
      modeloId: string,
      analisisId: string,
      opciones?: { severidad?: string; estado?: string; limit?: number; offset?: number },
    ): Promise<ClashResult[]> => {
      const params = new URLSearchParams();
      if (opciones?.severidad) params.set("severidad", opciones.severidad);
      if (opciones?.estado) params.set("estado", opciones.estado);
      if (opciones?.limit) params.set("limit", String(opciones.limit));
      if (opciones?.offset) params.set("offset", String(opciones.offset));
      const qs = params.toString();
      return this.request<ClashResult[]>(
        "GET",
        `/bim/${expedienteId}/modelos/${modeloId}/clash-detection/${analisisId}/resultados${qs ? `?${qs}` : ""}`,
      );
    },

    /** Marca un clash como revisado/resuelto/ignorado -- seguimiento de
     * equipo, no vuelve a correr el análisis geométrico. */
    actualizarEstadoClash: async (
      expedienteId: string,
      resultadoId: string,
      estado: "NUEVO" | "REVISADO" | "RESUELTO" | "IGNORADO",
    ): Promise<ClashResult> => {
      return this.request<ClashResult>(
        "PATCH",
        `/bim/${expedienteId}/clash-resultados/${resultadoId}/estado`,
        { estado },
      );
    },
  };

  /** Catálogo maestro de precios unitarios (APU) -- ya filtra por tenant
   * en el backend. Usado por bim.generarPresupuesto(mapeo_catalogo) para
   * dejar que el usuario elija el precio real en vez de que el 5D
   * invente uno. */
  catalogoApu = {
    listar: async (opciones?: {
      q?: string;
      fuente?: string;
      zona?: string;
      skip?: number;
      limit?: number;
    }): Promise<{ total: number; items: CatalogoAPUOut[] }> => {
      const params = new URLSearchParams();
      if (opciones?.q) params.set("q", opciones.q);
      if (opciones?.fuente) params.set("fuente", opciones.fuente);
      if (opciones?.zona) params.set("zona", opciones.zona);
      if (opciones?.skip) params.set("skip", String(opciones.skip));
      if (opciones?.limit) params.set("limit", String(opciones.limit));
      const qs = params.toString();
      return this.request("GET", `/catalogo-apu${qs ? `?${qs}` : ""}`);
    },
  };

  programacion = {
    crear: async (expedienteId: string, data: {
      nombre: string;
      descripcion?: string;
      fecha_inicio: string; // ISO 8601
      actividades: ActividadInput[];
    }): Promise<Programa> => {
      return this.request<Programa>("POST", `/programacion/${expedienteId}/programas`, data);
    },

    listar: async (expedienteId: string, skip = 0, limit = 20): Promise<Programa[]> => {
      return this.request<Programa[]>("GET", `/programacion/${expedienteId}/programas?skip=${skip}&limit=${limit}`);
    },

    obtener: async (expedienteId: string, programaId: string): Promise<any> => {
      // El backend regresa el programa con sus actividades y resultados
      // ya calculados (exportar_programa), no solo los campos de Programa.
      return this.request<any>("GET", `/programacion/${expedienteId}/programas/${programaId}`);
    },

    calcularCPM: async (expedienteId: string, programaId: string, fechaInicio?: string): Promise<ResultadoCPM> => {
      const qs = fechaInicio ? `?fecha_inicio=${encodeURIComponent(fechaInicio)}` : '';
      return this.request<ResultadoCPM>("POST", `/programacion/${expedienteId}/programas/${programaId}/cpm${qs}`);
    },

    calcularPERT: async (expedienteId: string, programaId: string, fechaObjetivo?: string): Promise<ResultadoPERT> => {
      const qs = fechaObjetivo ? `?fecha_objetivo=${encodeURIComponent(fechaObjetivo)}` : '';
      return this.request<ResultadoPERT>("POST", `/programacion/${expedienteId}/programas/${programaId}/pert${qs}`);
    },

    calcularEVM: async (expedienteId: string, programaId: string, fechaCorte?: string): Promise<ResultadoEVM> => {
      const qs = fechaCorte ? `?fecha_corte=${encodeURIComponent(fechaCorte)}` : '';
      return this.request<ResultadoEVM>("POST", `/programacion/${expedienteId}/programas/${programaId}/evm${qs}`);
    },

    actualizarAvance: async (
      expedienteId: string,
      programaId: string,
      actividadId: string,
      porcentaje: number,
      costoReal?: number,
    ): Promise<Actividad> => {
      return this.request<Actividad>(
        "PATCH",
        `/programacion/${expedienteId}/programas/${programaId}/actividades/${actividadId}/avance`,
        { porcentaje, costo_real: costoReal },
      );
    },

    listarActividades: async (expedienteId: string, programaId: string): Promise<Actividad[]> => {
      // A diferencia de `obtener` (exportar_programa, resumen para
      // reporte/export), esto trae predecesoras/tipo/costos -- lo que la
      // vista de edición necesita para poblar el formulario.
      return this.request<Actividad[]>("GET", `/programacion/${expedienteId}/programas/${programaId}/actividades`);
    },

    actualizarActividad: async (
      expedienteId: string,
      programaId: string,
      actividadId: string,
      cambios: {
        nombre?: string;
        wbs_codigo?: string;
        duracion?: number;
        tipo?: string;
        predecesoras?: string[];
        dependencias_tipo?: Record<string, string>;
      },
    ): Promise<Actividad> => {
      // El backend recalcula el CPM completo tras el cambio -- la
      // respuesta trae las fechas/holguras ya actualizadas de ESTA
      // actividad, pero las demás también cambiaron: hay que recargar
      // listarActividades después de esto para reflejarlas en el Gantt.
      return this.request<Actividad>(
        "PATCH",
        `/programacion/${expedienteId}/programas/${programaId}/actividades/${actividadId}`,
        cambios,
      );
    },

    gantt: async (expedienteId: string, programaId: string): Promise<any[]> => {
      // Vacío hasta que se corra calcularCPM al menos una vez -- el gantt
      // sale del resultado_cpm ya guardado, no se recalcula aparte.
      return this.request<any[]>("GET", `/programacion/${expedienteId}/programas/${programaId}/gantt`);
    },

    curvaS: async (expedienteId: string, programaId: string): Promise<PuntoCurvaS[]> => {
      return this.request<PuntoCurvaS[]>("GET", `/programacion/${expedienteId}/programas/${programaId}/curva-s`);
    },

    rutaCritica: async (expedienteId: string, programaId: string): Promise<RutaCriticaInfo> => {
      return this.request<RutaCriticaInfo>("GET", `/programacion/${expedienteId}/programas/${programaId}/ruta-critica`);
    },
  };

  tezcatlipoca = {
    geoContext: async (params?: {
      latMin?: number; latMax?: number; lonMin?: number; lonMax?: number;
      earthquakeDays?: number; earthquakeMagnitude?: number; limit?: number;
    }): Promise<ContextoGeoTez> => {
      const q = new URLSearchParams({
        lat_min: String(params?.latMin ?? -90),
        lat_max: String(params?.latMax ?? 90),
        lon_min: String(params?.lonMin ?? -180),
        lon_max: String(params?.lonMax ?? 180),
        earthquake_days: String(params?.earthquakeDays ?? 1),
        earthquake_magnitude: String(params?.earthquakeMagnitude ?? 2.5),
        limit: String(params?.limit ?? 100),
      });
      return this.requestTez<ContextoGeoTez>("GET", `/geo/context?${q.toString()}`);
    },
    telemetry: async () => this.requestTez<any>("GET", "/telemetry/"),
    weatherForecast: async (lat: number, lon: number) => {
      const q = new URLSearchParams({ lat: String(lat), lon: String(lon) });
      return this.requestTez<any>("GET", `/weather/forecast?${q.toString()}`);
    },
    globalForecast: async (lat: number, lon: number): Promise<{
      status: string; source: string; run_time?: string; valid_time?: string;
      temperature_2m_c?: number; wind_10m_ms?: number;
      grid_point?: {lat: number; lon: number}; attribution?: string; reason?: string;
    }> => this.requestTez("GET", `/weather/global?${new URLSearchParams({lat:String(lat),lon:String(lon)}).toString()}`),
    saveSnapshot: async (payload: {
      name: string; description?: string; layers: string[];
      viewport: Record<string, unknown>;
    }): Promise<{ id: number; name: string; created_at: string }> =>
      this.requestTez("POST", "/snapshots/create", payload),
    snapshots: async (): Promise<{ id: number; name: string; created_at: string }[]> =>
      this.requestTez("GET", "/snapshots/"),
    osintLookup: async (q: string, type = "auto") => {
      const params = new URLSearchParams({ q, type });
      return this.requestTez<any>("GET", `/osint/lookup?${params.toString()}`);
    },
    osintExpand: async (entity: string, maxDepth = 2) =>
      this.requestTez<any>("POST", "/osint/expand", { entity, max_depth: maxDepth }),
    cyberCisaStats: async () => this.requestTez<any>("GET", "/cyber/cisa-kev/stats"),
    cyberGreynoise: async (ip: string) => this.requestTez<any>("GET", `/cyber/greynoise/ip/${encodeURIComponent(ip)}`),
    sarScenes: async (params?: { bbox?: string; startDate?: string; endDate?: string }) => {
      const q = new URLSearchParams();
      if (params?.bbox) q.set("bbox", params.bbox);
      if (params?.startDate) q.set("start_date", params.startDate);
      if (params?.endDate) q.set("end_date", params.endDate);
      return this.requestTez<any>("GET", `/sar/scenes${q.toString() ? `?${q.toString()}` : ""}`);
    },
  };

  topografia = {
    crearLevantamiento: async (expedienteId: string, data: {
      nombre: string; descripcion?: string; crs?: string; srid?: number;
    }): Promise<Levantamiento> => {
      return this.request<Levantamiento>("POST", `/topografia/${expedienteId}/levantamientos`, data);
    },

    listarLevantamientos: async (expedienteId: string, limit = 50): Promise<Levantamiento[]> => {
      return this.request<Levantamiento[]>("GET", `/topografia/${expedienteId}/levantamientos?limit=${limit}`);
    },

    listarSuperficies: async (levantamientoId: string): Promise<Omit<SuperficieTIN, "malla_vertices" | "malla_caras">[]> => {
      return this.request("GET", `/topografia/levantamientos/${levantamientoId}/superficies`);
    },

    /** GAP encontrado: no existía forma de recuperar los puntos crudos de
     * un levantamiento ya existente (solo se veían como efecto secundario
     * de importar/agregar en esa misma sesión, se perdían al recargar).
     * Nuevo endpoint propuesto -- mismo patrón REST que el resto de este
     * namespace, pendiente de implementar en el backend. */
    listarPuntos: async (levantamientoId: string, limit = 5000): Promise<PuntoTopografico[]> => {
      return this.request<PuntoTopografico[]>("GET", `/topografia/levantamientos/${levantamientoId}/puntos?limit=${limit}`);
    },

    agregarPuntos: async (levantamientoId: string, puntos: Array<{
      identificador: string; x: number; y: number; z?: number;
      etiqueta?: string; descripcion?: string;
    }>): Promise<PuntoTopografico[]> => {
      return this.request<PuntoTopografico[]>("POST", `/topografia/levantamientos/${levantamientoId}/puntos`, puntos);
    },

    /** formato 'penzd' = Punto,Este,Norte,Elevación,Descripción (el
     * estándar que exportan estaciones totales / GPS RTK). */
    importarCSV: async (levantamientoId: string, file: File, formato: "penzd" | "generico" = "penzd"): Promise<PuntoTopografico[]> => {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("formato", formato);
      return this.request<PuntoTopografico[]>("POST", `/topografia/levantamientos/${levantamientoId}/importar-csv`, formData);
    },

    triangular: async (levantamientoId: string, nombre: string, tipo: "EXISTENTE" | "PROYECTO" = "EXISTENTE"): Promise<SuperficieTIN> => {
      return this.request<SuperficieTIN>("POST", `/topografia/levantamientos/${levantamientoId}/triangular`, { nombre, tipo });
    },

    obtenerSuperficie: async (superficieId: string): Promise<SuperficieTIN> => {
      return this.request<SuperficieTIN>("GET", `/topografia/superficies/${superficieId}`);
    },

    curvasNivel: async (superficieId: string, intervalo = 1.0): Promise<{ intervalo: number; curvas: Record<string, [number, number][][]> }> => {
      return this.request("GET", `/topografia/superficies/${superficieId}/curvas-nivel?intervalo=${intervalo}`);
    },

    generarPerfil: async (superficieId: string, eje: [number, number][], intervaloMuestreo = 5.0): Promise<PuntoPerfil[]> => {
      return this.request<PuntoPerfil[]>("POST", `/topografia/superficies/${superficieId}/perfil`, {
        eje, intervalo_muestreo: intervaloMuestreo,
      });
    },

    calcularVolumen: async (data: {
      superficie_existente_id: string; superficie_proyecto_id?: string; elevacion_referencia?: number;
    }): Promise<CalculoVolumen> => {
      return this.request<CalculoVolumen>("POST", "/topografia/volumenes", data);
    },

    generarPresupuestoMovimientoTierras: async (
      calculoId: string, expedienteId: string,
      data: { nombre?: string; parametros_costeo: ParametrosCosteoInput },
    ): Promise<Presupuesto> => {
      return this.request<Presupuesto>(
        "POST",
        `/topografia/${expedienteId}/volumenes/${calculoId}/generar-presupuesto`,
        data,
      );
    },

    transformarCoordenadas: async (
      puntos: [number, number][], crsOrigen: string, crsDestino: string,
    ): Promise<{ puntos: [number, number][] }> => {
      return this.request("POST", "/topografia/geodesia/transformar", { puntos, crs_origen: crsOrigen, crs_destino: crsDestino });
    },

    cierrePoligonal: async (vertices: [number, number][]): Promise<ResultadoCierrePoligonal> => {
      return this.request<ResultadoCierrePoligonal>("POST", "/topografia/geodesia/cierre-poligonal", { vertices });
    },
  };

  juridico = {
    /** Si `datos_verificados` viene false en la respuesta, procedimiento
     * es "SIN_DETERMINAR" -- no hay umbral confirmado para esa
     * jurisdicción/año. Si `es_candidato` viene true, sí hay un
     * procedimiento calculado pero con cifras citadas sin confirmar
     * contra la fuente oficial -- mostrar advertencia visible. */
    determinarProcedimiento: async (data: {
      monto: number;
      tipo_contratacion?: string;
      es_obra_publica?: boolean;
      jurisdiccion?: string;
      ejercicio_fiscal?: number;
      /** Requerido para FEDERAL: el Anexo 9 es una tabla escalonada por
       * el presupuesto autorizado de la dependencia contratante (en
       * miles de pesos), no un monto único. */
      presupuesto_dependencia_miles?: number;
    }): Promise<ResultadoJuridico> => {
      return this.request<ResultadoJuridico>("POST", "/juridico/determinar-procedimiento", data);
    },

    validarMonto: async (
      monto: number, tipo_contratacion: string,
      opciones?: { jurisdiccion?: string; ejercicio_fiscal?: number; presupuesto_dependencia_miles?: number },
    ): Promise<any> => {
      return this.request<any>("POST", "/juridico/validar-monto", {
        monto, tipo_contratacion,
        jurisdiccion: opciones?.jurisdiccion,
        ejercicio_fiscal: opciones?.ejercicio_fiscal,
        presupuesto_dependencia_miles: opciones?.presupuesto_dependencia_miles,
      });
    },

    checklist: async (procedimiento: string, tipo_contratacion: string): Promise<any> => {
      return this.request<any>("POST", "/juridico/checklist", { procedimiento, tipo_contratacion });
    },

    /** Qué jurisdicciones existen y
     * cuáles ya tienen umbrales verificados o candidatos -- para poblar
     * un selector sin adivinar qué está disponible. */
    jurisdiccionesDisponibles: async (): Promise<Array<{ jurisdiccion: string; estado_dato: "VERIFICADO" | "CANDIDATO" | "PENDIENTE" }>> => {
      return this.request("GET", "/juridico/jurisdicciones");
    },
  };

  riesgo = {
    simular: async (data: {
      expediente_id?: string;
      presupuesto_id?: string;
      programa_id?: string;
      presupuesto_base?: number;
      presupuesto_maximo: number;
      plazo_base_dias?: number;
      plazo_maximo_dias?: number;
      variables: Array<{
        nombre: string;
        distribucion: "normal" | "triangular" | "uniform" | "lognormal" | "beta";
        parametros: Record<string, number>;
        impacto?: "costo_pct" | "plazo_pct" | "plazo_dias" | "costo_y_plazo_pct";
      }>;
      iteraciones?: number;
      seed?: number;
      confidence_level?: number;
      correlaciones?: Record<string, Record<string, number>>;
    }): Promise<any> => {
      return this.request<any>("POST", "/riesgo/simular", data);
    },

    consultar: async (taskId: string): Promise<any> => {
      return this.request<any>("GET", `/riesgo/simular/${taskId}/status`);
    },

    cancel: async (taskId: string): Promise<any> => {
      return this.request<any>("POST", `/riesgo/simular/${taskId}/cancel`);
    },

    historial: async (params?: { limit?: number; offset?: number }): Promise<any> => {
      const q = new URLSearchParams();
      if (params?.limit != null) q.set("limit", String(params.limit));
      if (params?.offset != null) q.set("offset", String(params.offset));
      return this.request<any>("GET", `/riesgo/simulaciones?${q.toString()}`);
    },
  };

  // NOTA: `validadores` estaba declarado DOS VECES en este archivo (bug
  // original). En una `class` de TS/JS la segunda definición pisa a la
  // primera en runtime, pero es un error de compilación bajo la mayoría
  // de configuraciones estrictas y confunde a quien edite el archivo
  // después. Se conserva sólo la versión más completa (con obtener() y
  // validarCompleto()) y se elimina el duplicado.
  validadores = {
    /** Corre los 10 validadores reales (SAT, IMSS/INFONAVIT, e.firma,
     * FSR, maquinaria, sobrecostos, congruencia temporal, garantía,
     * publicación, requisitos de participación) contra una propuesta
     * completa, y persiste la bitácora para auditoría. */
    evaluarCompleto: async (expedienteId: string, propuesta: PropuestaLicitacion): Promise<ValidacionPropuesta> => {
      return this.request<ValidacionPropuesta>("POST", `/validadores/${expedienteId}/evaluar-completo`, propuesta);
    },

    historial: async (expedienteId: string, limit = 50): Promise<ValidacionPropuesta[]> => {
      return this.request<ValidacionPropuesta[]>("GET", `/validadores/${expedienteId}/historial?limit=${limit}`);
    },

    obtener: async (expedienteId: string, validacionId: string): Promise<ValidacionPropuesta> => {
      return this.request<ValidacionPropuesta>("GET", `/validadores/${expedienteId}/validacion/${validacionId}`);
    },

    /** Verificación de FORMATO de RFC únicamente (NO es una consulta
     * real al SAT/IMSS/INFONAVIT). Para la validación real, usar
     * evaluarCompleto(). Se conserva por compatibilidad. */
    validarCompleto: async (rfc: string, fsr: number = 1.0): Promise<any> => {
      return this.request<any>("POST", "/validadores/completo", { rfc, fsr });
    },
  };

  ocr = {
    extraer: async (file: File, presupuestoId?: string): Promise<TaskStatus> => {
      const formData = new FormData();
      formData.append("file", file);
      if (presupuestoId) formData.append("presupuesto_id", presupuestoId);
      return this.request<TaskStatus>("POST", "/ocr/extraer", formData);
    },

    consultar: async (taskId: string): Promise<TaskStatus> => {
      return this.request<TaskStatus>("GET", `/ocr/extraer/${taskId}/status`);
    },

    validar: async (metrados: MetradoOCR[], umbralConfianza: number = 60): Promise<any> => {
      // BUG ORIGINAL: se mandaba como header "umbral_confianza", pero el
      // backend (app/api/v1/ocr.py) lo declara como query param sin
      // anotación especial -> nunca se leía, siempre usaba el default 60.0.
      return this.request<any>(
        "POST",
        `/ocr/validar?umbral_confianza=${umbralConfianza}`,
        metrados,
      );
    },
  };

  firma = {
    firmarDocumento: async (
      documentoId: string,
      certificadoCer: File,
      certificadoKey: File,
      password: string,
      razon: string = "Firma de documento de obra pública",
      ubicacion: string = "México",
      usarTsa: boolean = true,
      tsaUrl?: string,
    ): Promise<any> => {
      const formData = new FormData();
      formData.append("certificado_cer", certificadoCer);
      formData.append("certificado_key", certificadoKey);
      formData.append("password", password);
      formData.append("razon", razon);
      formData.append("ubicacion", ubicacion);
      formData.append("usar_tsa", String(usarTsa));
      if (tsaUrl) formData.append("tsa_url", tsaUrl);
      return this.request<any>("POST", `/firma/documentos/${documentoId}`, formData);
    },

    validarFirma: async (documentoId: string): Promise<any> => {
      return this.request<any>("GET", `/firma/documentos/${documentoId}/validar`);
    },

    firmarMerkle: async (expedienteId: string, certificadoCer: File, certificadoKey: File, password: string): Promise<any> => {
      const formData = new FormData();
      formData.append("certificado_cer", certificadoCer);
      formData.append("certificado_key", certificadoKey);
      formData.append("password", password);
      return this.request<any>("POST", `/firma/expedientes/${expedienteId}/merkle`, formData);
    },

    /** Sella (NO timbra) un CFDI 4.0. El timbrado fiscal real requiere
     * un PAC autorizado por el SAT -- esto deja el XML listo para
     * mandarlo a cualquiera. */
    sellarCFDI: async (xmlCfdi: File, certificadoCer: File, certificadoKey: File, password: string): Promise<{
      xml_sellado: string;
      cadena_original: string;
      sello_digital: string;
      no_certificado: string;
      nota: string;
    }> => {
      const formData = new FormData();
      formData.append("xml_cfdi", xmlCfdi);
      formData.append("certificado_cer", certificadoCer);
      formData.append("certificado_key", certificadoKey);
      formData.append("password", password);
      return this.request("POST", "/firma/cfdi/sellar", formData);
    },

    /** Qué formato de firma (XAdES-EPES / PAdES-basic / PAdES-LT) exige
     * una plataforma gubernamental para un tipo de documento. */
    formatoRequerido: async (
      plataforma: "compranet" | "compras_mx" | "imss" | "infonavit" | "seop_generico" | "cfe" | "pemex" | "personalizada",
      tipoDocumento: string,
    ): Promise<{ plataforma: string; tipo_documento: string; formato_requerido: string }> => {
      return this.request(
        "GET",
        `/firma/formato-requerido?plataforma=${plataforma}&tipo_documento=${encodeURIComponent(tipoDocumento)}`,
      );
    },
  };

  // ═══════════════════════════════════════════════════════════════════════
  // DOCUMENTOS / CDE — Gestión documental avanzada
  // (clasificación, versionado, duplicados, búsqueda, estadísticas)
  // ═══════════════════════════════════════════════════════════════════════

  documentos = {
    clasificar: async (
      documentoId: string,
      tipoSugerido?: string,
      confianza?: number,
    ): Promise<DocumentoCDE> => {
      const params = new URLSearchParams();
      if (tipoSugerido) params.set("tipo_sugerido", tipoSugerido);
      if (confianza !== undefined) params.set("confianza", String(confianza));
      const qs = params.toString() ? `?${params.toString()}` : "";
      return this.request<DocumentoCDE>("POST", `/documentos/${documentoId}/clasificar${qs}`);
    },

    duplicados: async (expedienteId: string, umbralSimilitud = 0.95): Promise<DocumentoDuplicado[]> => {
      return this.request<DocumentoDuplicado[]>(
        "GET", `/documentos/duplicados/${expedienteId}?umbral_similitud=${umbralSimilitud}`,
      );
    },

    busquedaAvanzada: async (params?: {
      q?: string;
      tipo?: string;
      estado?: string;
      expedienteId?: string;
      fechaInicio?: string;
      fechaFin?: string;
      tags?: string[];
      skip?: number;
      limit?: number;
    }): Promise<BusquedaDocumentosResultado> => {
      const q = new URLSearchParams();
      if (params?.q) q.set("q", params.q);
      if (params?.tipo) q.set("tipo", params.tipo);
      if (params?.estado) q.set("estado", params.estado);
      if (params?.expedienteId) q.set("expediente_id", params.expedienteId);
      if (params?.fechaInicio) q.set("fecha_inicio", params.fechaInicio);
      if (params?.fechaFin) q.set("fecha_fin", params.fechaFin);
      (params?.tags || []).forEach((t) => q.append("tags", t));
      q.set("skip", String(params?.skip ?? 0));
      q.set("limit", String(params?.limit ?? 100));
      return this.request<BusquedaDocumentosResultado>("GET", `/documentos/busqueda-avanzada?${q.toString()}`);
    },

    nuevaVersion: async (
      documentoId: string,
      nuevoContenidoUrl: string,
      cambiosDescripcion?: string,
    ): Promise<DocumentoCDE> => {
      return this.request<DocumentoCDE>("POST", `/documentos/${documentoId}/nueva-version`, {
        nuevo_contenido_url: nuevoContenidoUrl,
        cambios_descripcion: cambiosDescripcion,
      });
    },

    versiones: async (documentoId: string): Promise<VersionDocumento[]> => {
      return this.request<VersionDocumento[]>("GET", `/documentos/${documentoId}/versiones`);
    },

    estadisticas: async (expedienteId: string): Promise<EstadisticasDocumentales> => {
      return this.request<EstadisticasDocumentales>("GET", `/documentos/estadisticas/${expedienteId}`);
    },
  };

  websocket = {
    connect: (token?: string): WebSocket => {
      const wsUrl = this.baseUrl.replace("http", "ws");
      const url = token
        ? `${wsUrl}/ws/progreso?token=${encodeURIComponent(token)}`
        : `${wsUrl}/ws/progreso`;
      this.ws = new WebSocket(url);

      this.ws.onmessage = (event) => {
        const msg: WebSocketMessage = JSON.parse(event.data);
        if (msg.task_id && this.wsCallbacks.has(msg.task_id)) {
          this.wsCallbacks.get(msg.task_id)?.forEach((cb) => cb(msg));
        }
      };
      return this.ws;
    },

    disconnect: () => {
      this.ws?.close();
      this.ws = null;
    },

    subscribe: (taskId: string, callback: (msg: WebSocketMessage) => void) => {
      if (!this.wsCallbacks.has(taskId)) {
        this.wsCallbacks.set(taskId, []);
      }
      this.wsCallbacks.get(taskId)?.push(callback);
      this.ws?.send(JSON.stringify({ action: "subscribe", task_id: taskId }));
    },

    unsubscribe: (taskId: string) => {
      this.wsCallbacks.delete(taskId);
      this.ws?.send(JSON.stringify({ action: "unsubscribe", task_id: taskId }));
    },

    onProgress: (taskId: string, onProgress: (progress: number, message?: string) => void) => {
      // BUG ORIGINAL: this.subscribe() buscaba un método "subscribe" en
      // MegalodonClient (no existe ahí, vive dentro de this.websocket),
      // así que esto tronaba con "this.subscribe is not a function" en
      // cuanto alguien llamaba client.websocket.onProgress(...).
      this.websocket.subscribe(taskId, (msg: WebSocketMessage) => {
        if (msg.type === "progress" && msg.progress !== undefined) {
          onProgress(msg.progress, msg.message);
        }
      });
    },

    onComplete: (taskId: string, onComplete: (result: any, error?: string) => void) => {
      this.websocket.subscribe(taskId, (msg: WebSocketMessage) => {
        if (msg.type === "complete") {
          onComplete(msg.result, msg.error);
          this.websocket.unsubscribe(taskId);
        }
      });
    },

    onError: (taskId: string, onError: (error: string) => void) => {
      this.websocket.subscribe(taskId, (msg: WebSocketMessage) => {
        if (msg.type === "error") {
          onError(msg.error || "Error desconocido en la tarea.");
          this.websocket.unsubscribe(taskId);
        }
      });
    },
  };

  /** Token actual (o cadena vacía si no hay sesión) -- para el puñado de
   * casos (WebSocket nativo, etc.) que no pasan por request(). */
  getToken(): string {
    return this.token || "";
  }

  // ═══════════════════════════════════════════════════════════════════════
  // MONTE CARLO — Simulación de riesgo
  // ═══════════════════════════════════════════════════════════════════════

  montecarlo = {
    simular: async (data: {
      presupuestoBase?: number;
      presupuestoMaximo: number;
      plazoBaseDias?: number;
      plazoMaximoDias?: number;
      expedienteId?: string;
      presupuestoId?: string;
      programaId?: string;
      variables: { nombre: string; distribucion: "normal" | "triangular" | "uniform" | "lognormal" | "beta"; parametros: Record<string, number>; impacto?: "costo_pct" | "plazo_pct" | "plazo_dias" | "costo_y_plazo_pct" }[];
      iteraciones?: number;
      seed?: number;
      confidenceLevel?: number;
      correlaciones?: Record<string, Record<string, number>>;
    }) => this.riesgo.simular({
      presupuesto_base: data.presupuestoBase,
      presupuesto_maximo: data.presupuestoMaximo,
      plazo_base_dias: data.plazoBaseDias,
      plazo_maximo_dias: data.plazoMaximoDias,
      expediente_id: data.expedienteId,
      presupuesto_id: data.presupuestoId,
      programa_id: data.programaId,
      variables: data.variables,
      iteraciones: data.iteraciones,
      seed: data.seed,
      confidence_level: data.confidenceLevel,
      correlaciones: data.correlaciones,
    }),
    consultarStatus: async (taskId: string) => this.riesgo.consultar(taskId),
    cancel: async (taskId: string) => this.riesgo.cancel(taskId),
    historial: async (params?: { limit?: number; offset?: number }) => this.riesgo.historial(params),
  };

  // ═══════════════════════════════════════════════════════════════════════
  // FASE 2 — CATÁLOGO APU
  // ═══════════════════════════════════════════════════════════════════════

  catalogoAPU = {
    crear: async (data: any) => {
      return this.request("POST", "/catalogo-apu", data);
    },
    listar: async (params?: { skip?: number; limit?: number; fuente?: string; zona?: string; tipo?: string; q?: string }) => {
      const query = new URLSearchParams(params as any).toString();
      return this.request("GET", `/catalogo-apu?${query}`);
    },
    obtener: async (id: string) => {
      return this.request("GET", `/catalogo-apu/${id}`);
    },
    actualizar: async (id: string, data: any) => {
      return this.request("PATCH", `/catalogo-apu/${id}`, data);
    },
    eliminar: async (id: string) => {
      return this.request("DELETE", `/catalogo-apu/${id}`);
    },
    precioConIVA: async (id: string, tasaIVA: number) => {
      return this.request("GET", `/catalogo-apu/${id}/precio-con-iva?tasa_iva=${tasaIVA}`);
    },
  };

  catalogoImportaciones = {
    listar: () => this.request<{total: number; items: CatalogoImportacionOut[]}>('GET', '/catalogo-apu/importaciones'),
    verificar: (archivo: File) => {
      const form = new FormData(); form.append('archivo', archivo);
      return this.request<{ fuentes: Array<{fuente_id: string; titulo: string; nombre_visible?: string; sha256: string; fecha_vigencia: string; original_cotejado: boolean}> }>(
        'POST', '/catalogo-apu/importaciones/verificar', form);
    },
    importar: (archivo: File, fuentes: string[]) => {
      const form = new FormData(); form.append('archivo', archivo); form.append('fuentes', JSON.stringify(fuentes));
      return this.request<CatalogoImportacionOut & {creada: boolean}>('POST', '/catalogo-apu/importaciones', form);
    },
    registros: (id: string, tabla: string, estado?: string, skip = 0, limit = 200) => {
      const query = new URLSearchParams({tabla, skip: String(skip), limit: String(limit), ...(estado ? {estado} : {})});
      return this.request<{total: number; items: CatalogoRegistroOut[]}>('GET', `/catalogo-apu/importaciones/${id}/registros?${query}`);
    },
    estimar: (data: {modelo_registro_id: string; factor_registro_id: string; cantidad: string; ajuste_proyecto: string; justificacion: string}) =>
      this.request<{id: string; monto: string; evidencia: Record<string, unknown>}>('POST', '/catalogo-apu/estimaciones-parametricas', data),
  };

  // ═══════════════════════════════════════════════════════════════════════
  // FASE 2 — CATÁLOGO CONCEPTOS
  // ═══════════════════════════════════════════════════════════════════════

  catalogoConceptos = {
    fuentes: {
      crear: async (data: any) => {
        return this.request("POST", "/catalogo-conceptos/fuentes", data);
      },
      listar: async (activo?: boolean) => {
        const query = activo !== undefined ? `?activo=${activo}` : "";
        return this.request("GET", `/catalogo-conceptos/fuentes${query}`);
      },
    },
    conceptos: {
      crear: async (data: any) => {
        return this.request("POST", "/catalogo-conceptos/conceptos", data);
      },
      listar: async (params?: { skip?: number; limit?: number; fuente_id?: string; zona?: string; estado?: string; q?: string }) => {
        const query = new URLSearchParams(params as any).toString();
        return this.request("GET", `/catalogo-conceptos/conceptos?${query}`);
      },
      obtener: async (id: string) => {
        return this.request("GET", `/catalogo-conceptos/conceptos/${id}`);
      },
      actualizar: async (id: string, data: any) => {
        return this.request("PATCH", `/catalogo-conceptos/conceptos/${id}`, data);
      },
      costoDesglosado: async (id: string, cantidad: number = 1, tasaIVA: number) => {
        return this.request("GET", `/catalogo-conceptos/conceptos/${id}/costo-desglosado?cantidad=${cantidad}&tasa_iva=${tasaIVA}`);
      },
    },
    insumos: {
      crear: async (data: any) => {
        return this.request("POST", "/catalogo-conceptos/insumos", data);
      },
      listar: async (params?: { skip?: number; limit?: number; fuente_id?: string; tipo?: string; categoria?: string }) => {
        const query = new URLSearchParams(params as any).toString();
        return this.request("GET", `/catalogo-conceptos/insumos?${query}`);
      },
    },
  };

  // ═══════════════════════════════════════════════════════════════════════
  // FASE 2 — COMPLIANCE
  // ═══════════════════════════════════════════════════════════════════════

  compliance = {
    reglas: {
      crear: async (data: ReglaCumplimientoInput): Promise<ReglaCumplimiento> => {
        return this.request("POST", "/compliance/reglas", data);
      },
      // BUG ORIGINAL: el componente compliance-dashboard hacía
      // `setReglas(reglasRes as ReglaCumplimiento[])`, pero el backend
      // (ComplianceService.listar_reglas) siempre regresa un objeto
      // paginado `{ total, items }`, nunca un array plano. En cuanto
      // hubiera una sola regla en la base, `reglas.map(...)` en el JSX
      // tronaba en runtime. Se tipa correctamente aquí para que el
      // error se vea en tiempo de compilación en vez de en producción.
      listar: async (params?: { tipo_procedimiento?: string; etapa?: string; activa?: boolean; skip?: number; limit?: number }): Promise<{ total: number; items: ReglaCumplimiento[] }> => {
        const query = new URLSearchParams(params as any).toString();
        return this.request("GET", `/compliance/reglas?${query}`);
      },
      obtener: async (id: string): Promise<ReglaCumplimiento> => {
        return this.request("GET", `/compliance/reglas/${id}`);
      },
      actualizar: async (id: string, data: ReglaCumplimientoInput): Promise<ReglaCumplimiento> => {
        return this.request("PATCH", `/compliance/reglas/${id}`, data);
      },
      eliminar: async (id: string): Promise<void> => {
        return this.request("DELETE", `/compliance/reglas/${id}`);
      },
    },
    inconformidades: {
      crear: async (data: InconformidadInput): Promise<Inconformidad> => {
        return this.request("POST", "/compliance/inconformidades", data);
      },
      listar: async (params?: { estado?: string; severidad?: string; expediente_id?: string; skip?: number; limit?: number }): Promise<{ total: number; items: Inconformidad[] }> => {
        const query = new URLSearchParams(params as any).toString();
        return this.request("GET", `/compliance/inconformidades?${query}`);
      },
      obtener: async (id: string): Promise<Inconformidad> => {
        return this.request("GET", `/compliance/inconformidades/${id}`);
      },
      actualizar: async (id: string, data: Partial<{ estado: string; severidad: string; asignado_a: string; fecha_limite: string; respuesta: string; resolucion: string; dictamen: string; fecha_dictamen: string }>): Promise<Inconformidad> => {
        return this.request("PATCH", `/compliance/inconformidades/${id}`, data);
      },
    },
    sanciones: {
      crear: async (data: SancionInput): Promise<Sancion> => {
        return this.request("POST", "/compliance/sanciones", data);
      },
      listar: async (params?: { proveedor_id?: string; tipo?: string; skip?: number; limit?: number }): Promise<{ total: number; items: Sancion[] }> => {
        const query = new URLSearchParams(params as any).toString();
        return this.request("GET", `/compliance/sanciones?${query}`);
      },
      obtener: async (id: string): Promise<Sancion> => {
        return this.request("GET", `/compliance/sanciones/${id}`);
      },
    },
    evaluar: async (expedienteId: string): Promise<EvaluacionComplianceResultado> => {
      return this.request("POST", `/compliance/evaluar/${expedienteId}`);
    },
  };

  // ═══════════════════════════════════════════════════════════════════════
  // FASE 2 — CONTRATOS
  // ═══════════════════════════════════════════════════════════════════════

  contratos = {
    crear: async (data: ContratoInput): Promise<Contrato> => {
      return this.request("POST", "/contratos", data);
    },
    listar: async (params?: { estado?: string; expediente_id?: string; proveedor_id?: string; skip?: number; limit?: number }): Promise<{ total: number; items: Contrato[] }> => {
      const query = new URLSearchParams(params as any).toString();
      return this.request("GET", `/contratos?${query}`);
    },
    obtener: async (id: string): Promise<Contrato> => {
      return this.request("GET", `/contratos/${id}`);
    },
    actualizar: async (id: string, data: Partial<{ monto_total: number; plazo_dias: number; fecha_firma: string; fecha_inicio: string; fecha_termino: string; avance_fisico: number; avance_financiero: number; fecha_finiquito: string; monto_finiquito: number }>): Promise<Contrato> => {
      return this.request("PATCH", `/contratos/${id}`, data);
    },
    transicionar: async (id: string, nuevoEstado: typeof ESTADOS_CONTRATO[number]): Promise<Contrato> => {
      return this.request("POST", `/contratos/${id}/transicionar?nuevo_estado=${nuevoEstado}`);
    },
    resumen: async (id: string): Promise<ResumenContrato> => {
      return this.request("GET", `/contratos/${id}/resumen`);
    },
    modificatorios: {
      crear: async (contratoId: string, data: ModificatorioInput): Promise<Modificatorio> => {
        return this.request("POST", `/contratos/${contratoId}/modificatorios`, data);
      },
      listar: async (contratoId: string): Promise<Modificatorio[]> => {
        return this.request("GET", `/contratos/${contratoId}/modificatorios`);
      },
    },
    garantias: {
      crear: async (contratoId: string, data: GarantiaInput): Promise<Garantia> => {
        return this.request("POST", `/contratos/${contratoId}/garantias`, data);
      },
      listar: async (contratoId: string): Promise<Garantia[]> => {
        return this.request("GET", `/contratos/${contratoId}/garantias`);
      },
      vigencia: async (contratoId: string): Promise<AlertaGarantia[]> => {
        return this.request("GET", `/contratos/${contratoId}/garantias/vigencia`);
      },
    },
    entregables: {
      crear: async (contratoId: string, data: EntregableInput): Promise<Entregable> => {
        return this.request("POST", `/contratos/${contratoId}/entregables`, data);
      },
      listar: async (contratoId: string): Promise<Entregable[]> => {
        return this.request("GET", `/contratos/${contratoId}/entregables`);
      },
      aprobar: async (contratoId: string, entregableId: string): Promise<Entregable> => {
        return this.request("POST", `/contratos/${contratoId}/entregables/${entregableId}/aprobar`);
      },
    },
    penalizaciones: {
      crear: async (contratoId: string, data: PenalizacionInput): Promise<Penalizacion> => {
        return this.request("POST", `/contratos/${contratoId}/penalizaciones`, data);
      },
      // El backend no tenía este GET (solo crear) pese a que el modelo y el
      // schema ya lo soportaban -- se agregó el endpoint correspondiente.
      listar: async (contratoId: string): Promise<Penalizacion[]> => {
        return this.request("GET", `/contratos/${contratoId}/penalizaciones`);
      },
    },
  };

  // ═══════════════════════════════════════════════════════════════════════
  // FASE 2 — LICITACIONES
  // ═══════════════════════════════════════════════════════════════════════

  proveedores = {
    listar: async (params: { q?: string; skip?: number; limit?: number } = {}) => {
      const query = new URLSearchParams();
      Object.entries(params).forEach(([key, value]) => { if (value !== undefined) query.set(key, String(value)); });
      return this.request<{ total: number; items: import('./licitacion-types').ProviderRecord[] }>('GET', `/proveedores?${query}`);
    },
    crear: async (data: Pick<import('./licitacion-types').ProviderRecord, 'rfc' | 'razon_social' | 'tipo_persona'>) =>
      this.request<import('./licitacion-types').ProviderRecord>('POST', '/proveedores', data),
  };

  licitaciones = {
    congelarBases: async (id: string, version: number) => this.request('POST', `/licitaciones/${id}/bases/congelar?version_esperada=${version}`),
    crear: async (data: any) => {
      return this.request("POST", "/licitaciones", data);
    },
    listar: async (params?: { estado?: string; tipo_procedimiento?: string; expediente_id?: string; skip?: number; limit?: number }) => {
      const query = new URLSearchParams(params as any).toString();
      return this.request("GET", `/licitaciones?${query}`);
    },
    obtener: async (id: string) => {
      return this.request("GET", `/licitaciones/${id}`);
    },
    actualizar: async (id: string, data: any) => {
      return this.request("PATCH", `/licitaciones/${id}`, data);
    },
    transicionar: async (id: string, data: { nuevo_estado: string }) => {
      return this.request("POST", `/licitaciones/${id}/transicionar`, data);
    },
    resumen: async (id: string) => {
      return this.request("GET", `/licitaciones/${id}/resumen`);
    },
    juntas: {
      // Las juntas ocurren fuera de Megalodon. Solo se consultan registros importados.
      listar: async (licitacionId: string) => {
        return this.request("GET", `/licitaciones/${licitacionId}/junta-aclaraciones`);
      },
    },
    proposiciones: {
      registrar: async (licitacionId: string, data: any) => {
        return this.request("POST", `/licitaciones/${licitacionId}/proposiciones`, data);
      },
      listar: async (licitacionId: string) => {
        return this.request("GET", `/licitaciones/${licitacionId}/proposiciones`);
      },
    },
    evaluaciones: {
      crear: async (licitacionId: string, data: any) => {
        return this.request("POST", `/licitaciones/${licitacionId}/evaluaciones`, data);
      },
    },
    fallo: {
      emitir: async (licitacionId: string, proposicionGanadoraId: string) => {
        return this.request("POST", `/licitaciones/${licitacionId}/fallo?proposicion_ganadora_id=${proposicionGanadoraId}`);
      },
    },
  };

  // ═══════════════════════════════════════════════════════════════════════
  // INTEGRACIÓN ZIP 2: LICITACIONES DE OBRA
  // ═══════════════════════════════════════════════════════════════════════

  licitacionesObra = {
    workspace: async (expedienteId: string) => this.request<any>("GET", `/licitaciones-obra/expediente/${expedienteId}/workspace`),
    planeacion: {
      create: async (data: any) => this.request("POST", `/licitaciones-obra/expediente/${data.expediente_id}/planeacion`, data),
    },
    convocatoria: {
      get: async (id: string) => this.request("GET", `/procurement/tenders${id ? `?expediente_id=${encodeURIComponent(id)}` : ""}`),
    },
    proposiciones: {
      list: async (id: string) => { const w = await this.request<any>("GET", `/licitaciones-obra/expediente/${id}/workspace`); return { proposiciones: w.proposiciones || [], licitacion: w.licitacion }; },
      create: async (id: string, data: any) => this.request("POST", `/licitaciones/${id}/proposiciones`, data),
      revisarDocumentacion: async (licitacionId: string, proposicionId: string, data: {
        documentos_soporte: string[]; firma_valida: boolean; cumplimiento_documental: boolean; dictamen: string;
      }) => this.request("POST", `/licitaciones/${licitacionId}/proposiciones/${proposicionId}/revision-documental`, data),
    },
    evaluacion: {
      evaluar: async (id: string, review?: { revision_esperada: number; insumos: Record<string, import('./licitacion-types').EvaluationInputs> }) => this.request<any>("POST", `/licitaciones-obra/expediente/${id}/evaluar`, review),
    },
    fallo: {
      emitir: async (id: string, data: any) => this.request<any>("POST", `/licitaciones-obra/expediente/${id}/fallo`, data),
    },
    contrato: {
      generar: async (id: string, data: any) => this.request<any>("POST", `/licitaciones-obra/expediente/${id}/contrato`, data),
    },
    estimaciones: {
      list: async (id: string) => this.request<any>("GET", `/licitaciones-obra/expediente/${id}/estimaciones`),
      create: async (id: string, data: any) => this.request<any>("POST", `/licitaciones-obra/expediente/${id}/estimaciones`, data),
    },
    finiquito: {
      generar: async (id: string, data: any) => this.request<any>("POST", `/licitaciones-obra/expediente/${id}/finiquito`, data),
      terminarContrato: async (id: string) => this.request<any>("POST", `/licitaciones-obra/expediente/${id}/contrato/terminar`),
    },
    resumenCiclo: async (id: string) => this.request<any>("GET", `/licitaciones-obra/expediente/${id}/workspace`),
  };

  // ═══════════════════════════════════════════════════════════════════════
  // PROCUREMENT — DOMINIO DE AUTOMATIZACIÓN DE LICITACIONES
  // ═══════════════════════════════════════════════════════════════════════

  procurement = {
    catalog: async () => this.request<any>("GET", "/procurement/catalog"),
    list: async (params?: { state?: string; jurisdiction_code?: string; expediente_id?: string }) => {
      const query = new URLSearchParams();
      Object.entries(params || {}).forEach(([k, v]) => { if (v) query.set(k, v); });
      return this.request<Array<any>>("GET", `/procurement/tenders${query.toString() ? `?${query}` : ""}`);
    },
    create: async (data: any) => this.request<any>("POST", "/procurement/tenders", data),
    get: async (id: string) => this.request<any>("GET", `/procurement/tenders/${id}`),
    artifacts: async (id: string) => this.request<any[]>("GET", `/procurement/tenders/${id}/artifacts`),
    ingest: async (id: string, files: File[], sourceRole = "CONVOCATORIA") => {
      const results: any[] = [];
      for (const file of files) {
        const form = new FormData();
        form.append("file", file);
        form.append("source_role", sourceRole);
        results.push(await this.request<any>("POST", `/procurement/tenders/${id}/sources`, form));
      }
      return results;
    },
    requirementCandidates: async (id: string) => this.request<any[]>("GET", `/procurement/tenders/${id}/requirements/candidates`),
    confirmRequirementCandidates: async (id: string, candidates: any[]) => this.request<any[]>("POST", `/procurement/tenders/${id}/requirements/candidates/confirm`, candidates),
    deriveRequirements: async (id: string) => this.request<any[]>("POST", `/procurement/tenders/${id}/requirements/derive`),
    readiness: async (id: string) => this.request<any>("GET", `/procurement/tenders/${id}/readiness`),
    resolveJurisdiction: async (id: string) => this.request<any>("POST", `/procurement/tenders/${id}/jurisdiction`),
    run: async (id: string) => this.request<any>("POST", `/procurement/tenders/${id}/run`),
    compile: async (id: string) => this.request<any[]>("POST", `/procurement/tenders/${id}/compile`),
    enqueueRun: async (id: string, idempotencyKey: string) => this.request<any>("POST", `/procurement/tenders/${id}/jobs/run`, undefined, { headers: { "Idempotency-Key": idempotencyKey } }),
    enqueueCompile: async (id: string, idempotencyKey: string) => this.request<any>("POST", `/procurement/tenders/${id}/jobs/compile`, undefined, { headers: { "Idempotency-Key": idempotencyKey } }),
    job: async (jobId: string) => this.request<any>("GET", `/procurement/jobs/${jobId}`),
    approvalManifest: async (id: string) => this.request<{ artifact_manifest_sha256: string; originals: { revision: number; artifacts: Array<{ id: string; code: string; version: number; sha256: string; storage_path: string }> } }>("GET", `/procurement/tenders/${id}/approvals/manifest`),
    originalArtifact: async (id: string, artifactId: string) => this.request<{ url: string; sha256: string }>("GET", `/procurement/tenders/${id}/artifacts/${artifactId}/original`),
    approve: async (id: string, data: { role: string; decision: "APPROVED" | "REJECTED"; reason?: string; expected_artifact_manifest_sha256?: string }) => this.request<any>("POST", `/procurement/tenders/${id}/approvals`, data),
    createRevision: async (id: string, reason: string, formatAmendment?: {
      version: string;
      format_definitions: Record<string, unknown>[];
      expected_revision: number;
      base_evidence_id: string;
      amendment_evidence_id: string;
    }) => this.request<any>("POST", `/procurement/tenders/${id}/revisions`, {
      reason,
      ...(formatAmendment && { format_amendment: formatAmendment }),
    }),
    signArtifact: async (id: string, artifactId: string, data: {
      certificadoCer: File;
      certificadoKey: File;
      password: string;
      idempotencyKey: string;
      razon?: string;
      ubicacion?: string;
      usarTsa?: boolean;
    }) => {
      const form = new FormData();
      form.append("certificado_cer", data.certificadoCer);
      form.append("certificado_key", data.certificadoKey);
      form.append("password", data.password);
      form.append("razon", data.razon || "Firma de artefacto de proposición");
      form.append("ubicacion", data.ubicacion || "México");
      form.append("usar_tsa", String(data.usarTsa !== false));
      return this.request<any>("POST", `/procurement/tenders/${id}/artifacts/${artifactId}/sign`, form, {
        headers: { "Idempotency-Key": data.idempotencyKey },
      });
    },
    submission: async (id: string) => this.request<any>("POST", `/procurement/tenders/${id}/submission`),
    submissionDownload: async (id: string) => this.request<any>("GET", `/procurement/tenders/${id}/submission/download`),
    freeze: async (id: string) => this.request<any>("POST", `/procurement/tenders/${id}/freeze`),
    /** Semi-auto: adjunta presupuesto programable al modelo canónico (usuario elige presupuesto). */
    /** Persiste facts + checklist del panel (semi-auto, no inventa partidas). */
    applySemiAutoReview: async (
      id: string,
      data: {
        authority?: string;
        object?: string;
        budget_total_reference?: number;
        format_checklist?: Array<{
          code: string;
          title?: string;
          category?: string;
          required?: boolean;
          status: string;
          notes?: string;
        }>;
        reason?: string;
      },
    ) => this.request<any>("POST", `/procurement/tenders/${id}/semi-auto-review`, data),
    workspaceDocuments: async (id: string) => this.request<any[]>("GET", `/procurement/tenders/${id}/workspace/documents`),
    workspaceCreateDocument: async (id: string, data: any) => this.request<any>("POST", `/procurement/tenders/${id}/workspace/documents`, data),
    workspaceDocumentTemplates: (id: string) =>
      this.request<{ artifact_code: string; name: string }[]>("GET", `/procurement/tenders/${id}/workspace/document-templates`),
    workspaceEditor: (id: string, documentId: string) =>
      this.request<WorkspaceEditor>("GET", `/procurement/tenders/${id}/workspace/documents/${documentId}/editor`),
    workspaceRender: (id: string, documentId: string, expected_row_version: number, values: Record<string, string>, template_token: string | null) =>
      this.request<WorkspaceEditor>("POST", `/procurement/tenders/${id}/workspace/documents/${documentId}/render`, { expected_row_version, values, template_token }),
    workspaceRevisionFile: async (id: string, documentId: string, version: number) => {
      const path = `/api/v1/procurement/tenders/${id}/workspace/documents/${documentId}/versions/${version}/file`;
      const headers: Record<string, string> = {};
      if (this.token) headers.Authorization = `Bearer ${this.token}`;
      const response = await this.fetchWithSession(`${this.baseUrl}${path}`, { headers, credentials: "include" });
      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.message || error?.detail || `No se pudo abrir el archivo (HTTP ${response.status}).`);
      }
      return response.blob();
    },
    workspaceGetDocument: async (id: string, documentId: string) =>
      this.request<WorkspaceDocumentDetail>("GET", `/procurement/tenders/${id}/workspace/documents/${documentId}`),
    workspaceUpdateDocument: async (id: string, documentId: string, data: {
      content_text: string;
      content_model: Record<string, unknown>;
      expected_row_version: number;
    }) => this.request<WorkspaceDocumentDetail>("PUT", `/procurement/tenders/${id}/workspace/documents/${documentId}`, data),
    workspaceHistory: async (id: string, documentId: string) =>
      this.request<WorkspaceDocumentRevision[]>("GET", `/procurement/tenders/${id}/workspace/documents/${documentId}/history`),
    workspaceRegenerate: async (id: string, documentId: string, data: any) => this.request<any>("POST", `/procurement/tenders/${id}/workspace/documents/${documentId}/regenerate`, data),
    workspaceLock: async (id: string, documentId: string, locked: boolean) => this.request<any>("PATCH", `/procurement/tenders/${id}/workspace/documents/${documentId}/lock`, { locked }),
    bridgeLicitacion: async (id: string, licitacion_id: string, relationship_type = "PRIMARY") => this.request<any>("POST", `/procurement/tenders/${id}/bridge/licitacion`, { licitacion_id, relationship_type }),
    bridgeSync: async (id: string, licitacion_id: string, data: any) => this.request<any>("POST", `/procurement/tenders/${id}/bridge/licitacion/${licitacion_id}/sync`, data),
    hydrateFromPresupuesto: async (
      id: string,
      opts?: { presupuesto_id?: string; overwrite_economic?: boolean },
    ) => {
      const q = new URLSearchParams();
      if (opts?.presupuesto_id) q.set("presupuesto_id", opts.presupuesto_id);
      if (opts?.overwrite_economic === false) q.set("overwrite_economic", "false");
      const qs = q.toString() ? `?${q}` : "";
      return this.request<any>("POST", `/procurement/tenders/${id}/hydrate-from-presupuesto${qs}`);
    },
    recommendProcedure: async (payload: any) =>
      this.request<any>("POST", "/procurement/recommend-procedure", payload),
    recommendProcedureForTender: async (id: string, payload: any) =>
      this.request<any>("POST", `/procurement/tenders/${id}/recommend-procedure`, payload),
    derivePropositionStructure: async (payload: any) =>
      this.request<any>("POST", "/procurement/derive-proposition-structure", payload),
  };

  // ═══════════════════════════════════════════════════════════════════════
  // INTEGRACIÓN ZIP 3: CONSULTOR LEGAL LEGL
  // ═══════════════════════════════════════════════════════════════════════

  legal = {
    cobertura: (): Promise<CoberturaCorpus> => this.request('GET', '/legal/cobertura'),
    // BUG ORIGINAL: legal_consultor.py declara query/ley/fase/monto/mensaje
    // como parámetros escalares sueltos (sin modelo Pydantic de body), así
    // que FastAPI los espera como query params -- pero aquí se mandaban
    // como JSON body. El backend nunca los habría visto (422 por campos
    // requeridos faltantes). Se corrige armando el query string. También
    // faltaban listarCategorias/buscarPorCategoria (endpoints reales) y
    // sobraba listarFases (no existe ese endpoint en el backend).
    consultar: async (query: string, ley?: string, fase?: string) => {
      const params = new URLSearchParams({ query });
      if (ley) params.set("ley", ley);
      if (fase) params.set("fase", fase);
      return this.request("POST", `/legal/consultar?${params.toString()}`);
    },
    determinarProcedimiento: async (monto: number, tipoObra?: string) => {
      const params = new URLSearchParams({ monto: String(monto), tipo_obra: tipoObra || "obra_publica" });
      return this.request("POST", `/legal/procedimiento?${params.toString()}`);
    },
    // Fechas de cierre/fallo en días HÁBILES reales (calendario LFT Art. 74
    // vía app/core/calendar.py) -- ver legal_consultor.py::calcular_fechas_procedimiento.
    // Corrige que CalculadoraPlazos.tsx calculaba estas fechas en el
    // navegador con días calendario.
    calcularFechas: async (fechaInicio: string, procedimiento: string): Promise<{
      fecha_inicio: string;
      fecha_cierre_estimada: string;
      fecha_fallo_estimada: string;
      plazos: Record<string, number>;
    }> => {
      const params = new URLSearchParams({ fecha_inicio: fechaInicio, procedimiento });
      return this.request("POST", `/legal/calcular-fechas?${params.toString()}`);
    },
    obtenerArticulo: async (ley: string, numero: string) => 
      this.request("GET", `/legal/articulo/${ley}/${numero}`),
    listarLeyes: async () => this.request("GET", "/legal/leyes"),
    listarCategorias: async () => this.request("GET", "/legal/categorias"),
    buscarPorCategoria: async (categoriaId: string, maxResultados: number = 10) => {
      const params = new URLSearchParams({ max_resultados: String(maxResultados) });
      return this.request("POST", `/legal/categoria/${categoriaId}?${params.toString()}`);
    },
    chat: async (mensaje: string): Promise<{
      respuesta: string;
      intencion_detectada: string;
      parametros: Record<string, unknown>;
    }> => {
      const params = new URLSearchParams({ mensaje });
      return this.request("POST", `/legal/chat?${params.toString()}`);
    },
  };

  // ═══════════════════════════════════════════════════════════════════════
  // BÚSQUEDA GLOBAL
  // ═══════════════════════════════════════════════════════════════════════

  search = {
    global: async (
      q: string,
      opts?: { dominios?: string[]; fechaInicio?: string; fechaFin?: string; skip?: number; limit?: number },
    ) => {
      const params = new URLSearchParams({ q });
      (opts?.dominios || []).forEach((d) => params.append("dominios", d));
      if (opts?.fechaInicio) params.set("fecha_inicio", opts.fechaInicio);
      if (opts?.fechaFin) params.set("fecha_fin", opts.fechaFin);
      if (opts?.skip !== undefined) params.set("skip", String(opts.skip));
      if (opts?.limit !== undefined) params.set("limit", String(opts.limit));
      return this.request("GET", `/search/global?${params.toString()}`);
    },
    porTags: async (tags: string[], operador: "AND" | "OR" = "AND", skip = 0, limit = 100) => {
      const params = new URLSearchParams({ operador, skip: String(skip), limit: String(limit) });
      tags.forEach((t) => params.append("tags", t));
      return this.request("GET", `/search/tags?${params.toString()}`);
    },
    sugerencias: async (q: string, dominio = "documentos", limit = 10) => {
      const params = new URLSearchParams({ q, dominio, limit: String(limit) });
      return this.request("GET", `/search/sugerencias?${params.toString()}`);
    },
  };

  // ═══════════════════════════════════════════════════════════════════════
  // EXPEDIENTES — VISTAS AVANZADAS (resumen cross-domain, timeline)
  // ═══════════════════════════════════════════════════════════════════════

  expedientesAdvanced = {
    resumenCompleto: async (expedienteId: string) =>
      this.request("GET", `/expedientes-advanced/${expedienteId}/resumen-completo`),
    timeline: async (expedienteId: string) =>
      this.request("GET", `/expedientes-advanced/${expedienteId}/timeline`),
    busquedaAvanzada: async (params: Record<string, string | number | boolean | undefined>) => {
      const searchParams = new URLSearchParams();
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined) searchParams.set(k, String(v));
      });
      return this.request("GET", `/expedientes-advanced/busqueda-avanzada?${searchParams.toString()}`);
    },
    cambiarEstado: async (expedienteId: string, nuevoEstado: string, motivo?: string) =>
      this.request("POST", `/expedientes-advanced/${expedienteId}/cambiar-estado`, { nuevo_estado: nuevoEstado, motivo }),
  };

  // ═══════════════════════════════════════════════════════════════════════
  // TRANSPARENCIA — Portal público (sin auth)
  // ═══════════════════════════════════════════════════════════════════════

  transparencia = {
    expedientesPublicos: async (params?: { q?: string; estado?: string; skip?: number; limit?: number }) => {
      const searchParams = new URLSearchParams();
      if (params?.q) searchParams.set("q", params.q);
      if (params?.estado) searchParams.set("estado", params.estado);
      searchParams.set("skip", String(params?.skip ?? 0));
      searchParams.set("limit", String(params?.limit ?? 100));
      return this.request("GET", `/transparencia/expedientes-publicos?${searchParams.toString()}`);
    },
    expediente: async (expedienteId: string) =>
      this.request("GET", `/transparencia/expediente/${expedienteId}`),
    lineaTiempo: async (expedienteId: string) =>
      this.request("GET", `/transparencia/linea-tiempo/${expedienteId}`),
    sancionesPublicas: async (params?: { proveedorId?: string; skip?: number; limit?: number }) => {
      const searchParams = new URLSearchParams();
      if (params?.proveedorId) searchParams.set("proveedor_id", params.proveedorId);
      searchParams.set("skip", String(params?.skip ?? 0));
      searchParams.set("limit", String(params?.limit ?? 50));
      return this.request("GET", `/transparencia/sanciones-publicas?${searchParams.toString()}`);
    },
  };

  // ═══════════════════════════════════════════════════════════════════════
  // ENTITLEMENTS / PAGOS (freemium: Free/Intermedio/Pro/Enterprise)
  // ═══════════════════════════════════════════════════════════════════════

  entitlements = {
    miPlan: async () => this.request("GET", "/entitlements/mi-plan"),
    modulos: async () => this.request("GET", "/entitlements/modulos"),
    // GodAdmin
    adminListarTenants: async () => this.request("GET", "/entitlements/admin/tenants"),
    adminActivarPlanManual: async (tenantId: string, plan: string, diasVigencia = 31) =>
      this.request("PATCH", `/entitlements/admin/tenants/${tenantId}/plan`, { plan, dias_vigencia: diasVigencia }),
    adminListarPlanes: async () => this.request("GET", "/entitlements/admin/planes"),
    adminActualizarPlan: async (plan: string, cambios: Record<string, unknown>) =>
      this.request("PATCH", `/entitlements/admin/planes/${plan}`, cambios),
    adminListarModulos: async () => this.request("GET", "/entitlements/admin/modulos"),
    adminActualizarModulo: async (appId: string, cambios: Record<string, unknown>) =>
      this.request("PATCH", `/entitlements/admin/modulos/${appId}`, cambios),
  };

  pagos = {
    crearCheckout: async (plan: string, proveedor: "MERCADOPAGO" | "STRIPE" = "MERCADOPAGO") =>
      this.request("POST", "/pagos/checkout", { plan, proveedor }),
    cancelar: async () => this.request("POST", "/pagos/cancelar"),
  };

}

export default MegalodonClient;
