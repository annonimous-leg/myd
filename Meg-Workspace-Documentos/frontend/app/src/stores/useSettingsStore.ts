/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface SettingsState {
  theme: 'dark' | 'light' | 'auto';
  accentColor: string;
  wallpaperBrightness: number;
  wallpaperAnimated: boolean;
  soundEnabled: boolean;
  notificationEnabled: boolean;
  clockFormat: '12h' | '24h';
  autoSave: boolean;
  updateSetting: <K extends keyof SettingsState>(key: K, value: SettingsState[K]) => void;
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      theme: 'dark',
      accentColor: '#C9A84C',
      wallpaperBrightness: 100,
      wallpaperAnimated: false,
      soundEnabled: false,
      notificationEnabled: true,
      clockFormat: '24h',
      autoSave: true,
      updateSetting: (key, value) => set({ [key]: value } as Partial<SettingsState>),
    }),
    { name: 'megalodon-settings' }
  )
);
