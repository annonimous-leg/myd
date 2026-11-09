/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { AppDefinition } from '@/types';

const ALL_APPS: AppDefinition[] = [
  // Science
  { id: 'bim-calculator', name: 'Calculadora BIM', icon: 'Building2', category: 'science', component: 'BimCalculator', defaultSize: { width: 550, height: 450 }, minSize: { width: 350, height: 300 }, pinned: true , estado: 'core', requiresPlan: 'FREE' },
  { id: 'monte-carlo', name: 'Monte Carlo', icon: 'Dices', category: 'science', component: 'MonteCarlo', defaultSize: { width: 700, height: 500 }, minSize: { width: 450, height: 350 }, pinned: true , estado: 'core', requiresPlan: 'FREE' },

  // INTEGRACIÓN ZIP 5: RASTREO ORBITAL (Kimi satellite tracker -- primer módulo real de Tezcatlipoca en el shell)
  { id: 'rastreo-orbital', name: 'Rastreo Orbital', icon: 'Globe2', category: 'flagship', component: 'RastreoOrbital', defaultSize: { width: 900, height: 650 }, minSize: { width: 500, height: 400 }, pinned: true, estado: 'showcase', requiresPlan: 'FREE' },
  { id: 'tezcatlipoca-hub', name: 'Tezcatlipoca', icon: 'Globe2', category: 'flagship', component: 'TezcatlipocaHub', defaultSize: { width: 1150, height: 760 }, minSize: { width: 700, height: 500 }, pinned: true, estado: 'core', requiresPlan: 'PRO' },
  // Flagship
  { id: 'proyectos', name: 'Proyectos', icon: 'FolderKanban', category: 'flagship', component: 'Proyectos', defaultSize: { width: 800, height: 600 }, minSize: { width: 500, height: 400 }, pinned: true , estado: 'core', requiresPlan: 'FREE' },
  { id: 'topografia', name: 'Topografía', icon: 'Mountain', category: 'flagship', component: 'Topografia', defaultSize: { width: 1360, height: 820 }, minSize: { width: 760, height: 520 }, pinned: true , estado: 'core', requiresPlan: 'FREE' },
  { id: 'megalodon-costos', name: 'Megalodon CostOS', icon: 'Hammer', category: 'flagship', component: 'MegalodonCostos', defaultSize: { width: 1100, height: 700 }, minSize: { width: 600, height: 450 }, pinned: true , estado: 'core', requiresPlan: 'FREE' },
  // Vista faltante para ProgramaObra/ActividadPrograma: el backend ya
  // generaba el cronograma 4D con CPM completo, pero no había ninguna
  // app en el frontend para verlo ni editarlo.
  { id: 'programacion-obra', name: 'Programación de Obra', icon: 'CalendarDays', category: 'flagship', component: 'ProgramacionObra', defaultSize: { width: 1200, height: 750 }, minSize: { width: 700, height: 450 }, pinned: true , estado: 'core', requiresPlan: 'FREE' },
  { id: 'transparencia', name: 'Portal de Transparencia', icon: 'Eye', category: 'flagship', component: 'Transparencia', defaultSize: { width: 1100, height: 700 }, minSize: { width: 600, height: 450 }, pinned: true , estado: 'core', requiresPlan: 'FREE' },
  { id: 'compliance-dashboard', name: 'Compliance Dashboard', icon: 'Shield', category: 'flagship', component: 'ComplianceDashboard', defaultSize: { width: 1100, height: 700 }, minSize: { width: 600, height: 450 }, pinned: true , estado: 'core', requiresPlan: 'FREE' },
  { id: 'search-global', name: 'Búsqueda Global', icon: 'Search', category: 'flagship', component: 'SearchGlobal', defaultSize: { width: 1000, height: 650 }, minSize: { width: 500, height: 400 }, pinned: true , estado: 'core', requiresPlan: 'FREE' },
  { id: 'consistency-engine', name: 'Motor de Consistencia', icon: 'Link2', category: 'flagship', component: 'ConsistencyEngine', defaultSize: { width: 1100, height: 700 }, minSize: { width: 600, height: 450 }, pinned: true , estado: 'core', requiresPlan: 'FREE' },
  // ═══════════════════════════════════════════════════════════════════════
  // INTEGRACIÓN ZIP 2: LICITACIONES DE OBRA
  // ═══════════════════════════════════════════════════════════════════════
  { id: 'licitaciones-obra', name: 'Licitaciones de Obra', icon: 'Gavel', category: 'flagship', component: 'LicitacionesObra', defaultSize: { width: 1200, height: 800 }, minSize: { width: 800, height: 600 }, pinned: true , estado: 'core', requiresPlan: 'FREE' },
  // ═══════════════════════════════════════════════════════════════════════
  // INTEGRACIÓN ZIP 3: CONSULTOR LEGAL LEGL
  // ═══════════════════════════════════════════════════════════════════════
  { id: 'legl-consultor', name: 'Consultor Legal LEGL', icon: 'Scale', category: 'flagship', component: 'LeglConsultor', defaultSize: { width: 950, height: 750 }, minSize: { width: 600, height: 500 }, pinned: true , estado: 'core', requiresPlan: 'FREE' },
  // ═══════════════════════════════════════════════════════════════════════
  // CIERRE DE BRECHA FRONTEND/BACKEND — Fase de auditoría 2026-08-11
  // ═══════════════════════════════════════════════════════════════════════
  { id: 'documentos-firma', name: 'Documentos & Firma', icon: 'FileStack', category: 'flagship', component: 'DocumentosFirma', defaultSize: { width: 1050, height: 700 }, minSize: { width: 650, height: 450 }, pinned: true , estado: 'core', requiresPlan: 'FREE' },
];

interface AppRegistryState {
  apps: AppDefinition[];
  getApp: (id: string) => AppDefinition | undefined;
  pinApp: (id: string) => void;
  unpinApp: (id: string) => void;
  getPinnedApps: () => AppDefinition[];
  getAppsByCategory: (category: string) => AppDefinition[];
}

export const useAppRegistry = create<AppRegistryState>()(
  persist(
    (set, get) => ({
      apps: ALL_APPS,
      getApp: (id) => get().apps.find((a) => a.id === id),
      pinApp: (id) => {
        set({
          apps: get().apps.map((a) => (a.id === id ? { ...a, pinned: true } : a)),
        });
      },
      unpinApp: (id) => {
        set({
          apps: get().apps.map((a) => (a.id === id ? { ...a, pinned: false } : a)),
        });
      },
      getPinnedApps: () => get().apps.filter((a) => a.pinned),
      getAppsByCategory: (category) => get().apps.filter((a) => a.category === category),
    }),
    {
      name: 'megalodon-apps',
      partialize: (state) => ({ apps: state.apps.map(a => ({ id: a.id, pinned: a.pinned })) }),
      merge: (persisted, current) => {
        const p = persisted as { apps?: { id: string; pinned: boolean }[] } | undefined;
        const pinnedMap = new Map(p?.apps?.map(a => [a.id, Boolean(a.pinned)]) ?? []);
        return {
          ...current,
          apps: current.apps.map(a => ({
            ...a,
            pinned: pinnedMap.has(a.id) ? pinnedMap.get(a.id)! : a.pinned,
          })),
        };
      },
    }
  )
);

export { ALL_APPS };
