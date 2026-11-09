/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import * as Icons from 'lucide-react';
import { motion } from 'framer-motion';
import { useAppRegistry } from '@/stores/useAppRegistry';

interface SidebarProps {
  activeId: string;
  onSelect: (id: string) => void;
}

function resolveIcon(name: string): Icons.LucideIcon {
  const map = Icons as unknown as Record<string, Icons.LucideIcon>;
  return map[name] || Icons.AppWindow;
}

export default function Sidebar({ activeId, onSelect }: SidebarProps) {
  const apps = useAppRegistry((s) => s.apps);

  return (
    <aside
      className="flex flex-col h-full w-[68px] sm:w-[224px] shrink-0 border-r"
      style={{ background: 'var(--abyss)', borderColor: 'var(--border-subtle)' }}
    >
      <div className="flex items-center gap-2.5 px-3 sm:px-5 h-16 shrink-0 border-b" style={{ borderColor: 'var(--border-subtle)' }}>
        <div
          className="w-8 h-8 rounded-md flex items-center justify-center shrink-0"
          style={{ background: 'linear-gradient(135deg, var(--accent-gold-bright), var(--accent-gold-dim))' }}
        >
          <span className="text-[15px] font-bold text-[#12121A]" style={{ fontFamily: 'Cinzel, serif' }}>M</span>
        </div>
        <div className="hidden sm:block leading-tight">
          <div className="text-[13px] font-semibold tracking-wide" style={{ color: 'var(--text-primary)', fontFamily: 'Cinzel, serif' }}>
            MEGALODON
          </div>
          <div className="text-[9px] uppercase tracking-[0.14em]" style={{ color: 'var(--text-muted)' }}>
            Infraestructura Pública
          </div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto py-3 px-2.5 space-y-0.5">
        <SidebarItem
          icon={Icons.LayoutDashboard}
          label="Inicio"
          isActive={activeId === 'inicio'}
          onClick={() => onSelect('inicio')}
        />

        <div className="h-px my-2.5 mx-1.5" style={{ background: 'var(--border-subtle)' }} />

        {apps.map((app) => {
          const Icon = resolveIcon(app.icon);
          return (
            <SidebarItem
              key={app.id}
              icon={Icon}
              label={app.name}
              isActive={activeId === app.id}
              onClick={() => onSelect(app.id)}
            />
          );
        })}
      </nav>

      <div className="hidden sm:block px-4 py-3.5 border-t text-[10px] leading-relaxed" style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-muted)' }}>
        DOMINA. ANALIZA. CONSTRUYE. PROTEGE.
      </div>
    </aside>
  );
}

function SidebarItem({
  icon: Icon,
  label,
  isActive,
  onClick,
}: {
  icon: Icons.LucideIcon;
  label: string;
  isActive: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      title={label}
      className="relative w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-left transition-colors group"
      style={{
        background: isActive ? 'var(--surface-elevated)' : 'transparent',
        color: isActive ? 'var(--accent-gold-bright)' : 'var(--text-secondary)',
      }}
    >
      {isActive && (
        <motion.div
          layoutId="sidebar-active-rail"
          className="absolute left-0 top-1.5 bottom-1.5 w-[2.5px] rounded-full"
          style={{ background: 'var(--accent-gold)' }}
          transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
        />
      )}
      <Icon className="w-[17px] h-[17px] shrink-0" />
      <span className="hidden sm:block text-[13px] font-medium truncate group-hover:text-(--text-primary)" style={{ color: isActive ? 'var(--accent-gold-bright)' : undefined }}>
        {label}
      </span>
    </button>
  );
}
