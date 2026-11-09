/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { create } from 'zustand';
import type { User } from '@/types';
import { megalodonClient } from '@/lib/api-client';
import { useExpedienteStore } from './useExpedienteStore';

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isBootComplete: boolean;
  isLoading: boolean;
  isCheckingSession: boolean;
  restoreSession: () => Promise<void>;
  error: string | null;
  /** Login real contra el backend (email + password). */
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  setBootComplete: (complete: boolean) => void;
}

let restoring: Promise<void> | null = null;

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  isBootComplete: false,
  isLoading: false,
  isCheckingSession: true,
  error: null,

  restoreSession: async () => {
    if (!restoring) {
      restoring = (async () => {
        try {
          const backendUser = await megalodonClient.auth.me();
          set({ user: { id: backendUser.id, name: backendUser.full_name,
            username: backendUser.email, isGuest: false, role: backendUser.role }, isAuthenticated: true });
          const { useEntitlementsStore } = await import('./useEntitlementsStore');
          void useEntitlementsStore.getState().cargar();
        } catch { set({ user: null, isAuthenticated: false }); }
        finally { set({ isCheckingSession: false }); }
      })().finally(() => { restoring = null; });
    }
    await restoring;
  },

  login: async (email, password) => {
    set({ isLoading: true, error: null });
    try {
      await megalodonClient.auth.login(email, password);
      const backendUser = await megalodonClient.auth.me();
      const user: User = {
        id: backendUser.id,
        name: backendUser.full_name,
        username: backendUser.email,
        isGuest: false,
        role: backendUser.role,
      };
      set({
        user,
        isAuthenticated: true,
        isBootComplete: false,
        isLoading: false,
      });
      import('./useEntitlementsStore').then(({ useEntitlementsStore }) => {
        void useEntitlementsStore.getState().cargar();
      });
    } catch (e) {
      const message = e instanceof Error ? e.message : 'No se pudo iniciar sesión';
      set({ isLoading: false, error: message, isAuthenticated: false });
      throw new Error(message);
    }
  },

  logout: async () => {
    try { await megalodonClient.auth.logout(); } catch (e) {
      set({ error: e instanceof Error ? e.message : "No se pudo cerrar la sesión" });
      return;
    }
    megalodonClient.setToken('');
    useExpedienteStore.getState().limpiar();
    set({
      user: null,
      isAuthenticated: false,
      isBootComplete: false,
    });
  },

  setBootComplete: (complete) => set({ isBootComplete: complete }),
}));
