/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { create } from 'zustand';

interface MegalodonProject {
  id: string;
  name: string;
  type: string;
  createdAt: number;
  lastModified: number;
}

interface ValidationRecord {
  id: string;
  projectId: string;
  timestamp: number;
  score: number;
  overall: 'PASS' | 'FAIL' | 'WARNING';
  rulesChecked: number;
  rulesPassed: number;
  rulesFailed: number;
  rulesWarning: number;
}

interface CalculationResult {
  id: string;
  projectId: string;
  type: 'fsr' | 'montecarlo' | 'bim' | 'budget';
  timestamp: number;
  summary: string;
  data: Record<string, unknown>;
}

interface MegalodonState {
  projects: MegalodonProject[];
  activeProjectId: string | null;
  activeTab: string;
  validationResults: ValidationRecord[];
  calculationResults: CalculationResult[];
  setActiveTab: (tab: string) => void;
  setActiveProject: (id: string | null) => void;
  addProject: (project: Omit<MegalodonProject, 'id' | 'createdAt' | 'lastModified'>) => string;
  removeProject: (id: string) => void;
  addValidationResult: (result: Omit<ValidationRecord, 'id' | 'timestamp'>) => void;
  addCalculationResult: (result: Omit<CalculationResult, 'id' | 'timestamp'>) => void;
  clearValidationHistory: () => void;
  clearAllProjects: () => void;
}

export const useMegalodonStore = create<MegalodonState>((set, get) => ({
  projects: [],
  activeProjectId: null,
  activeTab: 'resumen',
  validationResults: [],
  calculationResults: [],
  setActiveTab: (tab) => set({ activeTab: tab }),
  setActiveProject: (id) => set({ activeProjectId: id }),
  addProject: (project) => {
    const id = `meg-${Date.now()}`;
    set({ projects: [...get().projects, { ...project, id, createdAt: Date.now(), lastModified: Date.now() }] });
    return id;
  },
  removeProject: (id) => {
    set({ projects: get().projects.filter((p) => p.id !== id) });
  },
  addValidationResult: (result) => {
    const id = `val-${Date.now()}`;
    set({ validationResults: [...get().validationResults, { ...result, id, timestamp: Date.now() }] });
  },
  addCalculationResult: (result) => {
    const id = `calc-${Date.now()}`;
    set({ calculationResults: [...get().calculationResults, { ...result, id, timestamp: Date.now() }] });
  },
  clearValidationHistory: () => set({ validationResults: [] }),
  clearAllProjects: () => set({ projects: [], activeProjectId: null, validationResults: [], calculationResults: [] }),
}));
