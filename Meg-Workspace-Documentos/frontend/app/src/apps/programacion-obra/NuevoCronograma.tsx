// © 2026 Carl Own Megalodon
import { useState, type FormEvent } from 'react';
import { megalodonClient } from '@/lib/api-client';
import type { Programa } from '@/lib/megalodon-client';

export default function NuevoCronograma({ expedienteId, onCreated }: {
  expedienteId: string; onCreated: (programa: Programa) => void;
}) {
  const [nombre, setNombre] = useState('');
  const [fecha, setFecha] = useState('');
  const [filas, setFilas] = useState([{ nombre: '', duracion: '' }]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function guardar(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      const programa = await megalodonClient.programacion.crear(expedienteId, {
        nombre: nombre.trim(), fecha_inicio: fecha + 'T00:00:00',
        descripcion: 'Cronograma creado por el usuario en Workspace',
        actividades: filas.map((fila, index) => ({
          id: String(index + 1), nombre: fila.nombre.trim(), duracion: Number(fila.duracion),
          predecesoras: [], metadatos: { origen: 'workspace_manual' },
        })),
      });
      onCreated(programa);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally { setBusy(false); }
  }

  return (
    <form onSubmit={guardar} className="m-4 space-y-3 rounded border border-zinc-600 p-4">
      <h3>Nuevo cronograma independiente</h3>
      <label className="block">Nombre
        <input required maxLength={500} value={nombre} disabled={busy}
          onChange={e => setNombre(e.target.value)} className="ml-2 bg-zinc-800 p-2" />
      </label>
      <label className="block">Inicio previsto
        <input required type="date" value={fecha} disabled={busy}
          onChange={e => setFecha(e.target.value)} className="ml-2 bg-zinc-800 p-2" />
      </label>
      {filas.map((fila, index) => (
        <div key={index} className="flex flex-wrap gap-2">
          <label>Actividad {index + 1}
            <input required maxLength={500} value={fila.nombre} disabled={busy}
              onChange={e => setFilas(prev => prev.map((item, i) => i === index ? { ...item, nombre: e.target.value } : item))}
              className="ml-2 bg-zinc-800 p-2" />
          </label>
          <label>Duración en días
            <input required type="number" min="0.01" step="any" value={fila.duracion} disabled={busy}
              onChange={e => setFilas(prev => prev.map((item, i) => i === index ? { ...item, duracion: e.target.value } : item))}
              className="ml-2 w-24 bg-zinc-800 p-2" />
          </label>
          <button type="button" disabled={busy || filas.length === 1}
            onClick={() => setFilas(prev => prev.filter((_, i) => i !== index))}>Quitar actividad</button>
        </div>
      ))}
      <p>Define las dependencias en el editor antes de calcular el cronograma. Las actividades sin dependencias pueden ejecutarse en paralelo.</p>
      {error && <p role="alert">{error}</p>}
      <button type="button" disabled={busy} className="mr-4 underline"
        onClick={() => setFilas(prev => [...prev, { nombre: '', duracion: '' }])}>Añadir actividad</button>
      <button disabled={busy || !nombre.trim() || filas.some(f => !f.nombre.trim())}
        className="rounded bg-zinc-700 p-2">{busy ? 'Guardando…' : 'Crear cronograma'}</button>
    </form>
  );
}
