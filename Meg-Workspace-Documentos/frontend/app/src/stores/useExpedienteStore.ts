/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { megalodonClient } from '@/lib/api-client';
import type { Expediente } from '@/lib/megalodon-client';
import { MegalodonApiError } from '@/lib/megalodon-client';

export interface NuevoExpedienteInput {
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
}

interface ExpedienteState {
  expedientes: Expediente[];
  expedienteActivoId: string | null;
  isLoading: boolean;
  error: string | null;

  cargarExpedientes: () => Promise<void>;
  crearExpediente: (data: NuevoExpedienteInput) => Promise<Expediente>;
  setExpedienteActivo: (id: string | null) => void;
  expedienteActivo: () => Expediente | null;
  limpiar: () => void;
}
let ultimaCarga = 0;
let revisionSesion = 0;

// Fuente única de verdad de "en qué expediente estoy trabajando" para
// todo el sistema (costos, BIM, documentos, etc.). Antes no existía nada
// de esto -- cada app operaba sobre datos de demo hardcodeados, sin
// ningún expediente real detrás.
export const useExpedienteStore = create<ExpedienteState>()(
  persist(
    (set, get) => ({
      expedientes: [],
      expedienteActivoId: null,
      isLoading: false,
      error: null,

      cargarExpedientes: async () => {
        if (get().isLoading) return;
        const carga = ++ultimaCarga;
        const idsIniciales = new Set(get().expedientes.map(e => e.id));
        set({ isLoading: true, error: null });
        try {
          const expedientes = await megalodonClient.expedientes.list({ limit: 100 });
          const activoId = get().expedienteActivoId;
          let eliminado = false;
          if (activoId && !expedientes.some((e) => e.id === activoId)) {
            try {
              // Absence in the first page is not deletion of the selected project.
              expedientes.push(await megalodonClient.expedientes.get(activoId));
            } catch (e) {
              if (!(e instanceof MegalodonApiError) || ![403, 404].includes(e.status)) throw e;
              eliminado = true;
            }
          }
          if (carga !== ultimaCarga) return;
          set(state => {
            const conservados = state.expedientes.filter(e => !idsIniciales.has(e.id)
              || (e.id === state.expedienteActivoId && e.id !== activoId));
            const porId = new Map(expedientes.map(e => [e.id, e]));
            for (const expediente of conservados) porId.set(expediente.id, expediente);
            return { expedientes: [...porId.values()], isLoading: false,
              ...(eliminado && state.expedienteActivoId === activoId ? { expedienteActivoId: null } : {}) };
          });
        } catch (e) {
          if (carga !== ultimaCarga) return;
          set({
            isLoading: false,
            error: e instanceof Error ? e.message : 'No se pudieron cargar los expedientes',
          });
        }
      },

      crearExpediente: async (data) => {
        const sesion = revisionSesion;
        set({ isLoading: true, error: null });
        try {
          const nuevo = await megalodonClient.expedientes.create(data);
          if (sesion !== revisionSesion) return nuevo;
          set((state) => ({
            expedientes: [nuevo, ...state.expedientes],
            expedienteActivoId: nuevo.id, // el recién creado pasa a ser el activo
            isLoading: false,
          }));
          return nuevo;
        } catch (e) {
          const message = e instanceof Error ? e.message : 'No se pudo crear el expediente';
          if (sesion === revisionSesion) set({ isLoading: false, error: message });
          throw new Error(message);
        }
      },

      setExpedienteActivo: (id) => set({ expedienteActivoId: id }),
      limpiar: () => {
        ultimaCarga += 1;
        revisionSesion += 1;
        set({ expedientes: [], expedienteActivoId: null, isLoading: false, error: null });
      },

      expedienteActivo: () => {
        const { expedientes, expedienteActivoId } = get();
        return expedientes.find((e) => e.id === expedienteActivoId) ?? null;
      },
    }),
    {
      name: 'megalodon-expediente-activo',
      // Solo se persiste CUÁL es el activo; la lista se vuelve a pedir al
      // backend en cada sesión (podría estar desactualizada si se persiste).
      partialize: (state) => ({ expedienteActivoId: state.expedienteActivoId }),
    }
  )
);
