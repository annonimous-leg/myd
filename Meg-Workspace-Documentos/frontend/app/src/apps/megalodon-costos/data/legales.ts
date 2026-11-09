/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

// =============================================================================
// Megalodon CostOS — Mexican Legal Constants (LOPSRM / LAASSP / SAT)
// =============================================================================

/** LOPSRM Art. 34–47: Indirect cost factor ceilings */
export const LOPSRM_INDIRECTOS = {
  /** Art. 40: Max indirect cost factor (factor de indirectos) */
  MAX_FACTOR_INDIRECTOS: 0.15,
  /** Art. 40: Max financing cost factor */
  MAX_FACTOR_FINANCIAMIENTO: 0.03,
  /** Art. 45: Max profit margin (utilidad) as decimal */
  MAX_UTILIDAD: 0.10,
  /** Art. 37: Max contingency reserve */
  MAX_CONTINGENCIA: 0.05,
  /** Art. 34: Min direct cost percentage of total */
  MIN_COSTO_DIRECTO_PCT: 0.70,
  /** Art. 46: Additional charge for remote/rural works */
  RECARGO_ZONA_REMOTA: 0.02,
} as const;

/** LOPSRM procedural thresholds (Art. 26–33) */
export const LOPSRM_UMBRALES = {
  /** Art. 26: Lower threshold for simplified procedure (MXN pesos) */
  LICITACION_PUBLICA_MIN: 50_000_000,
  /** Art. 27: Threshold for invited bidders procedure */
  INVITACION_MIN: 5_000_000,
  /** Art. 28: Direct award maximum */
  ADJUDICACION_DIRECTA_MAX: 1_500_000,
  /** Art. 29: Emergency procurement threshold */
  EMERGENCIA_MAX: 10_000_000,
  /** Art. 33: Price ceiling for unit-price contracts */
  TOPE_PRECIO_UNITARIO: 100_000_000,
} as const;

/** SAT tax compliance rules (32D & related) */
export const SAT_REGIMEN = {
  /** 32-D: CFDI requirement since 2014 */
  CFDI_OBLIGATORIO_DESDE: 2014,
  /** 32-D: e.firma (FIEL) required for electronic invoicing */
  EFIRMA_REQUERIDA: true,
  /** 32-D: Monthly VAT filing deadline (days after month end) */
  DIAS_VENCIMIENTO_IVA: 17,
  /** ISR withholding rate for subcontracting */
  RETENCION_ISR_SUBCONTRATO: 0.10,
  /** IVA rate (2024) */
  TASA_IVA: 0.16,
  /** RET IVA rate for construction subcontractors */
  RETENCION_IVA: 0.08,
  /** ISR provisional payment deadline (days) */
  DIAS_PAGO_PROVISIONAL_ISR: 17,
  /** e.firma certificate validity (years) */
  VIGENCIA_CERT_EFIRMA_ANIOS: 4,
  /** SAT opinion valid statuses */
  OPINION_CUMPLIMIENTO_VALIDA: ['POSITIVO', 'EXTRAVIADA'] as string[],
} as const;

/** FSR (Factor de Salario Real) constants per LAASSP Art. 12 */
export const FSR_CONST = {
  /** Official working days per year */
  DIAS_ANIO: 365,
  /** Paid non-working days (holidays + weekends) */
  DIAS_NO_LABORABLES_PAGADOS: 74,
  /** Base formula: FSR = PS * (TP / TL) + (TP / TL) */
  FORMULA: {
    /** PS = fraccion seguridad social (employer contribution %) */
    FRACCION_SEGURIDAD_SOCIAL_DEFAULT: 0.3056,
    /** TP = dias pagados per year */
    DIAS_PAGADOS: 365,
    /** TL = dias laborados per year (default) */
    DIAS_LABORADOS: 291,
  },
  /** LAASSP Art. 12: Minimum FSR value */
  FSR_MINIMO: 1.0,
  /** LAASSP Art. 12: Typical FSR range upper bound */
  FSR_MAXIMO_TIPICO: 1.8,
  /** IMSS employer contribution components */
  IMSS_PATRONAL: {
    RIESGO_TRABAJO: 0.02375,
    ENFERMEDAD_MATERNIDAD: 0.20400,
    INVALIDEZ_VIDA: 0.01750,
    GUARDERIA: 0.01000,
    RETIRO: 0.02000,
    CESANTIA: 0.03125,
    INFONAVIT: 0.05000,
  },
} as const;

/** LFT (Labor Law) salary compliance */
export const LFT_SALARIOS = {
  /** 2024 general minimum wage (MXN per day) */
  SALARIO_MINIMO_DIARIO_2024: 248.93,
  /** Professional minimum wage multiplier */
  MULTIPLICADOR_PROFESIONAL: 1.5,
  /** Vacation days per year (min) */
  DIAS_VACACIONES_MIN: 12,
  /** Aguinaldo ( Christmas bonus): min 15 days */
  AGUINALDO_DIAS: 15,
  /** Profit sharing (PTU) — max 3 months salary equivalent */
  PTU_TOPE_MESES: 3,
} as const;

/** Machinery hourly cost validation norms */
export const MAQUINARIA_NORMAS = {
  /** ACM (Análisis de Costos de Maquinaria) required fields */
  CAMPOS_ACM: [
    'costo_adquisicion',
    'vida_economica',
    'horas_anio_trabajo',
    'factor_mantenimiento',
    'combustible_hora',
    'lubricante_hora',
    'operador_hora',
    'seguro_anual',
    'almacenaje_anual',
  ] as string[],
  /** Max depreciation factor per year */
  DEPRECIACION_MAX_ANUAL: 0.20,
  /** Min hours per year for economic life calculation */
  HORAS_MIN_ANIO: 1000,
  /** Fuel cost max variation from catalog (%) */
  VARIACION_COMBUSTIBLE_MAX: 0.15,
  /** Maintenance factor typical range */
  FACTOR_MANTENIMIENTO_RANGO: [0.30, 0.60] as [number, number],
  /** Insurance as % of acquisition cost (annual) */
  SEGURO_PCT_ANUAL: 0.02,
} as const;

/** Overhead factor validation */
export const SOBRECOSTOS = {
  /** Central administration (field office) max */
  GASTOS_ADMIN_CENTRAL_MAX: 0.08,
  /** Site administration max */
  GASTOS_ADMIN_OBRA_MAX: 0.05,
  /** Camp facilities max */
  CAMPAMENTO_MAX: 0.03,
  /** Total overhead max */
  GASTOS_INDIRECTOS_OBRA_MAX: 0.15,
  /** Quality control as % of direct cost */
  CONTROL_CALIDAD_PCT: 0.02,
  /** Safety equipment as % of direct cost */
  SEGURIDAD_PCT: 0.015,
  /** Environmental management as % of direct cost */
  PROTECCION_AMBIENTAL_PCT: 0.01,
} as const;

/** INFONAVIT & IMSS compliance */
export const SEGURIDAD_SOCIAL = {
  /** IMSS registration required if > 1 worker */
  IMSS_REGISTRO_OBRERO_MIN: 1,
  /** INFONAVIT registration required if > 1 worker */
  INFONAVIT_REGISTRO_OBRERO_MIN: 1,
  /** SAR (Sistema de Ahorro para el Retiro) contribution % */
  SAR_PATRONAL_PCT: 0.02,
  /** Max days to register new employee */
  DIAS_ALTA_IMSS: 5,
  /** Monthly INFONAVIT payment: 5% of payroll */
  INFONAVIT_APORTACION_PCT: 0.05,
  /** RT premium max (% of base contribution salary) */
  PRIMA_RT_MAX: 0.15,
} as const;

/** Validation rule IDs */
export const REGLAS_VALIDACION = {
  /** SAT 32-D: e.firma + CFDI compliance */
  REG_FIS_32D: 'REG-FIS-32D',
  /** IMSS/INFONAVIT: Social security registration */
  REG_FIS_SEG_SOCIAL: 'REG-FIS-SEG-SOCIAL',
  /** e.firma certificate validity */
  REG_ADM_EFIRMA: 'REG-ADM-EFIRMA',
  /** FSR arithmetic validation */
  REG_ECO_FSR: 'REG-ECO-FSR',
  /** Machinery hourly costs */
  REG_ECO_MAQUINARIA: 'REG-ECO-MAQUINARIA',
  /** Overhead factors within norms */
  REG_ECO_SOBRECOSTOS: 'REG-ECO-SOBRECOSTOS',
} as const;

/** Procedure determination types per LOPSRM */
export type TipoProcedimiento =
  | 'LICITACION_PUBLICA'
  | 'INVITACION_A_TRES'
  | 'ADJUDICACION_DIRECTA'
  | 'EMERGENCIA'
  | 'REGLADA'
  | 'NO_APLICA';

/** Determine procurement procedure per LOPSRM Art. 26-33 */
export function determinarProcedimiento(monto: number): TipoProcedimiento {
  if (monto >= LOPSRM_UMBRALES.LICITACION_PUBLICA_MIN) return 'LICITACION_PUBLICA';
  if (monto >= LOPSRM_UMBRALES.INVITACION_MIN) return 'INVITACION_A_TRES';
  if (monto <= LOPSRM_UMBRALES.ADJUDICACION_DIRECTA_MAX) return 'ADJUDICACION_DIRECTA';
  if (monto <= LOPSRM_UMBRALES.EMERGENCIA_MAX) return 'EMERGENCIA';
  return 'REGLADA';
}

/** Get human-readable procedure name */
export function nombreProcedimiento(tipo: TipoProcedimiento): string {
  const nombres: Record<TipoProcedimiento, string> = {
    LICITACION_PUBLICA: 'Licitación Pública (Art. 26)',
    INVITACION_A_TRES: 'Invitación a Cuando Menos Tres (Art. 27)',
    ADJUDICACION_DIRECTA: 'Adjudicación Directa (Art. 28)',
    EMERGENCIA: 'Adjudicación Directa por Emergencia (Art. 29)',
    REGLADA: 'Contratación Reglada',
    NO_APLICA: 'No Aplica',
  };
  return nombres[tipo];
}
