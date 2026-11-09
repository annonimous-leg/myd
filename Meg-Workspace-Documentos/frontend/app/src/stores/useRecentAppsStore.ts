/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

const MAX_RECENTS = 5;

interface RecentAppsState {
  recentIds: string[];
  register: (id: string) => void;
}

export const useRecentAppsStore = create<RecentAppsState>()(
  persist(
    (set, get) => ({
      recentIds: [],
      register: (id) => {
        if (id === 'inicio') return;
        const withoutId = get().recentIds.filter((existing) => existing !== id);
        set({ recentIds: [id, ...withoutId].slice(0, MAX_RECENTS) });
      },
    }),
    { name: 'megalodon-recent-apps' }
  )
);
