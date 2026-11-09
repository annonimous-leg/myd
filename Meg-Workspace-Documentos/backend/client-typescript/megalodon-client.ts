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
  monto_utilidad: number;
  monto_riesgo?: number | null;
  monto_impuesto: number;
  monto_total: number;
  moneda: string;
  factor_indirecto: number;
  factor_utilidad: number;
  factor_impuesto: number;
  factor_riesgo?: number | null;
  metadatos?: {
    parametros_costeo?: ParametrosCosteoSnapshot;
    [key: string]: unknown;
  } | null;
  zona_economica: string;
  created_at?: string;
  creado_por_id?: string;
}

export interface ParametrosCosteoInput {
  factor_indirecto: number;
  factor_utilidad: number;
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
      method,
      headers,
      ...options,
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

    const response = await fetch(url, config);

    if (!response.ok) {
      const error = await response.json().catch(() => ({
        message: `HTTP ${response.status}: ${response.statusText}`,
      }));
      throw new Error(error.message || `HTTP ${response.status}`);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return response.json();
  }

  auth = {
    login: async (username: string, password: string): Promise<Token> => {
      const formData = new URLSearchParams();
      formData.append("username", username);
      formData.append("password", password);

      const token = await this.request<Token>("POST", "/auth/login", formData, {
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      });

      this.setToken(token.access_token);
      return token;
    },

    register: async (data: {
      email: string;
      password: string;
      full_name: string;
      tenant_id: string;
      rfc?: string;
      curp?: string;
      role?: string;
    }): Promise<User> => {
      return this.request<User>("POST", "/auth/register", data);
    },

    refresh: async (refreshToken: string): Promise<Token> => {
      return this.request<Token>("POST", "/auth/refresh", { refresh_token: refreshToken });
    },

    me: async (): Promise<User> => {
      return this.request<User>("GET", "/auth/me");
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

    /** Antes no existía -- el backend nunca exponía cómo bajar un
     * documento ya subido. Regresa el blob listo para descargar o mostrar. */
    descargarDocumento: async (expedienteId: string, documentoId: string): Promise<Blob> => {
      const response = await fetch(
        `${this.baseUrl}/api/v1/expedientes/${expedienteId}/documentos/${documentoId}/descarga`,
        { headers: this.token ? { Authorization: `Bearer ${this.token}` } : {} }
      );
      if (!response.ok) throw new Error("Error al descargar documento");
      return response.blob();
    },
  };

  presupuestos = {
    create: async (expedienteId: string, data: {
      nombre: string;
      descripcion?: string;
      partidas: Array<{
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
        { headers: this.token ? { Authorization: `Bearer ${this.token}` } : {} }
      );
      if (!response.ok) throw new Error("Error al descargar Excel");
      return response.blob();
    },

    exportPdf: async (expedienteId: string, presupuestoId: string): Promise<Blob> => {
      const response = await fetch(
        `${this.baseUrl}/api/v1/presupuestos/${expedienteId}/presupuestos/${presupuestoId}/pdf`,
        { headers: this.token ? { Authorization: `Bearer ${this.token}` } : {} }
      );
      if (!response.ok) throw new Error("Error al descargar PDF");
      return response.blob();
    },

    validarSobrecostos: async (expedienteId: string, presupuestoId: string, presupuestoBaseId: string): Promise<any> => {
      return this.request<any>("POST", `/presupuestos/${expedienteId}/presupuestos/${presupuestoId}/validar-sobrecostos?presupuesto_base_id=${presupuestoBaseId}`);
    },
  };

  bim = {
    /** Sube y procesa un IFC de una vez: registra el modelo, extrae
     * cantidades reales (Qto del IFC + respaldo geométrico) y la malla
     * para renderizar en Three.js. Síncrono por ahora (ver nota en
     * app/api/v1/bim.py sobre la pieza de storage que falta para hacerlo
     * asíncrono con Celery). */
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
      data: { nombre?: string; parametros_costeo: ParametrosCosteoInput },
    ): Promise<Presupuesto> => {
      return this.request<Presupuesto>(
        "POST",
        `/bim/${expedienteId}/modelos/${modeloId}/generar-presupuesto`,
        data ?? {},
      );
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

    gantt: async (expedienteId: string, programaId: string): Promise<any[]> => {
      // Vacío hasta que se corra calcularCPM al menos una vez -- el gantt
      // sale del resultado_cpm ya guardado, no se recalcula aparte.
      return this.request<any[]>("GET", `/programacion/${expedienteId}/programas/${programaId}/gantt`);
    },

    curvaS: async (expedienteId: string, programaId: string): Promise<any[]> => {
      return this.request<any[]>("GET", `/programacion/${expedienteId}/programas/${programaId}/curva-s`);
    },

    rutaCritica: async (expedienteId: string, programaId: string): Promise<any> => {
      return this.request<any>("GET", `/programacion/${expedienteId}/programas/${programaId}/ruta-critica`);
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

    /** Qué jurisdicciones existen (aunque sea con datos placeholder) y
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

  websocket = {
    connect: (token: string): WebSocket => {
      const wsUrl = this.baseUrl.replace("http", "ws");
      this.ws = new WebSocket(`${wsUrl}/ws/progreso?token=${token}`);

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
    precioConIVA: async (id: string, tasaIVA: number = 0.16) => {
      return this.request("GET", `/catalogo-apu/${id}/precio-con-iva?tasa_iva=${tasaIVA}`);
    },
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
      costoDesglosado: async (id: string, cantidad: number = 1, tasaIVA: number = 0.16) => {
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
      crear: async (data: any) => {
        return this.request("POST", "/compliance/reglas", data);
      },
      listar: async (params?: { tipo_procedimiento?: string; etapa?: string; activa?: boolean; skip?: number; limit?: number }) => {
        const query = new URLSearchParams(params as any).toString();
        return this.request("GET", `/compliance/reglas?${query}`);
      },
      obtener: async (id: string) => {
        return this.request("GET", `/compliance/reglas/${id}`);
      },
      actualizar: async (id: string, data: any) => {
        return this.request("PATCH", `/compliance/reglas/${id}`, data);
      },
      eliminar: async (id: string) => {
        return this.request("DELETE", `/compliance/reglas/${id}`);
      },
    },
    inconformidades: {
      crear: async (data: any) => {
        return this.request("POST", "/compliance/inconformidades", data);
      },
      listar: async (params?: { estado?: string; severidad?: string; expediente_id?: string; skip?: number; limit?: number }) => {
        const query = new URLSearchParams(params as any).toString();
        return this.request("GET", `/compliance/inconformidades?${query}`);
      },
      obtener: async (id: string) => {
        return this.request("GET", `/compliance/inconformidades/${id}`);
      },
      actualizar: async (id: string, data: any) => {
        return this.request("PATCH", `/compliance/inconformidades/${id}`, data);
      },
    },
    sanciones: {
      crear: async (data: any) => {
        return this.request("POST", "/compliance/sanciones", data);
      },
      listar: async (params?: { proveedor_id?: string; tipo?: string; skip?: number; limit?: number }) => {
        const query = new URLSearchParams(params as any).toString();
        return this.request("GET", `/compliance/sanciones?${query}`);
      },
      obtener: async (id: string) => {
        return this.request("GET", `/compliance/sanciones/${id}`);
      },
    },
    evaluar: async (expedienteId: string) => {
      return this.request("POST", `/compliance/evaluar/${expedienteId}`);
    },
  };

  // ═══════════════════════════════════════════════════════════════════════
  // FASE 2 — CONTRATOS
  // ═══════════════════════════════════════════════════════════════════════

  contratos = {
    crear: async (data: any) => {
      return this.request("POST", "/contratos", data);
    },
    listar: async (params?: { estado?: string; expediente_id?: string; proveedor_id?: string; skip?: number; limit?: number }) => {
      const query = new URLSearchParams(params as any).toString();
      return this.request("GET", `/contratos?${query}`);
    },
    obtener: async (id: string) => {
      return this.request("GET", `/contratos/${id}`);
    },
    actualizar: async (id: string, data: any) => {
      return this.request("PATCH", `/contratos/${id}`, data);
    },
    transicionar: async (id: string, nuevoEstado: string) => {
      return this.request("POST", `/contratos/${id}/transicionar?nuevo_estado=${nuevoEstado}`);
    },
    resumen: async (id: string) => {
      return this.request("GET", `/contratos/${id}/resumen`);
    },
    modificatorios: {
      crear: async (contratoId: string, data: any) => {
        return this.request("POST", `/contratos/${contratoId}/modificatorios`, data);
      },
      listar: async (contratoId: string) => {
        return this.request("GET", `/contratos/${contratoId}/modificatorios`);
      },
    },
    garantias: {
      crear: async (contratoId: string, data: any) => {
        return this.request("POST", `/contratos/${contratoId}/garantias`, data);
      },
      listar: async (contratoId: string) => {
        return this.request("GET", `/contratos/${contratoId}/garantias`);
      },
      vigencia: async (contratoId: string) => {
        return this.request("GET", `/contratos/${contratoId}/garantias/vigencia`);
      },
    },
    entregables: {
      crear: async (contratoId: string, data: any) => {
        return this.request("POST", `/contratos/${contratoId}/entregables`, data);
      },
      listar: async (contratoId: string) => {
        return this.request("GET", `/contratos/${contratoId}/entregables`);
      },
    },
    penalizaciones: {
      crear: async (contratoId: string, data: any) => {
        return this.request("POST", `/contratos/${contratoId}/penalizaciones`, data);
      },
    },
  };

  // ═══════════════════════════════════════════════════════════════════════
  // FASE 2 — LICITACIONES
  // ═══════════════════════════════════════════════════════════════════════

  licitaciones = {
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
      crear: async (licitacionId: string, data: any) => {
        return this.request("POST", `/licitaciones/${licitacionId}/junta-aclaraciones`, data);
      },
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
    planeacion: {
      create: async (data: any) => this.request("POST", "/licitaciones-obra/planeacion", data),
      get: async (id: string) => this.request("GET", `/licitaciones-obra/planeacion/${id}`),
    },
    convocatoria: {
      publicar: async (id: string) => this.request("POST", `/licitaciones-obra/${id}/convocatoria`),
      get: async (id: string) => this.request("GET", `/licitaciones-obra/${id}/convocatoria`),
    },
    proposiciones: {
      list: async (id: string) => this.request("GET", `/licitaciones-obra/${id}/proposiciones`),
      create: async (id: string, data: any) => this.request("POST", `/licitaciones-obra/${id}/proposiciones`, data),
    },
    evaluacion: {
      evaluar: async (id: string) => this.request("POST", `/licitaciones-obra/${id}/evaluacion`),
    },
    fallo: {
      emitir: async (id: string, data: any) => this.request("POST", `/licitaciones-obra/${id}/fallo`, data),
    },
    contrato: {
      generar: async (id: string, data: any) => this.request("POST", `/licitaciones-obra/${id}/contrato`, data),
    },
    estimaciones: {
      list: async (id: string) => this.request("GET", `/licitaciones-obra/${id}/estimaciones`),
      create: async (id: string, data: any) => this.request("POST", `/licitaciones-obra/${id}/estimaciones`, data),
    },
    finiquito: {
      generar: async (id: string) => this.request("POST", `/licitaciones-obra/${id}/finiquito`),
    },
    pujas: {
      list: async (id: string) => this.request("GET", `/licitaciones-obra/${id}/pujas`),
      registrar: async (id: string, data: any) => this.request("POST", `/licitaciones-obra/${id}/pujas`, data),
    },
    garantias: {
      get: async (id: string) => this.request("GET", `/licitaciones-obra/${id}/garantias`),
    },
    bitacora: {
      get: async (id: string) => this.request("GET", `/licitaciones-obra/${id}/bitacora`),
    },
    ajusteCostos: {
      calcular: async (id: string) => this.request("POST", `/licitaciones-obra/${id}/ajuste-costos`),
    },
    compranet: {
      publicar: async (id: string) => this.request("POST", `/licitaciones-obra/${id}/publicar-compranet`),
    },
    resumenCiclo: async (id: string) => this.request("GET", `/licitaciones-obra/${id}/resumen-ciclo`),
  };

  // ═══════════════════════════════════════════════════════════════════════
  // INTEGRACIÓN ZIP 3: CONSULTOR LEGAL LEGL
  // ═══════════════════════════════════════════════════════════════════════

  legal = {
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
    obtenerArticulo: async (ley: string, numero: string) => 
      this.request("GET", `/legal/articulo/${ley}/${numero}`),
    listarLeyes: async () => this.request("GET", "/legal/leyes"),
    listarCategorias: async () => this.request("GET", "/legal/categorias"),
    buscarPorCategoria: async (categoriaId: string, maxResultados: number = 10) => {
      const params = new URLSearchParams({ max_resultados: String(maxResultados) });
      return this.request("POST", `/legal/categoria/${categoriaId}?${params.toString()}`);
    },
    chat: async (mensaje: string) => {
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
