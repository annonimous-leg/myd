/**
 * Utilidades compartidas del módulo LEGL para trabajar con el resultado de
 * /juridico/procedimiento (motor jurídico real -- ver
 * backend/app/engines/juridico/motor_juridico.py).
 *
 * Antes de esta corrección (F-01 de la auditoría 2026-09-01), los
 * componentes de este módulo llamaban a `megalodonClient.legal.
 * determinarProcedimiento(...)`, que pegaba a un endpoint con un umbral de
 * un solo nivel hardcodeado (1,000,000 / 50,000,000) en vez de la tabla
 * escalonada real por presupuesto de dependencia. Ahora todos llaman a
 * `megalodonClient.juridico.determinarProcedimiento(...)`, el motor real
 * con comportamiento fail-closed (SIN_DETERMINAR cuando falta el
 * presupuesto de la dependencia) y trazabilidad de qué tan confiable es
 * cada cifra (`datos_verificados` / `es_candidato`).
 */
import type { ResultadoJuridico } from '@/lib/megalodon-client';

export type ProcedimientoClave = 'adjudicacion_directa' | 'invitacion_restringida' | 'licitacion_publica';

export const NOMBRE_PROCEDIMIENTO: Record<ProcedimientoClave, string> = {
  adjudicacion_directa: 'Adjudicación Directa',
  invitacion_restringida: 'Invitación Restringida (a cuando menos tres personas)',
  licitacion_publica: 'Licitación Pública',
};

const CLAVE_POR_ENUM: Record<string, ProcedimientoClave> = {
  ADJUDICACION_DIRECTA: 'adjudicacion_directa',
  INVITACION_TRES: 'invitacion_restringida',
  LICITACION_PUBLICA: 'licitacion_publica',
};

/**
 * Plazos mínimos por procedimiento (días hábiles de publicación + recepción
 * de proposiciones). Dato legal separado del umbral de monto -- no depende
 * del presupuesto de la dependencia. NO reverificado letra por letra contra
 * LOPSRM Art. 33 / LAASSP Art. 32 en esta ronda (el foco fue el umbral de
 * monto, que es F-01); son los mismos valores que ya traía el backend,
 * consolidados aquí en un solo lugar del frontend.
 */
const PLAZOS_POR_PROCEDIMIENTO: Record<ProcedimientoClave, { publicacionDiasHabiles: number; recepcionDiasHabiles: number }> = {
  adjudicacion_directa: { publicacionDiasHabiles: 0, recepcionDiasHabiles: 3 },
  invitacion_restringida: { publicacionDiasHabiles: 5, recepcionDiasHabiles: 10 },
  licitacion_publica: { publicacionDiasHabiles: 10, recepcionDiasHabiles: 20 },
};

export function claveProcedimiento(resultado: ResultadoJuridico): ProcedimientoClave | null {
  return CLAVE_POR_ENUM[resultado.procedimiento] ?? null;
}

export function nombreProcedimiento(resultado: ResultadoJuridico): string {
  const clave = claveProcedimiento(resultado);
  return clave ? NOMBRE_PROCEDIMIENTO[clave] : 'No determinado';
}

export function plazosPara(clave: ProcedimientoClave) {
  const p = PLAZOS_POR_PROCEDIMIENTO[clave];
  return { ...p, totalMinimo: p.publicacionDiasHabiles + p.recepcionDiasHabiles };
}

/** Texto de advertencia a mostrar cuando el resultado no es verificado. */
export function advertenciaConfiabilidad(resultado: ResultadoJuridico): string | null {
  if (!resultado.valido) {
    return 'El Anexo 9 del PEF es una tabla escalonada por el presupuesto autorizado de la dependencia contratante -- captúralo abajo para obtener un procedimiento confiable. ' +
      (resultado.observaciones?.[0] ?? '');
  }
  if (resultado.es_candidato) {
    return 'Cifras sin confirmar contra el Anexo 9 oficial (citadas por investigación). No las uses como único fundamento de una decisión de cumplimiento.';
  }
  return null;
}
