/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

/**
 * Megalodon Compliance Dashboard — Backend real obligatorio.
 * NO hay fallback a datos demo: si el backend no responde, cada panel
 * muestra su propio error inline (no bloquea a los demás tabs).
 *
 * Reescritura completa. La versión anterior tenía dos bugs de fondo:
 *  1. `setReglas(reglasRes as ReglaCumplimiento[])` sobre una respuesta que
 *     el backend siempre pagina como `{ total, items }`; tronaba en cuanto
 *     existiera una sola regla real. Ya corregido también en el cliente.
 *  2. Interfaces locales inventadas: `Inconformidad.fecha_registro`,
 *     `Sancion.proveedor`/`estado`; no correspondían a los schemas reales
 *     del backend. Ahora los 4 tabs usan los tipos reales de megalodon-client.
 */
import { useState } from 'react';
import { Shield, ListChecks, MessageSquareWarning, Gavel, ClipboardCheck } from 'lucide-react';
import ReglasPanel from './components/ReglasPanel';
import InconformidadesPanel from './components/InconformidadesPanel';
import SancionesPanel from './components/SancionesPanel';
import EvaluarPanel from './components/EvaluarPanel';

type Tab = 'reglas' | 'inconformidades' | 'sanciones' | 'evaluar';

const TABS: { id: Tab; label: string; icon: typeof ListChecks }[] = [
  { id: 'reglas', label: 'Reglas', icon: ListChecks },
  { id: 'inconformidades', label: 'Inconformidades', icon: MessageSquareWarning },
  { id: 'sanciones', label: 'Sanciones', icon: Gavel },
  { id: 'evaluar', label: 'Evaluar expediente', icon: ClipboardCheck },
];

export default function ComplianceDashboardApp() {
  const [tab, setTab] = useState<Tab>('reglas');

  return (
    <div className="flex flex-col h-full" style={{ background: 'var(--abyss)', color: 'var(--text-primary)' }}>
      <div className="flex items-center gap-2 px-4 py-3" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        <Shield size={18} style={{ color: 'var(--accent-gold)' }} />
        <h1 className="text-sm font-semibold">Compliance Dashboard</h1>
      </div>

      <div className="flex items-center gap-1 px-3 pt-2" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-t"
            style={
              tab === id
                ? { color: 'var(--accent-gold)', borderBottom: '2px solid var(--accent-gold)', background: 'var(--surface)' }
                : { color: 'var(--text-secondary)', borderBottom: '2px solid transparent' }
            }
          >
            <Icon size={13} />
            {label}
          </button>
        ))}
      </div>

      <div className="flex-1 min-h-0">
        {tab === 'reglas' && <ReglasPanel />}
        {tab === 'inconformidades' && <InconformidadesPanel />}
        {tab === 'sanciones' && <SancionesPanel />}
        {tab === 'evaluar' && <EvaluarPanel />}
      </div>
    </div>
  );
}
