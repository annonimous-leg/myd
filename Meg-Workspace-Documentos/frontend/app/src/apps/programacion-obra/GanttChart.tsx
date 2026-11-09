/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { useMemo, useRef, useState, useCallback } from 'react';
import { differenceInCalendarDays, addDays, format } from 'date-fns';
import { es } from 'date-fns/locale';
import type { Actividad } from '@/lib/megalodon-client';

const ROW_H = 36;
const PX_DIA = 28;
const LABEL_W = 240;
const DOT_R = 5;

interface ConnectingState {
  fromId: string;
  x: number;
  y: number;
}

interface ResizingState {
  id: string;
  startClientX: number;
  deltaDias: number;
}

export interface GanttChartProps {
  actividades: Actividad[];
  selectedId: string | null;
  busy: boolean;
  onSelectActividad: (id: string) => void;
  onResizeDuracion?: (id: string, nuevaDuracion: number) => void;
  onConectarDependencia?: (actividadId: string, nuevaPredecesora: string) => void;
}

/** Solo se puede dibujar el Gantt real (con fechas) para actividades que
 * ya pasaron por el CPM al menos una vez -- si no, inicio_temprano /
 * fin_temprano vienen null. El caller (index.tsx) filtra ese caso antes
 * de montar este componente en vez de que lo haga este componente
 * silenciosamente con fechas inventadas. */
export default function GanttChart({
  actividades,
  selectedId,
  busy,
  onSelectActividad,
  onResizeDuracion,
  onConectarDependencia,
}: GanttChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [connecting, setConnecting] = useState<ConnectingState | null>(null);
  const [resizing, setResizing] = useState<ResizingState | null>(null);

  const filas = useMemo(
    () =>
      [...actividades]
        .filter((a) => a.inicio_temprano && a.fin_temprano)
        .sort((a, b) => new Date(a.inicio_temprano!).getTime() - new Date(b.inicio_temprano!).getTime()),
    [actividades],
  );

  const { minDate, totalDias } = useMemo(() => {
    let min: Date | null = null;
    let max: Date | null = null;
    for (const a of filas) {
      const ini = new Date(a.inicio_temprano!);
      const fin = new Date(a.fin_temprano!);
      if (!min || ini < min) min = ini;
      if (!max || fin > max) max = fin;
    }
    if (!min || !max) return { minDate: new Date(), totalDias: 1 };
    return { minDate: min, totalDias: Math.max(differenceInCalendarDays(max, min) + 3, 5) };
  }, [filas]);

  const diaAX = useCallback((fecha: Date) => LABEL_W + differenceInCalendarDays(fecha, minDate) * PX_DIA, [minDate]);

  const relPos = useCallback((clientX: number, clientY: number) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0 };
    const scrollLeft = containerRef.current?.scrollLeft || 0;
    const scrollTop = containerRef.current?.scrollTop || 0;
    return { x: clientX - rect.left + scrollLeft, y: clientY - rect.top + scrollTop };
  }, []);

  // `fromId` se captura directamente en el closure de esta función (no se
  // lee del estado `connecting` en el mouseup) -- si se leyera del estado
  // ahí, el mouseup dispararía un closure viejo con el valor de
  // `connecting` de ANTES del mousedown (stale closure clásico), porque
  // los listeners se agregan en el mismo render síncrono en que se llama
  // setConnecting, antes de que React vuelva a renderizar con el valor
  // nuevo. El estado `connecting` solo se usa para pintar la línea.
  const iniciarConexion = (fromId: string, clientX: number, clientY: number) => {
    if (busy) return;
    const posInicial = relPos(clientX, clientY);
    setConnecting({ fromId, x: posInicial.x, y: posInicial.y });

    const onMove = (e: MouseEvent) => {
      const pos = relPos(e.clientX, e.clientY);
      setConnecting({ fromId, x: pos.x, y: pos.y });
    };
    const onUp = (e: MouseEvent) => {
      const el = document.elementFromPoint(e.clientX, e.clientY);
      const dot = el?.closest('[data-dot="left"]') as HTMLElement | null;
      const targetId = dot?.dataset.activityId;
      if (targetId && targetId !== fromId) {
        onConectarDependencia?.(targetId, fromId);
      }
      setConnecting(null);
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  const onMouseMoveResize = useCallback((e: MouseEvent) => {
    setResizing((r) => {
      if (!r) return r;
      const deltaPx = e.clientX - r.startClientX;
      return { ...r, deltaDias: Math.round(deltaPx / PX_DIA) };
    });
  }, []);

  const onMouseUpResize = useCallback(
    (e: MouseEvent) => {
      setResizing((r) => {
        if (r) {
          const deltaPx = e.clientX - r.startClientX;
          const deltaDias = Math.round(deltaPx / PX_DIA);
          const act = actividades.find((a) => a.identificador === r.id);
          if (act && deltaDias !== 0) {
            const nueva = Math.max(0.5, act.duracion + deltaDias);
            onResizeDuracion?.(r.id, nueva);
          }
        }
        return null;
      });
      window.removeEventListener('mousemove', onMouseMoveResize);
      window.removeEventListener('mouseup', onMouseUpResize);
    },
    [actividades, onResizeDuracion, onMouseMoveResize],
  );

  const iniciarResize = (id: string, clientX: number) => {
    if (busy) return;
    setResizing({ id, startClientX: clientX, deltaDias: 0 });
    window.addEventListener('mousemove', onMouseMoveResize);
    window.addEventListener('mouseup', onMouseUpResize);
  };

  if (filas.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-sm text-[#8A8578] p-6 text-center">
        Ninguna actividad tiene fechas calculadas todavía. Ejecuta "Calcular CPM" para generar el Gantt.
      </div>
    );
  }

  const chartWidth = LABEL_W + totalDias * PX_DIA;
  const chartHeight = filas.length * ROW_H + 40;
  const indexPorId = new Map(filas.map((a, i) => [a.identificador, i]));

  // Ticks de fecha: uno cada 2 días si hay poco espacio, si no cada día.
  const pasoTick = totalDias > 40 ? 5 : totalDias > 20 ? 2 : 1;
  const ticks = Array.from({ length: Math.ceil(totalDias / pasoTick) }, (_, i) => addDays(minDate, i * pasoTick));

  return (
    <div ref={containerRef} className="flex-1 overflow-auto relative bg-[#0A0A0F]">
      <div style={{ width: chartWidth, height: chartHeight, position: 'relative' }}>
        {/* Cabecera de fechas */}
        <div
          className="sticky top-0 z-20 bg-[#0F0F16] border-b border-[#2A2A3E]"
          style={{ height: 28, width: chartWidth }}
        >
          <div className="sticky left-0 inline-block bg-[#0F0F16]" style={{ width: LABEL_W, height: 28 }} />
          {ticks.map((t, i) => (
            <span
              key={i}
              className="absolute text-[10px] text-[#8A8578] top-1.5"
              style={{ left: diaAX(t) }}
            >
              {format(t, 'd MMM', { locale: es })}
            </span>
          ))}
        </div>

        {/* Líneas verticales de guía */}
        {ticks.map((t, i) => (
          <div
            key={i}
            className="absolute top-7 bottom-0 border-l border-[#1C1C28]"
            style={{ left: diaAX(t) }}
          />
        ))}

        {/* SVG de dependencias */}
        <svg
          className="absolute top-7 left-0 pointer-events-none"
          width={chartWidth}
          height={chartHeight}
          style={{ overflow: 'visible' }}
        >
          {filas.map((act) =>
            (act.predecesoras || []).map((predId) => {
              const predIdx = indexPorId.get(predId);
              const thisIdx = indexPorId.get(act.identificador);
              const pred = filas.find((a) => a.identificador === predId);
              if (predIdx === undefined || thisIdx === undefined || !pred) return null;
              const x1 = diaAX(new Date(pred.fin_temprano!));
              const y1 = predIdx * ROW_H + ROW_H / 2;
              const x2 = diaAX(new Date(act.inicio_temprano!));
              const y2 = thisIdx * ROW_H + ROW_H / 2;
              const midX = x1 + 10;
              const critica = act.en_ruta_critica && pred.en_ruta_critica;
              return (
                <path
                  key={`${predId}->${act.identificador}`}
                  d={`M ${x1} ${y1} L ${midX} ${y1} L ${midX} ${y2} L ${x2} ${y2}`}
                  fill="none"
                  stroke={critica ? '#C9A84C' : '#3A3A4E'}
                  strokeWidth={1.5}
                  markerEnd="url(#arrow)"
                />
              );
            }),
          )}
          {connecting &&
            (() => {
              const fromIdx = indexPorId.get(connecting.fromId);
              const from = filas.find((a) => a.identificador === connecting.fromId);
              if (fromIdx === undefined || !from) return null;
              const x1 = diaAX(new Date(from.fin_temprano!));
              const y1 = fromIdx * ROW_H + ROW_H / 2;
              return (
                <line
                  x1={x1}
                  y1={y1}
                  x2={connecting.x}
                  y2={connecting.y - 28}
                  stroke="#C9A84C"
                  strokeDasharray="4 3"
                  strokeWidth={1.5}
                />
              );
            })()}
          <defs>
            <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
              <path d="M0,0 L0,6 L6,3 z" fill="#3A3A4E" />
            </marker>
          </defs>
        </svg>

        {/* Filas + barras */}
        {filas.map((act, i) => {
          const top = i * ROW_H + 28;
          const left = diaAX(new Date(act.inicio_temprano!));
          let width = Math.max(
            differenceInCalendarDays(new Date(act.fin_temprano!), new Date(act.inicio_temprano!)) * PX_DIA,
            PX_DIA * 0.5,
          );
          if (resizing && resizing.id === act.identificador) {
            width = Math.max(width + resizing.deltaDias * PX_DIA, PX_DIA * 0.5);
          }
          const seleccionada = selectedId === act.identificador;

          return (
            <div key={act.identificador}>
              <div
                className="absolute text-xs text-[#C9C7BE] truncate pr-2 flex items-center gap-1.5"
                style={{ left: 8, top, width: LABEL_W - 12, height: ROW_H }}
              >
                {act.en_ruta_critica && <span className="w-1.5 h-1.5 rounded-full bg-[#B84A4A] shrink-0" />}
                <span className="truncate">{act.nombre}</span>
              </div>

              <button
                onClick={() => onSelectActividad(act.identificador)}
                className="absolute rounded-md flex items-center transition-colors"
                style={{
                  left,
                  top: top + 6,
                  width,
                  height: ROW_H - 12,
                  background: act.en_ruta_critica ? 'rgba(184,74,74,0.25)' : 'rgba(90,140,200,0.25)',
                  border: `1px solid ${seleccionada ? '#C9A84C' : act.en_ruta_critica ? '#B84A4A' : '#5A8CC8'}`,
                }}
              >
                <div
                  className="h-full rounded-sm"
                  style={{
                    width: `${Math.min(act.porcentaje_avance, 100)}%`,
                    background: act.en_ruta_critica ? 'rgba(184,74,74,0.55)' : 'rgba(90,140,200,0.55)',
                  }}
                />
              </button>

              {/* Conector de entrada (predecesora) */}
              {onConectarDependencia && (<>
                <div
                  data-dot="left"
                  data-activity-id={act.identificador}
                  className="absolute rounded-full border border-[#8A8578] bg-[#0A0A0F] hover:bg-[#C9A84C] hover:border-[#C9A84C] cursor-crosshair"
                  style={{ left: left - DOT_R, top: top + ROW_H / 2 - 6 - DOT_R, width: DOT_R * 2, height: DOT_R * 2 }}
                  title="Suelta aquí para conectar como sucesora"
                />

                {/* Conector de salida (arrastrar para crear dependencia) */}
                <div
                  data-dot="right"
                  data-activity-id={act.identificador}
                  onMouseDown={(e) => {
                    e.stopPropagation();
                    iniciarConexion(act.identificador, e.clientX, e.clientY);
                  }}
                  className="absolute rounded-full border border-[#8A8578] bg-[#0A0A0F] hover:bg-[#C9A84C] hover:border-[#C9A84C] cursor-crosshair"
                  style={{
                    left: left + width - DOT_R,
                    top: top + ROW_H / 2 - 6 - DOT_R,
                    width: DOT_R * 2,
                    height: DOT_R * 2,
                  }}
                  title="Arrastra para conectar como predecesora de otra actividad"
                />

              </>)}

              {/* Handle de resize (duración) */}
              {onResizeDuracion && (
                <div
                  onMouseDown={(e) => {
                    e.stopPropagation();
                    iniciarResize(act.identificador, e.clientX);
                  }}
                  className="absolute cursor-ew-resize"
                  style={{ left: left + width - 4, top: top + 6, width: 8, height: ROW_H - 12 }}
                  title="Arrastra para cambiar la duración"
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
