/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { Suspense, lazy, useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import Sidebar from './Sidebar';
import TopBar from './TopBar';
import Home from './Home';
import CommandPalette from './CommandPalette';
import { useAppRegistry } from '@/stores/useAppRegistry';
import { useRecentAppsStore } from '@/stores/useRecentAppsStore';
import { useExpedienteStore } from '@/stores/useExpedienteStore';

const appModules = import.meta.glob('../apps/*/index.tsx') as Record<
  string,
  () => Promise<{ default: React.ComponentType }>
>;
const loadedApps = new Map<string, React.ComponentType>();

function getAppComponent(appId: string) {
  const loaded = loadedApps.get(appId);
  if (loaded) return loaded;
  const path = `../apps/${appId}/index.tsx`;
  const loader = appModules[path];
  if (!loader) {
    return () => (
      <div className="w-full h-full flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>
        <p className="text-sm">App no encontrada: {appId}</p>
      </div>
    );
  }
  const component = lazy(loader);
  loadedApps.set(appId, component);
  return component;
}

export default function CommandCenter() {
  const [activeId, setActiveId] = useState(() => {
    const value = new URLSearchParams(window.location.search).get('app');
    return value && appModules[`../apps/${value}/index.tsx`] ? value : 'inicio';
  });
  const { getApp } = useAppRegistry();
  const registerRecent = useRecentAppsStore((s) => s.register);
  const cargarExpedientes = useExpedienteStore(s => s.cargarExpedientes);
  const errorExpedientes = useExpedienteStore(s => s.error);
  useEffect(() => { void cargarExpedientes(); }, [cargarExpedientes]);
  const activeApp = activeId !== 'inicio' ? getApp(activeId) : null;
  const title = activeId === 'inicio' ? 'Inicio' : activeApp?.name || activeId;

  useEffect(() => {
    const onPopState = () => {
      const value = new URLSearchParams(window.location.search).get('app');
      setActiveId(value && appModules[`../apps/${value}/index.tsx`] ? value : 'inicio');
    };
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  const navigateTo = (id: string) => {
    if (id !== 'inicio') registerRecent(id);
    const url = new URL(window.location.href);
    if (id === 'inicio') url.searchParams.delete('app');
    else url.searchParams.set('app', id);
    window.history.pushState({}, '', url);
    setActiveId(id);
  };

  return (
    <div className="flex w-full h-full overflow-hidden" style={{ background: 'var(--void)' }}>
      <CommandPalette onSelectApp={navigateTo} />
      <Sidebar activeId={activeId} onSelect={navigateTo} />

      <div className="flex flex-col flex-1 min-w-0">
        <TopBar title={title} />
        {errorExpedientes && <div role="alert" className="px-4 py-2 text-sm text-red-300 bg-red-950/40">
          No se pudo recuperar el expediente: {errorExpedientes}
          <button className="ml-3 underline" onClick={() => void cargarExpedientes()}>Reintentar</button>
        </div>}

        <main className="flex-1 min-h-0 relative">
          <AnimatePresence mode="wait">
            <motion.div
              key={activeId}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="absolute inset-0"
            >
              {activeId === 'inicio' ? (
                <Home onOpenApp={navigateTo} />
              ) : (
                <Suspense
                  fallback={
                    <div className="w-full h-full flex items-center justify-center">
                      <div
                        className="w-6 h-6 border-2 rounded-full animate-spin"
                        style={{ borderColor: 'var(--accent-gold-dim)', borderTopColor: 'var(--accent-gold)' }}
                      />
                    </div>
                  }
                >
                  {(() => {
                    const AppComponent = getAppComponent(activeId);
                    return <AppComponent />;
                  })()}
                </Suspense>
              )}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </div>
  );
}
