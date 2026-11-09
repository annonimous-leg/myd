/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { useState, useEffect } from 'react';
import { Bell, Wifi, LogOut, ChevronDown, Search } from 'lucide-react';
import { useAuthStore } from '@/stores/useAuthStore';
import { useNotificationStore } from '@/stores/useNotificationStore';
import { useCommandPaletteStore } from '@/stores/useCommandPaletteStore';
import NotificationPanel from './NotificationPanel';

interface TopBarProps {
  title: string;
}

export default function TopBar({ title }: TopBarProps) {
  const { user, logout } = useAuthStore();
  const notifications = useNotificationStore((s) => s.notifications);
  const unread = notifications?.length ?? 0;
  const openPalette = useCommandPaletteStore((s) => s.open);
  const [now, setNow] = useState(new Date());
  const [menuOpen, setMenuOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(t);
  }, []);

  return (
    <header
      className="flex items-center justify-between h-16 px-3 sm:px-6 shrink-0 border-b"
      style={{ background: 'var(--surface)', borderColor: 'var(--border-subtle)' }}
    >
      <div className="flex items-center gap-3">
        <h1 className="text-[15px] font-semibold" style={{ color: 'var(--text-primary)' }}>
          {title}
        </h1>
        <span
          className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider px-2 py-1 rounded"
          style={{ background: 'rgba(90,158,111,0.12)', color: 'var(--success)' }}
        >
          <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--success)' }} />
          Sesión activa
        </span>
      </div>

      <div className="flex items-center gap-4">
        <button
          onClick={openPalette}
          className="hidden sm:flex items-center gap-2.5 pl-3 pr-2.5 py-1.5 rounded-lg text-[12px] transition-colors hover:border-(--border-active)"
          style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)' }}
        >
          <Search className="w-3.5 h-3.5" />
          <span>Buscar o saltar a…</span>
          <kbd
            className="text-[10px] px-1.5 py-0.5 rounded"
            style={{ background: 'var(--surface)', color: 'var(--text-muted)', border: '1px solid var(--border-subtle)' }}
          >
            ⌘K
          </kbd>
        </button>

        <div className="hidden lg:flex items-center gap-1.5 text-[11.5px]" style={{ color: 'var(--text-muted)' }}>
          <Wifi className="w-3.5 h-3.5" />
          <span>
            {now.toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>

        <div className="relative">
          <button
            onClick={() => setNotifOpen((v) => !v)}
            className="relative p-1.5 rounded-md hover:bg-(--surface-hover) transition-colors"
            aria-label="Notificaciones"
          >
            <Bell className="w-[18px] h-[18px]" style={{ color: 'var(--text-secondary)' }} />
            {unread > 0 && (
              <span
                className="absolute -top-0.5 -right-0.5 min-w-[15px] h-[15px] px-[3px] rounded-full text-[9px] font-bold flex items-center justify-center"
                style={{ background: 'var(--danger)', color: '#fff' }}
              >
                {unread > 9 ? '9+' : unread}
              </span>
            )}
          </button>
          {notifOpen && (
            <div className="absolute right-0 top-[calc(100%+6px)]" style={{ zIndex: 'var(--z-menus)' }}>
              <NotificationPanel onClose={() => setNotifOpen(false)} />
            </div>
          )}
        </div>

        <div className="relative">
          <button
            onClick={() => setMenuOpen((v) => !v)}
            className="flex items-center gap-2 pl-1 pr-2 py-1 rounded-md hover:bg-(--surface-hover) transition-colors"
          >
            <div
              className="w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-semibold"
              style={{ background: 'var(--accent-gold-dim)', color: 'var(--void)' }}
            >
              {(user?.name || 'U').slice(0, 1).toUpperCase()}
            </div>
            <span className="text-[12.5px] font-medium hidden md:inline" style={{ color: 'var(--text-primary)' }}>
              {user?.name || 'Usuario'}
            </span>
            <ChevronDown className="w-3.5 h-3.5" style={{ color: 'var(--text-muted)' }} />
          </button>

          {menuOpen && (
            <div
              className="absolute right-0 top-[calc(100%+6px)] w-44 rounded-lg overflow-hidden border py-1"
              style={{ background: 'var(--surface-elevated)', borderColor: 'var(--border-subtle)', boxShadow: 'var(--shadow-elevated)', zIndex: 'var(--z-menus)' }}
              onMouseLeave={() => setMenuOpen(false)}
            >
              <button
                onClick={() => { setMenuOpen(false); logout(); }}
                className="flex items-center gap-2.5 w-full px-3.5 py-2 text-[12.5px] hover:bg-(--surface-hover) transition-colors"
                style={{ color: 'var(--text-primary)' }}
              >
                <LogOut className="w-3.5 h-3.5" />
                Cerrar sesión
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
