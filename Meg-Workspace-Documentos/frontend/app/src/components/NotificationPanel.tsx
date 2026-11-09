/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { motion, AnimatePresence } from 'framer-motion';
import { X, Bell, Info, AlertTriangle, AlertCircle, CheckCircle2 } from 'lucide-react';
import { useNotificationStore } from '@/stores/useNotificationStore';

interface NotificationPanelProps {
  onClose: () => void;
}

const typeConfig = {
  success: { icon: CheckCircle2, color: '#5A9E6F', bg: 'rgba(90,158,111,0.12)' },
  warning: { icon: AlertTriangle, color: '#D4953A', bg: 'rgba(212,149,58,0.12)' },
  error: { icon: AlertCircle, color: '#B84A4A', bg: 'rgba(184,74,74,0.12)' },
  info: { icon: Info, color: '#5A8AB8', bg: 'rgba(90,138,184,0.12)' },
};

export default function NotificationPanel({ onClose }: NotificationPanelProps) {
  const { notifications, removeNotification, clearAll } = useNotificationStore();

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-19999" onClick={onClose} />

      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -10 }}
        transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] as [number, number, number, number] }}
        className="fixed top-14 right-4 w-[360px] max-h-[560px] rounded-lg flex flex-col overflow-hidden"
        style={{
          background: 'var(--surface-elevated)',
          border: '1px solid var(--border-subtle)',
          boxShadow: 'var(--shadow-elevated)',
          zIndex: 30000,
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#2A2A3E]">
          <span className="text-sm font-semibold text-[#E8E4DC]">Notifications</span>
          {notifications.length > 0 && (
            <button
              onClick={clearAll}
              className="text-xs text-[#8A8578] hover:text-[#C9A84C] transition-colors"
            >
              Clear all
            </button>
          )}
        </div>

        {/* List */}
        <div className="flex-1 overflow-auto">
          {notifications.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <Bell className="w-12 h-12 text-[#2A2A3E] mb-3" />
              <p className="text-sm text-[#8A8578]">No new notifications</p>
            </div>
          ) : (
            <AnimatePresence>
              {notifications.map((notif) => {
                const config = typeConfig[notif.type];
                const IconComp = config.icon;
                return (
                  <motion.div
                    key={notif.id}
                    initial={{ opacity: 0, x: 50 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 50 }}
                    transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] as [number, number, number, number] }}
                    className="flex gap-3 p-3 border-b border-[#2A2A3E]/50 hover:bg-[#222235]/50 transition-colors"
                  >
                    <div
                      className="w-1 self-stretch rounded-full shrink-0"
                      style={{ backgroundColor: config.color }}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-1.5">
                          <IconComp className="w-3.5 h-3.5" style={{ color: config.color }} />
                          <span className="text-xs font-medium text-[#E8E4DC]">{notif.title}</span>
                        </div>
                        <button
                          onClick={() => removeNotification(notif.id)}
                          className="text-[#4D4A42] hover:text-[#8A8578] transition-colors shrink-0"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </div>
                      <p className="text-xs text-[#8A8578] mt-0.5">{notif.message}</p>
                    </div>
                  </motion.div>
                );
              })}
            </AnimatePresence>
          )}
        </div>
      </motion.div>
    </>
  );
}
