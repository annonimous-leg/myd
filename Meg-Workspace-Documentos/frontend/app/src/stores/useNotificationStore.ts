/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { create } from 'zustand';
import type { Notification } from '@/types';

interface NotificationState {
  notifications: Notification[];
  addNotification: (notification: Omit<Notification, 'id' | 'timestamp'>) => string;
  removeNotification: (id: string) => void;
  clearAll: () => void;
}

export const useNotificationStore = create<NotificationState>((set, get) => ({
  notifications: [],

  addNotification: (notification) => {
    const id = `notif-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
    const notif: Notification = {
      ...notification,
      id,
      timestamp: Date.now(),
    };
    set({ notifications: [notif, ...get().notifications].slice(0, 5) });

    // Auto-dismiss after 5s
    setTimeout(() => {
      get().removeNotification(id);
    }, 5000);

    return id;
  },

  removeNotification: (id) => {
    set({ notifications: get().notifications.filter((n) => n.id !== id) });
  },

  clearAll: () => set({ notifications: [] }),
}));
