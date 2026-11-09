/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { useEffect, useState } from 'react';
import * as Icons from 'lucide-react';
import { motion } from 'framer-motion';
import { megalodonClient } from '@/lib/api-client';
import type { DashboardResponse } from '@/lib/megalodon-client';
import { useAppRegistry } from '@/stores/useAppRegistry';
import AnimatedNumber from './AnimatedNumber';

interface HomeProps {
  onOpenApp: (id: string) => void;
}

function resolveIcon(name: string): Icons.LucideIcon {
  const map = Icons as unknown as Record<string, Icons.LucideIcon>;
  return map[name] || Icons.AppWindow;
}

export default function Home({ onOpenApp }: HomeProps) {
  const apps = useAppRegistry((s) => s.apps);
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tez, setTez] = useState<any | null>(null);
  const [tezError, setTezError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    megalodonClient.dashboard
      .stats()
      .then((res) => { if (!cancelled) { setData(res); setError(null); } })
      .catch(() => { if (!cancelled) setError('No se pudo conectar con el backend.'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    megalodonClient.tezcatlipoca.telemetry()
      .then((res) => { if (!cancelled) { setTez(res); setTezError(null); } })
      .catch((e) => { if (!cancelled) setTezError(e instanceof Error ? e.message : 'Tezcatlipoca no disponible'); });
    return () => { cancelled = true; };
  }, []);

  const summaryCards = data ? [
    { label: 'Licitaciones en proceso', value: data.stats.licitaciones_en_proceso, of: data.stats.total_licitaciones, icon: Icons.Gavel },
    { label: 'Expedientes activos', value: data.stats.expedientes_activos, of: data.stats.total_expedientes, icon: Icons.FolderKanban },
    { label: 'Contratos vigentes', value: data.stats.contratos_vigentes, of: data.stats.total_contratos, icon: Icons.FileCheck2 },
    { label: 'Documentos pendientes', value: data.stats.documentos_pendientes_firma, of: data.stats.total_documentos, icon: Icons.FileSignature },
  ] : [];

  return (
    <div className="h-full overflow-y-auto px-8 py-7">
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 mb-6">
        {loading && Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-[92px] rounded-xl animate-pulse" style={{ background: 'var(--surface-elevated)' }} />
        ))}

        {!loading && error && (
          <div
            className="lg:col-span-4 rounded-xl px-5 py-4 text-[13px] flex items-center gap-2.5"
            style={{ background: 'var(--surface-elevated)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}
          >
            <Icons.PlugZap className="w-4 h-4 shrink-0" style={{ color: 'var(--amber)' }} />
            {error} Los números de este panel salen de <code className="text-[11.5px]" style={{ color: 'var(--text-primary)' }}>/api/v1/dashboard/stats</code> — conecta el backend para verlos.
          </div>
        )}

        {!loading && !error && summaryCards.map((card, i) => (
          <motion.div
            key={card.label}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: i * 0.04, ease: [0.16, 1, 0.3, 1] }}
            whileHover={{ y: -2 }}
            className="group relative rounded-xl px-5 py-4 border overflow-hidden cursor-default"
            style={{
              background: 'var(--glass-bg)',
              backdropFilter: 'var(--backdrop-blur)',
              borderColor: 'var(--border-subtle)',
              transition: 'border-color 250ms, box-shadow 250ms',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = 'var(--accent-gold-dim)';
              e.currentTarget.style.boxShadow = 'var(--shadow-glow-gold)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'var(--border-subtle)';
              e.currentTarget.style.boxShadow = 'none';
            }}
          >
            <div
              className="absolute inset-x-0 top-0 h-[2px] scale-x-0 group-hover:scale-x-100 origin-left transition-transform duration-300"
              style={{ background: 'linear-gradient(90deg, var(--accent-gold), transparent)' }}
            />
            <div className="flex items-start justify-between mb-2.5">
              <card.icon className="w-[18px] h-[18px]" style={{ color: 'var(--accent-gold)' }} />
              <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>de {card.of}</span>
            </div>
            <div className="text-[26px] font-semibold leading-none mb-1.5" style={{ color: 'var(--text-primary)', fontFamily: 'Cinzel, serif' }}>
              <AnimatedNumber value={card.value} />
            </div>
            <div className="text-[11.5px]" style={{ color: 'var(--text-secondary)' }}>{card.label}</div>
          </motion.div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 space-y-5">
          <section className="rounded-xl border overflow-hidden" style={{ background: 'var(--surface-elevated)', borderColor: 'var(--border-subtle)' }}>
            <div className="px-5 py-3.5 border-b flex items-center gap-2" style={{ borderColor: 'var(--border-subtle)' }}>
              <Icons.Zap className="w-4 h-4" style={{ color: 'var(--accent-gold)' }} />
              <h2 className="text-[13px] font-semibold" style={{ color: 'var(--text-primary)' }}>Acceso rápido</h2>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 p-4">
              {apps.map((app) => {
                const Icon = resolveIcon(app.icon);
                return (
                  <motion.button
                    key={app.id}
                    onClick={() => onOpenApp(app.id)}
                    whileHover={{ y: -1 }}
                    whileTap={{ scale: 0.98 }}
                    className="flex flex-col items-start gap-2 p-3 rounded-lg text-left transition-all hover:bg-(--surface-hover)"
                    style={{ border: '1px solid var(--border-subtle)' }}
                    onMouseEnter={(e) => { e.currentTarget.style.boxShadow = 'var(--shadow-glow-gold)'; e.currentTarget.style.borderColor = 'var(--accent-gold-dim)'; }}
                    onMouseLeave={(e) => { e.currentTarget.style.boxShadow = 'none'; e.currentTarget.style.borderColor = 'var(--border-subtle)'; }}
                  >
                    <Icon className="w-4 h-4" style={{ color: 'var(--accent-gold)' }} />
                    <span className="text-[12px] font-medium leading-tight" style={{ color: 'var(--text-primary)' }}>{app.name}</span>
                  </motion.button>
                );
              })}
            </div>
          </section>

          <section className="rounded-xl border overflow-hidden" style={{ background: 'var(--surface-elevated)', borderColor: 'var(--border-subtle)' }}>
            <div className="px-5 py-3.5 border-b flex items-center gap-2" style={{ borderColor: 'var(--border-subtle)' }}>
              <Icons.Activity className="w-4 h-4" style={{ color: 'var(--accent-gold)' }} />
              <h2 className="text-[13px] font-semibold" style={{ color: 'var(--text-primary)' }}>Actividad reciente</h2>
            </div>
            <div className="divide-y" style={{ borderColor: 'var(--border-subtle)' }}>
              {loading && (
                <div className="px-5 py-6 text-[12px] text-center" style={{ color: 'var(--text-muted)' }}>Cargando…</div>
              )}
              {!loading && (data?.recent_activity?.length ?? 0) === 0 && (
                <div className="px-5 py-6 text-[12px] text-center" style={{ color: 'var(--text-muted)' }}>
                  Sin actividad registrada todavía.
                </div>
              )}
              {!loading && data?.recent_activity?.map((item) => (
                <div key={item.id} className="px-5 py-3 flex items-center justify-between text-[12.5px]">
                  <div>
                    <span style={{ color: 'var(--text-primary)' }}>{item.accion}</span>
                    <span style={{ color: 'var(--text-secondary)' }}> · {item.entidad}</span>
                  </div>
                  <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>{item.usuario}</span>
                </div>
              ))}
            </div>
          </section>
        </div>

        <div className="space-y-5">
          <section className="rounded-xl border overflow-hidden" style={{ background: 'var(--surface-elevated)', borderColor: 'var(--border-subtle)' }}>
            <div className="px-5 py-3.5 border-b flex items-center justify-between" style={{ borderColor: 'var(--border-subtle)' }}>
              <div className="flex items-center gap-2">
                <Icons.Globe2 className="w-4 h-4" style={{ color: 'var(--accent-gold)' }} />
                <h2 className="text-[13px] font-semibold" style={{ color: 'var(--text-primary)' }}>Tezcatlipoca · Geo Hub</h2>
              </div>
              <span className="text-[10px]" style={{ color: tez?.status === 'online' ? 'var(--success)' : 'var(--text-muted)' }}>{tez?.status ?? (tezError ? 'offline' : 'conectando…')}</span>
            </div>
            <div className="p-4 space-y-3">
              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-lg p-3" style={{ background: 'var(--surface)' }}>
                  <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>Fuentes en memoria</div>
                  <div className="text-xl font-semibold" style={{ color: 'var(--text-primary)' }}>{tez?.sources ?? 0}</div>
                </div>
                <div className="rounded-lg p-3" style={{ background: 'var(--surface)' }}>
                  <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>Capas activas</div>
                  <div className="text-xl font-semibold" style={{ color: 'var(--text-primary)' }}>{tez?.active_layers?.length ?? 0}</div>
                </div>
              </div>
              <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                Contexto geoespacial compartido mediante el bridge autenticado Megalodon ↔ Tezcatlipoca.
              </div>
              <button onClick={() => onOpenApp('topografia')} className="w-full rounded-md px-3 py-2 text-[11px] font-medium" style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}>Abrir Topografía + contexto Tezcatlipoca</button>
            </div>
          </section>

          {!loading && !error && data && data.kpis.length > 0 && (
            <section className="rounded-xl border overflow-hidden" style={{ background: 'var(--surface-elevated)', borderColor: 'var(--border-subtle)' }}>
              <div className="px-5 py-3.5 border-b" style={{ borderColor: 'var(--border-subtle)' }}>
                <h2 className="text-[13px] font-semibold" style={{ color: 'var(--text-primary)' }}>KPIs</h2>
              </div>
              <div className="divide-y" style={{ borderColor: 'var(--border-subtle)' }}>
                {data.kpis.map((kpi) => (
                  <div key={kpi.label} className="px-5 py-3 flex items-center justify-between">
                    <span className="text-[12px]" style={{ color: 'var(--text-secondary)' }}>{kpi.label}</span>
                    <span className="text-[13px] font-semibold" style={{ color: 'var(--text-primary)' }}>{kpi.value}</span>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
