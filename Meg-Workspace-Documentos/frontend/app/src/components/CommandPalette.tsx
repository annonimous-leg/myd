/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { useEffect, useMemo, useRef } from 'react';
import { Command as CommandPrimitive } from 'cmdk';
import { AnimatePresence, motion } from 'framer-motion';
import * as Icons from 'lucide-react';
import { useAppRegistry } from '@/stores/useAppRegistry';
import { useRecentAppsStore } from '@/stores/useRecentAppsStore';
import { useCommandPaletteStore } from '@/stores/useCommandPaletteStore';
import { useAuthStore } from '@/stores/useAuthStore';

interface CommandPaletteProps {
  onSelectApp: (id: string) => void;
}

function resolveIcon(name: string): Icons.LucideIcon {
  const map = Icons as unknown as Record<string, Icons.LucideIcon>;
  return map[name] || Icons.AppWindow;
}

const CATEGORY_LABEL: Record<string, string> = {
  flagship: 'Insignia',
  science: 'Ingeniería',
  productivity: 'Productividad',
  development: 'Desarrollo',
  media: 'Medios',
  communication: 'Comunicación',
  games: 'Simulación',
  system: 'Sistema',
};

export default function CommandPalette({ onSelectApp }: CommandPaletteProps) {
  const { isOpen, close, toggle } = useCommandPaletteStore();
  const apps = useAppRegistry((s) => s.apps);
  const { recentIds, register } = useRecentAppsStore();
  const logout = useAuthStore((s) => s.logout);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        toggle();
      }
      if (e.key === 'Escape') close();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [toggle, close]);

  useEffect(() => {
    if (isOpen) {
      // Deja que el diálogo monte antes de enfocar, si no el primer
      // keystroke se lo come el navegador en algunos browsers.
      const t = setTimeout(() => inputRef.current?.focus(), 10);
      return () => clearTimeout(t);
    }
  }, [isOpen]);

  const recentApps = useMemo(
    () => recentIds.map((id) => apps.find((a) => a.id === id)).filter(Boolean) as typeof apps,
    [recentIds, apps]
  );

  const handleSelect = (id: string) => {
    if (id !== 'inicio') register(id);
    onSelectApp(id);
    close();
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0" style={{ zIndex: 'var(--z-modal-overlay)' }}>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="absolute inset-0"
            style={{ background: 'rgba(3,3,5,0.72)', backdropFilter: 'blur(6px)' }}
            onClick={close}
          />

          <motion.div
            initial={{ opacity: 0, y: 10, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 6, scale: 0.98 }}
            transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
            className="absolute left-1/2 top-[16vh] -translate-x-1/2 w-[min(560px,92vw)] rounded-xl overflow-hidden"
            style={{
              background: 'var(--glass-bg-heavy)',
              backdropFilter: 'var(--backdrop-blur)',
              border: '1px solid var(--glass-border)',
              boxShadow: 'var(--shadow-window-active)',
            }}
            role="dialog"
            aria-modal="true"
            aria-label="Buscar módulos y acciones"
          >
            <CommandPrimitive shouldFilter loop className="flex flex-col">
              <div
                className="flex items-center gap-3 px-5 border-b"
                style={{ borderColor: 'var(--glass-border)' }}
              >
                <Icons.Search className="w-[16px] h-[16px] shrink-0" style={{ color: 'var(--accent-gold)' }} />
                <CommandPrimitive.Input
                  ref={inputRef}
                  autoFocus
                  placeholder="Saltar a un módulo, expediente o acción…"
                  className="flex-1 h-[52px] bg-transparent outline-hidden text-[14px]"
                  style={{ color: 'var(--text-primary)' }}
                />
                <kbd
                  className="text-[10px] px-1.5 py-0.5 rounded shrink-0"
                  style={{ background: 'var(--surface)', color: 'var(--text-muted)', border: '1px solid var(--border-subtle)' }}
                >
                  ESC
                </kbd>
              </div>

              <CommandPrimitive.List className="max-h-[52vh] overflow-y-auto p-2">
                <CommandPrimitive.Empty
                  className="py-10 text-center text-[12.5px]"
                  style={{ color: 'var(--text-muted)' }}
                >
                  Sin resultados. Intenta con otro nombre de módulo.
                </CommandPrimitive.Empty>

                <CommandPrimitive.Item
                  value="inicio panel resumen dashboard"
                  onSelect={() => handleSelect('inicio')}
                  className="group flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer text-[13px] data-[selected=true]:bg-(--surface-hover)"
                  style={{ color: 'var(--text-primary)' }}
                >
                  <Icons.LayoutDashboard className="w-[16px] h-[16px]" style={{ color: 'var(--accent-gold)' }} />
                  <span className="font-medium">Inicio</span>
                  <span className="ml-auto text-[10.5px]" style={{ color: 'var(--text-muted)' }}>Panel general</span>
                </CommandPrimitive.Item>

                {recentApps.length > 0 && (
                  <CommandPrimitive.Group
                    heading="Recientes"
                    className="mt-1 **:[[cmdk-group-heading]]:px-3 **:[[cmdk-group-heading]]:py-1.5 **:[[cmdk-group-heading]]:text-[10px] **:[[cmdk-group-heading]]:uppercase **:[[cmdk-group-heading]]:tracking-[0.12em]"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    {recentApps.map((app) => {
                      const Icon = resolveIcon(app.icon);
                      return (
                        <CommandPrimitive.Item
                          key={`recent-${app.id}`}
                          value={`recent ${app.name} ${app.id}`}
                          onSelect={() => handleSelect(app.id)}
                          className="flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer text-[13px] data-[selected=true]:bg-(--surface-hover)"
                          style={{ color: 'var(--text-primary)' }}
                        >
                          <Icon className="w-[16px] h-[16px]" style={{ color: 'var(--accent-gold)' }} />
                          <span className="font-medium">{app.name}</span>
                          <Icons.Clock3 className="w-[12px] h-[12px] ml-auto" style={{ color: 'var(--text-muted)' }} />
                        </CommandPrimitive.Item>
                      );
                    })}
                  </CommandPrimitive.Group>
                )}

                <CommandPrimitive.Group
                  heading="Módulos"
                  className="mt-1 **:[[cmdk-group-heading]]:px-3 **:[[cmdk-group-heading]]:py-1.5 **:[[cmdk-group-heading]]:text-[10px] **:[[cmdk-group-heading]]:uppercase **:[[cmdk-group-heading]]:tracking-[0.12em]"
                  style={{ color: 'var(--text-muted)' }}
                >
                  {apps.map((app) => {
                    const Icon = resolveIcon(app.icon);
                    return (
                      <CommandPrimitive.Item
                        key={app.id}
                        value={`${app.name} ${app.id} ${CATEGORY_LABEL[app.category] ?? ''}`}
                        onSelect={() => handleSelect(app.id)}
                        className="flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer text-[13px] data-[selected=true]:bg-(--surface-hover)"
                        style={{ color: 'var(--text-primary)' }}
                      >
                        <Icon className="w-[16px] h-[16px]" style={{ color: 'var(--accent-gold)' }} />
                        <span className="font-medium">{app.name}</span>
                        <span className="ml-auto text-[10.5px]" style={{ color: 'var(--text-muted)' }}>
                          {CATEGORY_LABEL[app.category] ?? app.category}
                          {app.requiresPlan && app.requiresPlan !== 'FREE' ? ` · ${app.requiresPlan}` : ''}
                        </span>
                      </CommandPrimitive.Item>
                    );
                  })}
                </CommandPrimitive.Group>

                <CommandPrimitive.Group
                  heading="Sesión"
                  className="mt-1 **:[[cmdk-group-heading]]:px-3 **:[[cmdk-group-heading]]:py-1.5 **:[[cmdk-group-heading]]:text-[10px] **:[[cmdk-group-heading]]:uppercase **:[[cmdk-group-heading]]:tracking-[0.12em]"
                  style={{ color: 'var(--text-muted)' }}
                >
                  <CommandPrimitive.Item
                    value="cerrar sesion logout salir"
                    onSelect={() => { close(); logout(); }}
                    className="flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer text-[13px] data-[selected=true]:bg-(--surface-hover)"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    <Icons.LogOut className="w-[16px] h-[16px]" />
                    <span className="font-medium">Cerrar sesión</span>
                  </CommandPrimitive.Item>
                </CommandPrimitive.Group>
              </CommandPrimitive.List>

              <div
                className="flex items-center gap-4 px-5 py-2.5 border-t text-[10.5px]"
                style={{ borderColor: 'var(--glass-border)', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}
              >
                <span className="flex items-center gap-1.5"><Icons.ArrowUp className="w-3 h-3" /><Icons.ArrowDown className="w-3 h-3" /> navegar</span>
                <span className="flex items-center gap-1.5"><Icons.CornerDownLeft className="w-3 h-3" /> abrir</span>
                <span className="ml-auto flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--accent-gold)' }} />
                  MEGALODON
                </span>
              </div>
            </CommandPrimitive>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
