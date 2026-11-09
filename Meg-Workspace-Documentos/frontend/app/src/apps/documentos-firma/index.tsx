/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

/**
 * Documentos & Firma — Repositorio documental (CDE) + firma electrónica.
 *
 * El backend ya tenía clasificación, versionado, detección de duplicados,
 * búsqueda avanzada, estadísticas (app/api/v1/documentos.py) y firma real
 * (XAdES/PAdES, sellado CFDI, Merkle de expediente — app/api/v1/firma.py)
 * pero no existía ninguna app en el shell para usarlos: el cliente TS
 * tenía firma.* desde hace tiempo, y documentos.* se agrega junto con
 * esta app. Esto cierra el hueco "Backend adelantado: MUY ALTO" que
 * marcaba la auditoría para Firma y para Documentos/CDE.
 */
import { useState } from 'react';
import { FileStack, FileSignature, FolderKanban, type LucideIcon } from 'lucide-react';
import { useExpedienteStore } from '@/stores/useExpedienteStore';
import RepositorioPanel from './components/RepositorioPanel';
import FirmaPanel from './components/FirmaPanel';

type Tab = 'repositorio' | 'firma';

const TABS: { id: Tab; label: string; icon: LucideIcon }[] = [
  { id: 'repositorio', label: 'Repositorio (CDE)', icon: FileStack },
  { id: 'firma', label: 'Firma Electrónica', icon: FileSignature },
];

export default function DocumentosFirmaApp() {
  const expediente = useExpedienteStore((s) => s.expedienteActivo());
  const [tab, setTab] = useState<Tab>('repositorio');

  if (!expediente) {
    return (
      <div
        className="w-full h-full flex flex-col items-center justify-center gap-2 text-center px-6"
        style={{ color: 'var(--text-muted)' }}
      >
        <FolderKanban size={28} className="opacity-40" />
        <p className="text-sm">No hay ningún expediente activo.</p>
        <p className="text-xs">Abre la app &quot;Proyectos&quot; y selecciona o crea un expediente primero.</p>
      </div>
    );
  }

  return (
    <div
      className="w-full h-full flex flex-col overflow-hidden"
      style={{ background: 'var(--void)', color: 'var(--text-primary)' }}
    >
      <div
        className="flex items-center justify-between px-3 py-2 shrink-0"
        style={{ background: 'var(--surface)', borderBottom: '1px solid var(--border-subtle)' }}
      >
        <div className="flex items-center gap-2">
          <FileStack size={16} style={{ color: 'var(--accent-gold)' }} />
          <span className="text-sm font-semibold">Documentos &amp; Firma</span>
          <span className="text-xs ml-2" style={{ color: 'var(--text-muted)' }}>
            {expediente.identificador || expediente.titulo}
          </span>
        </div>
      </div>

      <div
        className="flex items-center gap-1 px-3 pt-2 shrink-0"
        style={{ borderBottom: '1px solid var(--border-subtle)', background: 'var(--surface)' }}
      >
        {TABS.map((t) => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-t-md transition-colors"
              style={{
                color: active ? 'var(--accent-gold)' : 'var(--text-secondary)',
                background: active ? 'var(--surface-elevated)' : 'transparent',
                borderBottom: active ? '2px solid var(--accent-gold)' : '2px solid transparent',
              }}
            >
              <Icon size={13} />
              {t.label}
            </button>
          );
        })}
      </div>

      <div className="flex-1 min-h-0 overflow-auto">
        {tab === 'repositorio' && <RepositorioPanel expedienteId={expediente.id} />}
        {tab === 'firma' && <FirmaPanel expedienteId={expediente.id} />}
      </div>
    </div>
  );
}
