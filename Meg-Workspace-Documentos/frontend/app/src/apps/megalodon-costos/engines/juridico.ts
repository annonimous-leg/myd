/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

// =============================================================================
// Megalodon CostOS — Legal Framework Engine (LOPSRM / LAASSP / LFT)
// =============================================================================

import { determinarProcedimiento, nombreProcedimiento, LOPSRM_UMBRALES, LOPSRM_INDIRECTOS, FSR_CONST, LFT_SALARIOS } from '../data/legales';
import type { TipoProcedimiento } from '../data/legales';

export interface LegalRequirement {
  article: string;
  law: string;
  description: string;
  status: 'PASS' | 'FAIL' | 'WARNING';
  detail: string;
}

export interface LegalFramework {
  procedureType: TipoProcedimiento;
  procedureName: string;
  requirements: LegalRequirement[];
  recommendations: string[];
}

/** Evaluate legal framework compliance for a given budget amount */
export function evaluateLegalFramework(
  montoTotal: number,
  hasIMSS: boolean,
  hasINFONAVIT: boolean,
  hasLFTCompliance: boolean,
  costoDirectoPct: number,
  utilidadPct: number,
  factorIndirectos: number,
): LegalFramework {
  const procedureType = determinarProcedimiento(montoTotal);
  const procedureName = nombreProcedimiento(procedureType);
  const requirements: LegalRequirement[] = [];
  const recommendations: string[] = [];

  // LOPSRM Art. 34 — Unit price completeness
  {
    const status = costoDirectoPct >= LOPSRM_INDIRECTOS.MIN_COSTO_DIRECTO_PCT ? 'PASS' : 'FAIL';
    requirements.push({
      article: 'Art. 34',
      law: 'LOPSRM',
      description: 'Completitud de análisis de precios unitarios',
      status,
      detail: `Costo directo ${(costoDirectoPct * 100).toFixed(1)}% del total. Mínimo requerido: ${(LOPSRM_INDIRECTOS.MIN_COSTO_DIRECTO_PCT * 100).toFixed(0)}%.`,
    });
  }

  // LOPSRM Art. 37 — Direct cost limits
  {
    const status = costoDirectoPct >= 0.65 ? 'PASS' : 'WARNING';
    requirements.push({
      article: 'Art. 37',
      law: 'LOPSRM',
      description: 'Límites de costo directo',
      status,
      detail: `Costos directos representan ${(costoDirectoPct * 100).toFixed(1)}% del presupuesto (límite: 70%).`,
    });
  }

  // LOPSRM Art. 40 — Indirect cost factors
  {
    const status = factorIndirectos <= LOPSRM_INDIRECTOS.MAX_FACTOR_INDIRECTOS ? 'PASS' : 'FAIL';
    requirements.push({
      article: 'Art. 40',
      law: 'LOPSRM',
      description: 'Factores de costos indirectos',
      status,
      detail: `Factor de indirectos: ${(factorIndirectos * 100).toFixed(2)}% (máximo permitido: ${(LOPSRM_INDIRECTOS.MAX_FACTOR_INDIRECTOS * 100).toFixed(0)}%).`,
    });
  }

  // LOPSRM Art. 45 — Profit margin
  {
    let status: 'PASS' | 'FAIL' | 'WARNING' = 'PASS';
    let detail = `Utilidad: ${(utilidadPct * 100).toFixed(2)}% (límite: ${(LOPSRM_INDIRECTOS.MAX_UTILIDAD * 100).toFixed(0)}%).`;
    if (utilidadPct > LOPSRM_INDIRECTOS.MAX_UTILIDAD) {
      status = 'FAIL';
      detail += ' EXCEDE LÍMITE LEGAL.';
    } else if (utilidadPct > LOPSRM_INDIRECTOS.MAX_UTILIDAD * 0.85) {
      status = 'WARNING';
      detail += ' Cercano al límite.';
      recommendations.push('Considerar reducir margen de utilidad para evitar observaciones en auditoría.');
    }
    requirements.push({
      article: 'Art. 45',
      law: 'LOPSRM',
      description: 'Margen de utilidad',
      status,
      detail,
    });
  }

  // LAASSP Art. 12 — Social security
  {
    const status = hasIMSS && hasINFONAVIT ? 'PASS' : 'FAIL';
    requirements.push({
      article: 'Art. 12',
      law: 'LAASSP',
      description: 'Contribuciones de seguridad social (IMSS/INFONAVIT)',
      status,
      detail: `IMSS: ${hasIMSS ? 'Registrado' : 'NO registrado'} | INFONAVIT: ${hasINFONAVIT ? 'Registrado' : 'NO registrado'}. Todos los costos de mano de obra deben incluir IMSS e INFONAVIT.`,
    });
    if (!hasIMSS) recommendations.push('Registrar empresa y trabajadores ante IMSS.');
    if (!hasINFONAVIT) recommendations.push('Registrar empresa ante INFONAVIT.');
  }

  // LFT Art. 123 — Salary compliance
  {
    const status = hasLFTCompliance ? 'PASS' : 'WARNING';
    requirements.push({
      article: 'Art. 123',
      law: 'LFT',
      description: 'Cumplimiento salarial (salario mínimo × FSR)',
      status,
      detail: hasLFTCompliance
        ? `Todos los salarios ≥ $${LFT_SALARIOS.SALARIO_MINIMO_DIARIO_2024.toFixed(2)} MXN/día (mínimo vigente 2024) × FSR.`
        : `Algunos salarios pueden estar por debajo del mínimo legal con FSR aplicado. Mínimo: $${LFT_SALARIOS.SALARIO_MINIMO_DIARIO_2024.toFixed(2)} MXN/día × ${FSR_CONST.FORMULA.FRACCION_SEGURIDAD_SOCIAL_DEFAULT.toFixed(4)} = $${(LFT_SALARIOS.SALARIO_MINIMO_DIARIO_2024 * (1 + FSR_CONST.FORMULA.FRACCION_SEGURIDAD_SOCIAL_DEFAULT)).toFixed(2)} MXN/día real.`,
    });
  }

  // Procedure-specific requirements
  if (procedureType === 'LICITACION_PUBLICA') {
    requirements.push({
      article: 'Art. 26',
      law: 'LOPSRM',
      description: 'Licitación pública obligatoria',
      status: 'PASS',
      detail: `Monto $${montoTotal.toLocaleString('es-MX')} ≥ umbral $${LOPSRM_UMBRALES.LICITACION_PUBLICA_MIN.toLocaleString('es-MX')}. Aplica licitación pública nacional.`,
    });
    recommendations.push('Publicar convocatoria en CompraNet y portal de contrataciones.');
    recommendations.push('Incluir garantía de seriedad del 2% del monto estimado.');
  } else if (procedureType === 'INVITACION_A_TRES') {
    requirements.push({
      article: 'Art. 27',
      law: 'LOPSRM',
      description: 'Invitación a cuando menos tres',
      status: 'PASS',
      detail: `Monto $${montoTotal.toLocaleString('es-MX')} en rango de invitación restringida.`,
    });
  }

  return { procedureType, procedureName, requirements, recommendations };
}

/** Get procedure color */
export function getProcedureColor(tipo: TipoProcedimiento): string {
  switch (tipo) {
    case 'LICITACION_PUBLICA': return '#5A9E6F';
    case 'INVITACION_A_TRES': return '#5A8AB8';
    case 'ADJUDICACION_DIRECTA': return '#D4953A';
    case 'EMERGENCIA': return '#B84A4A';
    default: return '#8A8578';
  }
}
