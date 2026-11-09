export interface Criterion {
  descripcion?: string;
  campo?: string;
  requerido?: boolean;
  peso?: number;
  ponderacion?: number;
  [key: string]: unknown;
}
export interface EvaluationMatrix {
  legal?: Record<string, Criterion>;
  tecnico?: Record<string, Criterion>;
  economico?: Record<string, Criterion>;
  minimo_tecnico?: number;
  minimo_economico?: number;
  variacion_mercado_max?: number;
  variacion_mercado_penalty?: number;
  [key: string]: unknown;
}
export interface LicitacionRecord {
  id: string; folio: string; estado: string; jurisdiction_code: string;
  bases: string | null; bases_version: number; bases_congeladas: boolean;
  row_version: number; matriz_evaluacion: EvaluationMatrix | null;
  transiciones_disponibles: string[];
}
export interface ProviderRecord {
  id: string; rfc: string; razon_social: string;
  tipo_persona: 'FISICA' | 'MORAL' | 'CONSORCIO'; estado: string;
}
export interface ProposalRecord {
  id: string; proveedor_id: string; monto: number; plazo_dias: number; estado: string;
  proveedor: { razon_social: string | null; rfc: string | null };
  firma_valida: boolean | null; integridad_valida: boolean | null; cumplimiento_documental: boolean | null;
  verificacion_documental: { fecha: string; autor_id: string; dictamen: string } | null;
}
export interface EvaluationInputs {
  legal: Record<string, boolean>; tecnico: Record<string, number>; economico: Record<string, number>;
}
export interface EvaluationRecord {
  id: string; proposicion_id: string; tipo: 'LEGAL' | 'TECNICA' | 'ECONOMICA'; revision: number;
  resultado: string; puntaje: number | null; dictamen: string | null;
  criterios: { datos?: Record<string, boolean | number>; [key: string]: unknown } | null;
}
export interface LicitacionWorkspace {
  licitacion: LicitacionRecord; proposiciones: ProposalRecord[]; evaluaciones: EvaluationRecord[];
}
