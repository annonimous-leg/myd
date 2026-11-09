// © 2026 Carl Own Megalodon
import { useEffect, useState } from 'react';
import { megalodonClient } from '@/lib/api-client';
import type { Actividad } from '@/lib/megalodon-client';
import GanttChart from '../programacion-obra/GanttChart';

type Estado =
  | { estado: 'cargando' }
  | { estado: 'error'; mensaje: string }
  | { estado: 'listo'; actividades: Actividad[] };

export default function CronogramaBim({
  expedienteId, programaId,
}: { expedienteId: string; programaId: string }) {
  const [resultado, setResultado] = useState<Estado>({ estado: 'cargando' });
  const [intento, setIntento] = useState(0);
  const [seleccion, setSeleccion] = useState<string | null>(null);

  useEffect(() => {
    let vigente = true;
    megalodonClient.programacion.listarActividades(expedienteId, programaId)
      .then(actividades => {
        if (vigente) setResultado({ estado: 'listo', actividades });
      })
      .catch(error => {
        if (vigente) setResultado({ estado: 'error', mensaje: error instanceof Error ? error.message : String(error) });
      });
    return () => { vigente = false; };
  }, [expedienteId, programaId, intento]);

  if (resultado.estado === 'cargando') return <p role="status">Cargando actividades del programa…</p>;
  if (resultado.estado === 'error') {
    return (
      <div>
        <p role="alert">{resultado.mensaje}</p>
        <button type="button" className="underline" onClick={() => {
          setResultado({ estado: 'cargando' });
          setIntento(anterior => anterior + 1);
        }}>Reintentar</button>
      </div>
    );
  }

  const fechadas = resultado.actividades.filter(actividad => actividad.inicio_temprano && actividad.fin_temprano);
  const pendientes = resultado.actividades.filter(actividad => !actividad.inicio_temprano || !actividad.fin_temprano);
  return (
    <section aria-label="Cronograma del modelo" className="mt-3 min-w-0 space-y-2 text-xs">
      <h3 className="font-semibold">Cronograma del modelo</h3>
      {resultado.actividades.length === 0 && <p>El programa todavía no tiene actividades.</p>}
      {fechadas.length > 0 && (
        <GanttChart actividades={fechadas} selectedId={seleccion} busy={false}
          onSelectActividad={setSeleccion} />
      )}
      {pendientes.length > 0 && (
        <details open={fechadas.length === 0}>
          <summary>{pendientes.length} actividades sin fechas calculadas</summary>
          <p>Calcula la ruta crítica en Workspace para verlas en el Gantt.</p>
          <ul className="max-h-40 list-disc overflow-auto pl-5">
            {pendientes.map(actividad => <li key={actividad.identificador}>{actividad.nombre}</li>)}
          </ul>
        </details>
      )}
    </section>
  );
}
