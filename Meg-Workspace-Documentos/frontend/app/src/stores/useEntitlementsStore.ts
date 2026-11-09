/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

/**
 * Fuente de verdad de qué apps puede abrir el usuario actual.
 *
 * IMPORTANTE: esto es solo para RENDER (ocultar/mostrar candados en el
 * launcher). El backend es quien realmente manda -- cada endpoint
 * sensible valida plan/rol de nuevo con requiere_plan_minimo/
 * requiere_rol (ver app/core/entitlements.py). Si este store dice
 * "desbloqueado" pero el backend no está de acuerdo (caché viejo, plan
 * vencido justo ahora), el endpoint responde 402/403 de todas formas.
 */
import { create } from 'zustand';
import { megalodonClient } from '../lib/api-client';

export interface ModuloEntitlement {
  app_id: string;
  nombre: string;
  estado: string;
  requiere_plan: string | null;
  requiere_rol: string[] | null;
  desbloqueado: boolean;
  motivo_bloqueo: string | null;
}

export interface MiPlan {
  plan: string;
  plan_efectivo: string;
  plan_vencimiento: string | null;
  limites: Record<string, unknown>;
  uso_actual: Record<string, number>;
}

interface EntitlementsState {
  modulos: ModuloEntitlement[];
  miPlan: MiPlan | null;
  cargado: boolean;
  cargando: boolean;
  error: string | null;
  cargar: () => Promise<void>;
  puedeAbrir: (appId: string) => boolean;
  motivoBloqueo: (appId: string) => string | null;
}

export const useEntitlementsStore = create<EntitlementsState>((set, get) => ({
  modulos: [],
  miPlan: null,
  cargado: false,
  cargando: false,
  error: null,

  cargar: async () => {
    if (get().cargando) return;
    set({ cargando: true, error: null });
    try {
      const [modulos, miPlan] = await Promise.all([
        megalodonClient.entitlements.modulos() as Promise<ModuloEntitlement[]>,
        megalodonClient.entitlements.miPlan() as Promise<MiPlan>,
      ]);
      set({ modulos, miPlan, cargado: true, cargando: false });
    } catch (e: any) {
      // Fail-closed para operaciones SaaS: la ausencia de autorización no
      // debe interpretarse como permiso. El backend sigue siendo la autoridad
      // final; este estado evita que la UX abra capacidades premium cuando el
      // servicio de entitlements no está disponible.
      set({ error: e.message || 'No se pudo cargar el estado de tu plan', cargando: false, cargado: false });
    }
  },

  puedeAbrir: (appId: string) => {
    const modulo = get().modulos.find((m) => m.app_id === appId);
    if (!get().cargado) return false;
    if (!modulo) return false;
    return modulo.desbloqueado;
  },

  motivoBloqueo: (appId: string) => {
    const modulo = get().modulos.find((m) => m.app_id === appId);
    return modulo?.motivo_bloqueo ?? null;
  },
}));
