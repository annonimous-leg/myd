/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

/**
 * Topografía & GIS — shell con tabs.
 *
 * Reescritura sobre la app que ya existía (448 líneas, funcional: visor 3D
 * TIN, CSV, volumen corte/relleno, presupuesto, contexto Tezcatlipoca). Se
 * conserva TODA esa funcionalidad real, movida a components/LevantamientoPanel.tsx,
 * y se agrega:
 *  - Mapa real (MapaReal.tsx, MapLibre GL) en vez del único visor 3D --
 *    OSM / Esri satélite / NASA GIBS, sin API key.
 *  - Puntos, Poligonal, Perfil, Curvas: los 4 ya tenían endpoint real en el
 *    backend (curvasNivel, generarPerfil, transformarCoordenadas,
 *    cierrePoligonal) pero el frontend nunca los usaba.
 *  - El tab Mapa es el puente real Topografía <-> Tezcatlipoca: transforma
 *    los puntos del levantamiento a lon/lat con el endpoint real y con ese
 *    bbox alimenta el feed de Tezcatlipoca (aeronaves/barcos/sismos cerca
 *    del sitio real, no un query global).
 *
 * Nota: el backend de Tezcatlipoca es más grande que lo que este frontend
 * expone todavía (confirmado) -- este pase cubre el puente geoespacial
 * hacia Topografía, no los demás hubs (Cyber/OSINT/SAR tienen su propio
 * harness en apps/tezcatlipoca-hub, sin tocar aquí).
 */
import { useState } from 'react';
import { Mountain, Map as MapIcon, Layers3, MapPin, Hexagon, TrendingUp, Waves, FolderKanban, type LucideIcon } from 'lucide-react';
import { useExpedienteStore } from '@/stores/useExpedienteStore';
import type { Levantamiento, SuperficieTIN } from '@/lib/megalodon-client';
import MapaPanel from './components/MapaPanel';
import LevantamientoPanel from './components/LevantamientoPanel';
import PuntosPanel from './components/PuntosPanel';
import PoligonalPanel from './components/PoligonalPanel';
import PerfilPanel from './components/PerfilPanel';
import CurvasPanel from './components/CurvasPanel';

type Tab = 'mapa' | 'levantamiento' | 'puntos' | 'poligonal' | 'perfil' | 'curvas';
const TABS: { id: Tab; label: string; icon: LucideIcon }[] = [
  { id: 'mapa', label: 'Mapa', icon: MapIcon },
  { id: 'levantamiento', label: 'Levantamiento', icon: Layers3 },
  { id: 'puntos', label: 'Puntos', icon: MapPin },
  { id: 'poligonal', label: 'Poligonal', icon: Hexagon },
  { id: 'perfil', label: 'Perfil', icon: TrendingUp },
  { id: 'curvas', label: 'Curvas', icon: Waves },
];

export default function TopografiaApp() {
  const expedienteActivo = useExpedienteStore((s) => s.expedienteActivo());
  return <TopografiaWorkspace key={expedienteActivo?.id || 'sin-expediente'} expedienteActivo={expedienteActivo} />;
}

function TopografiaWorkspace({ expedienteActivo }: {
  expedienteActivo: ReturnType<ReturnType<typeof useExpedienteStore.getState>['expedienteActivo']>;
}) {
  const [tab, setTab] = useState<Tab>('mapa');
  const [levantamiento, setLevantamiento] = useState<Levantamiento | null>(null);
  const [superficies, setSuperficies] = useState<SuperficieTIN[]>([]);

  if (!expedienteActivo) {
    return (
      <div className="w-full h-full flex flex-col items-center justify-center gap-2 text-center px-6" style={{ color: 'var(--text-muted)' }}>
        <FolderKanban size={32} style={{ opacity: 0.5 }} />
        <p className="text-sm">No hay ningún expediente activo.</p>
        <p className="text-xs">Abre la app &quot;Proyectos&quot; y selecciona o crea un expediente primero.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full" style={{ background: 'var(--void)', color: 'var(--text-primary)' }}>
      <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        <div className="flex items-center gap-2">
          <Mountain size={17} style={{ color: 'var(--accent-gold)' }} />
          <h1 className="text-sm font-semibold">Topografía &amp; GIS</h1>
          {levantamiento && <span className="text-xs" style={{ color: 'var(--text-muted)' }}>· {levantamiento.nombre}</span>}
        </div>
        <span className="flex items-center gap-1.5 text-[10px] font-medium px-2 py-1 rounded-full" style={{ color: 'var(--accent-purple)', background: 'var(--accent-purple)14', border: '1px solid var(--accent-purple)33' }}>
          <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: 'var(--accent-purple)' }} />
          TEZCATLIPOCA
        </span>
      </div>

      <div className="flex items-center gap-1 px-3 pt-1.5" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-t-md"
            style={
              tab === id
                ? { color: 'var(--accent-gold)', borderBottom: '2px solid var(--accent-gold)', background: 'var(--surface)' }
                : { color: 'var(--text-secondary)', borderBottom: '2px solid transparent' }
            }
          >
            <Icon size={13} /> {label}
          </button>
        ))}
      </div>

      <div className="flex-1 min-h-0">
        {tab === 'mapa' && <MapaPanel levantamiento={levantamiento} />}
        {tab === 'levantamiento' && (
          <LevantamientoPanel
            expedienteId={expedienteActivo.id}
            onLevantamientoChange={setLevantamiento}
            onSuperficiesChange={setSuperficies}
          />
        )}
        {tab === 'puntos' && <PuntosPanel levantamiento={levantamiento} />}
        {tab === 'poligonal' && <PoligonalPanel levantamiento={levantamiento} />}
        {tab === 'perfil' && <PerfilPanel superficies={superficies} levantamiento={levantamiento} />}
        {tab === 'curvas' && <CurvasPanel superficies={superficies} />}
      </div>
    </div>
  );
}
