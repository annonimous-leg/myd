/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

// =============================================================================
// Megalodon CostOS — Deterministic Validation Engine
// =============================================================================

import {
  SAT_REGIMEN,
  FSR_CONST,
  MAQUINARIA_NORMAS,
  SEGURIDAD_SOCIAL,
  LOPSRM_INDIRECTOS,
  REGLAS_VALIDACION,
} from '../data/legales';

export type ValidationStatus = 'PASS' | 'FAIL' | 'WARNING';

export interface ValidationRule {
  id: string;
  name: string;
  category: string;
  status: ValidationStatus;
  detail: string;
  evidence: string;
  fixAction?: string;
}

export interface ValidationInput {
  rfc: string;
  opinionSAT: string;
  imssStatus: string;
  infonavitStatus: string;
  efirmaValid: boolean;
  efirmaExpiryDays: number;
  fsrSeguridadSocial: number;
  fsrDiasPagados: number;
  fsrDiasLaborados: number;
  maquinariaItems: MachineryItem[];
  factorIndirectos: number;
  factorFinanciamiento: number;
  utilidad: number;
  costoDirectoPct: number;
  numWorkers: number;
  hasCFDI: boolean;
}

export interface MachineryItem {
  key: string;
  description: string;
  costoAdquisicion: number;
  vidaEconomica: number;
  horasAnio: number;
  factorMantenimiento: number;
  combustibleHora: number;
  operadorHora: number;
  seguroAnual: number;
}

/** Validate RFC format (Mexico: 12/13 chars) */
function validateRFC(rfc: string): boolean {
  const pattern = /^[A-Z&Ñ]{3,4}[0-9]{6}[A-V1-9][A-Z1-9][0-9A-Z]$/;
  return pattern.test(rfc.toUpperCase());
}

/** Compute FSR from components */
function computeFSR(ps: number, tp: number, tl: number): number {
  const ratio = tp / tl;
  return ps * ratio + ratio;
}

/** Run full deterministic validation */
export function runValidacion(input: ValidationInput): ValidationRule[] {
  const results: ValidationRule[] = [];

  // --- REG-FIS-32D: SAT / CFDI / e.firma ---
  {
    const checks: string[] = [];
    let status: ValidationStatus = 'PASS';

    if (!validateRFC(input.rfc)) {
      status = 'FAIL';
      checks.push(`RFC "${input.rfc}" no cumple formato oficial SAT`);
    } else {
      checks.push(`RFC "${input.rfc}" formato válido`);
    }

    if (!SAT_REGIMEN.OPINION_CUMPLIMIENTO_VALIDA.includes(input.opinionSAT.toUpperCase())) {
      status = 'FAIL';
      checks.push(`Opinión de cumplimiento "${input.opinionSAT}" no es válida (esperado: POSITIVO o EXTRAVIADA)`);
    } else {
      checks.push(`Opinión de cumplimiento: ${input.opinionSAT} — válida`);
    }

    if (!input.hasCFDI) {
      status = 'FAIL';
      checks.push('CFDI no activo — obligatorio desde 2014');
    } else {
      checks.push('CFDI activo y reportando');
    }

    if (!input.efirmaValid) {
      status = 'FAIL';
      checks.push('e.firma (FIEL) no válida o no configurada');
    } else {
      checks.push(`e.firma vigente (${input.efirmaExpiryDays} días restantes)`);
      if (input.efirmaExpiryDays < 90) {
        status = status === 'PASS' ? 'WARNING' : status;
        checks.push('ADVERTENCIA: e.firma expira en menos de 90 días');
      }
    }

    results.push({
      id: REGLAS_VALIDACION.REG_FIS_32D,
      name: 'SAT 32-D — Cumplimiento Fiscal CFDI / e.firma',
      category: 'Obligaciones Fiscales',
      status,
      detail: checks.join(' | '),
      evidence: `RFC=${input.rfc}, Opinión=${input.opinionSAT}, CFDI=${input.hasCFDI}, e.firma=${input.efirmaValid}`,
      fixAction: status === 'FAIL' ? 'Regularizar situación fiscal ante SAT' : undefined,
    });
  }

  // --- REG-FIS-SEG-SOCIAL: IMSS / INFONAVIT ---
  {
    const checks: string[] = [];
    let status: ValidationStatus = 'PASS';

    if (input.numWorkers >= SEGURIDAD_SOCIAL.IMSS_REGISTRO_OBRERO_MIN) {
      if (input.imssStatus.toUpperCase() !== 'ACTIVO') {
        status = 'FAIL';
        checks.push(`IMSS: estado "${input.imssStatus}" — debe ser ACTIVO con ${input.numWorkers} trabajadores`);
      } else {
        checks.push(`IMSS: ACTIVO — ${input.numWorkers} trabajadores registrados`);
      }

      if (input.infonavitStatus.toUpperCase() !== 'ACTIVO') {
        status = 'FAIL';
        checks.push(`INFONAVIT: estado "${input.infonavitStatus}" — debe ser ACTIVO`);
      } else {
        checks.push('INFONAVIT: ACTIVO — cumple LAASSP Art. 12');
      }

      const aportacionInfonavit = input.numWorkers * FSR_CONST.FORMULA.DIAS_LABORADOS * 0.05;
      checks.push(`Aportación INFONAVIT estimada: $${aportacionInfonavit.toFixed(2)} MXN/mes`);
    } else {
      checks.push(`Menos de ${SEGURIDAD_SOCIAL.IMSS_REGISTRO_OBRERO_MIN} trabajadores — no obligatorio`);
    }

    results.push({
      id: REGLAS_VALIDACION.REG_FIS_SEG_SOCIAL,
      name: 'Seguridad Social — IMSS / INFONAVIT / LAASSP Art. 12',
      category: 'Obligaciones Fiscales',
      status,
      detail: checks.join(' | '),
      evidence: `IMSS=${input.imssStatus}, INFONAVIT=${input.infonavitStatus}, Trabajadores=${input.numWorkers}`,
      fixAction: status === 'FAIL' ? 'Registrar empresa y trabajadores ante IMSS/INFONAVIT' : undefined,
    });
  }

  // --- REG-ADM-EFIRMA: e.firma certificate ---
  {
    let status: ValidationStatus = 'PASS';
    const checks: string[] = [];

    if (!input.efirmaValid) {
      status = 'FAIL';
      checks.push('Certificado de e.firma revocado o no vigente');
    } else {
      checks.push('Certificado de e.firma vigente');
    }

    if (input.efirmaExpiryDays <= 0) {
      status = 'FAIL';
      checks.push('Certificado EXPIRADO');
    } else if (input.efirmaExpiryDays < 60) {
      status = 'WARNING';
      checks.push(`Certificado expira en ${input.efirmaExpiryDays} días — renovar urgentemente`);
    } else if (input.efirmaExpiryDays < 180) {
      status = 'WARNING';
      checks.push(`Certificado expira en ${input.efirmaExpiryDays} días — programar renovación`);
    } else {
      checks.push(`Certificado vigente por ${input.efirmaExpiryDays} días`);
    }

    results.push({
      id: REGLAS_VALIDACION.REG_ADM_EFIRMA,
      name: 'e.firma — Vigencia de Certificado Digital',
      category: 'Administrativa',
      status,
      detail: checks.join(' | '),
      evidence: `e.firmaValid=${input.efirmaValid}, diasRestantes=${input.efirmaExpiryDays}`,
      fixAction: status === 'FAIL' ? 'Renovar certificado de e.firma ante SAT' : 'Programar renovación de e.firma',
    });
  }

  // --- REG-ECO-FSR: FSR Arithmetic ---
  {
    const fsr = computeFSR(input.fsrSeguridadSocial, input.fsrDiasPagados, input.fsrDiasLaborados);
    let status: ValidationStatus = 'PASS';
    const checks: string[] = [];

    checks.push(`FSR = ${fsr.toFixed(4)} (PS=${input.fsrSeguridadSocial}, TP=${input.fsrDiasPagados}, TL=${input.fsrDiasLaborados})`);
    checks.push(`Fórmula: ${input.fsrSeguridadSocial.toFixed(4)} × (${input.fsrDiasPagados}/${input.fsrDiasLaborados}) + (${input.fsrDiasPagados}/${input.fsrDiasLaborados}) = ${fsr.toFixed(4)}`);

    if (fsr < FSR_CONST.FSR_MINIMO) {
      status = 'FAIL';
      checks.push(`FSR ${fsr.toFixed(4)} por debajo del mínimo ${FSR_CONST.FSR_MINIMO}`);
    } else if (fsr > FSR_CONST.FSR_MAXIMO_TIPICO) {
      status = 'WARNING';
      checks.push(`FSR ${fsr.toFixed(4)} excede rango típico máximo ${FSR_CONST.FSR_MAXIMO_TIPICO}`);
    } else {
      checks.push(`FSR dentro del rango aceptable [${FSR_CONST.FSR_MINIMO} – ${FSR_CONST.FSR_MAXIMO_TIPICO}]`);
    }

    if (input.fsrDiasLaborados <= 0) {
      status = 'FAIL';
      checks.push('ERROR: Días laborados debe ser mayor a 0');
    }

    if (input.fsrDiasPagados < input.fsrDiasLaborados) {
      status = 'WARNING';
      checks.push('ADVERTENCIA: Días pagados menor que días laborados — revisar calendario laboral');
    }

    results.push({
      id: REGLAS_VALIDACION.REG_ECO_FSR,
      name: 'FSR — Factor de Salario Real (LAASSP Art. 12)',
      category: 'Indicadores Económicos',
      status,
      detail: checks.join(' | '),
      evidence: `FSR=${fsr.toFixed(4)}, PS=${input.fsrSeguridadSocial}, TP=${input.fsrDiasPagados}, TL=${input.fsrDiasLaborados}`,
      fixAction: status === 'FAIL' ? 'Revisar componentes de seguridad social y calendario laboral' : undefined,
    });
  }

  // --- REG-ECO-MAQUINARIA: Machinery hourly costs ---
  {
    let status: ValidationStatus = 'PASS';
    const checks: string[] = [];

    if (input.maquinariaItems.length === 0) {
      checks.push('Sin maquinaria registrada — validación no aplica');
    } else {
      let allValid = true;
      for (const item of input.maquinariaItems) {
        if (item.horasAnio < MAQUINARIA_NORMAS.HORAS_MIN_ANIO) {
          status = 'WARNING';
          allValid = false;
          checks.push(`${item.key}: Horas/año ${item.horasAnio} < mínimo ${MAQUINARIA_NORMAS.HORAS_MIN_ANIO}`);
        }
        if (item.factorMantenimiento < MAQUINARIA_NORMAS.FACTOR_MANTENIMIENTO_RANGO[0] ||
            item.factorMantenimiento > MAQUINARIA_NORMAS.FACTOR_MANTENIMIENTO_RANGO[1]) {
          status = 'WARNING';
          allValid = false;
          checks.push(`${item.key}: Factor mantenimiento ${item.factorMantenimiento} fuera de rango [${MAQUINARIA_NORMAS.FACTOR_MANTENIMIENTO_RANGO.join('-')}]`);
        }
        const depreciacionAnual = item.vidaEconomica > 0 ? 1 / item.vidaEconomica : 0;
        if (depreciacionAnual > MAQUINARIA_NORMAS.DEPRECIACION_MAX_ANUAL) {
          status = 'FAIL';
          allValid = false;
          checks.push(`${item.key}: Depreciación anual ${(depreciacionAnual * 100).toFixed(1)}% excede máximo ${(MAQUINARIA_NORMAS.DEPRECIACION_MAX_ANUAL * 100).toFixed(0)}%`);
        }
        // Compute ACM hourly cost
        if (item.vidaEconomica > 0 && item.horasAnio > 0) {
          const costoHoraDepreciacion = item.costoAdquisicion / (item.vidaEconomica * item.horasAnio);
          const costoHoraMantenimiento = costoHoraDepreciacion * item.factorMantenimiento;
          const costoHoraOperacion = item.combustibleHora + item.operadorHora;
          const costoHoraSeguro = (item.seguroAnual || item.costoAdquisicion * MAQUINARIA_NORMAS.SEGURO_PCT_ANUAL) / item.horasAnio;
          const costoHoraTotal = costoHoraDepreciacion + costoHoraMantenimiento + costoHoraOperacion + costoHoraSeguro;
          checks.push(`${item.key}: ACM = $${costoHoraTotal.toFixed(2)}/hr (depreciación $${costoHoraDepreciacion.toFixed(2)} + mantto $${costoHoraMantenimiento.toFixed(2)} + operación $${costoHoraOperacion.toFixed(2)} + seguro $${costoHoraSeguro.toFixed(2)})`);
        }
      }
      if (allValid) {
        checks.push(`Todos los ${input.maquinariaItems.length} equipos validados contra catálogo`);
      }
    }

    results.push({
      id: REGLAS_VALIDACION.REG_ECO_MAQUINARIA,
      name: 'ACM — Análisis de Costos de Maquinaria',
      category: 'Indicadores Económicos',
      status,
      detail: checks.join(' | '),
      evidence: `${input.maquinariaItems.length} equipos registrados`,
      fixAction: status === 'FAIL' ? 'Revisar vida económica y costos de adquisición' : undefined,
    });
  }

  // --- REG-ECO-SOBRECOSTOS: Overhead factors ---
  {
    let status: ValidationStatus = 'PASS';
    const checks: string[] = [];

    if (input.factorIndirectos > LOPSRM_INDIRECTOS.MAX_FACTOR_INDIRECTOS) {
      status = 'FAIL';
      checks.push(`Factor indirectos ${(input.factorIndirectos * 100).toFixed(2)}% excede límite LOPSRM ${(LOPSRM_INDIRECTOS.MAX_FACTOR_INDIRECTOS * 100).toFixed(0)}%`);
    } else {
      checks.push(`Factor indirectos: ${(input.factorIndirectos * 100).toFixed(2)}% ≤ ${(LOPSRM_INDIRECTOS.MAX_FACTOR_INDIRECTOS * 100).toFixed(0)}%`);
    }

    if (input.factorFinanciamiento > LOPSRM_INDIRECTOS.MAX_FACTOR_FINANCIAMIENTO) {
      status = 'FAIL';
      checks.push(`Factor financiamiento ${(input.factorFinanciamiento * 100).toFixed(2)}% excede límite ${(LOPSRM_INDIRECTOS.MAX_FACTOR_FINANCIAMIENTO * 100).toFixed(1)}%`);
    } else {
      checks.push(`Factor financiamiento: ${(input.factorFinanciamiento * 100).toFixed(2)}% ≤ ${(LOPSRM_INDIRECTOS.MAX_FACTOR_FINANCIAMIENTO * 100).toFixed(1)}%`);
    }

    if (input.utilidad > LOPSRM_INDIRECTOS.MAX_UTILIDAD) {
      status = 'FAIL';
      checks.push(`Utilidad ${(input.utilidad * 100).toFixed(2)}% excede límite LOPSRM Art. 45 ${(LOPSRM_INDIRECTOS.MAX_UTILIDAD * 100).toFixed(0)}%`);
    } else if (input.utilidad > LOPSRM_INDIRECTOS.MAX_UTILIDAD * 0.85) {
      status = 'WARNING';
      checks.push(`Utilidad ${(input.utilidad * 100).toFixed(2)}% cercana al límite ${(LOPSRM_INDIRECTOS.MAX_UTILIDAD * 100).toFixed(0)}%`);
    } else {
      checks.push(`Utilidad: ${(input.utilidad * 100).toFixed(2)}% ≤ ${(LOPSRM_INDIRECTOS.MAX_UTILIDAD * 100).toFixed(0)}%`);
    }

    if (input.costoDirectoPct < LOPSRM_INDIRECTOS.MIN_COSTO_DIRECTO_PCT) {
      status = 'FAIL';
      checks.push(`Costo directo ${(input.costoDirectoPct * 100).toFixed(1)}% por debajo del mínimo ${(LOPSRM_INDIRECTOS.MIN_COSTO_DIRECTO_PCT * 100).toFixed(0)}%`);
    } else {
      checks.push(`Costo directo: ${(input.costoDirectoPct * 100).toFixed(1)}% ≥ ${(LOPSRM_INDIRECTOS.MIN_COSTO_DIRECTO_PCT * 100).toFixed(0)}%`);
    }

    const totalCargos = input.factorIndirectos + input.factorFinanciamiento + input.utilidad;
    if (totalCargos > 0.25) {
      status = 'WARNING';
      checks.push(`Suma de cargos indirectos ${(totalCargos * 100).toFixed(2)}% > 25% — revisar composición`);
    } else {
      checks.push(`Suma de cargos: ${(totalCargos * 100).toFixed(2)}%`);
    }

    results.push({
      id: REGLAS_VALIDACION.REG_ECO_SOBRECOSTOS,
      name: 'Sobrecostos — Factores de Indirectos, Financiamiento y Utilidad',
      category: 'Indicadores Económicos',
      status,
      detail: checks.join(' | '),
      evidence: `CF=${input.factorFinanciamiento}, CI=${input.factorIndirectos}, U=${input.utilidad}, CD=${input.costoDirectoPct}`,
      fixAction: status === 'FAIL' ? 'Ajustar factores dentro de los límites LOPSRM' : undefined,
    });
  }

  return results;
}

/** Compute compliance score (0-100) */
export function computeComplianceScore(results: ValidationRule[]): number {
  if (results.length === 0) return 0;
  const weights: Record<ValidationStatus, number> = { PASS: 1, WARNING: 0.5, FAIL: 0 };
  const total = results.reduce((sum, r) => sum + weights[r.status], 0);
  return Math.round((total / results.length) * 100);
}

/** Get overall status */
export function getOverallStatus(results: ValidationRule[]): ValidationStatus {
  if (results.some((r) => r.status === 'FAIL')) return 'FAIL';
  if (results.some((r) => r.status === 'WARNING')) return 'WARNING';
  return 'PASS';
}
