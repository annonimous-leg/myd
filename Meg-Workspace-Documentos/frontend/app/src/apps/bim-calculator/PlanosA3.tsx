import { useEffect, useState, type FormEvent } from 'react';
import { megalodonClient } from '@/lib/api-client';

type Plano = Awaited<ReturnType<typeof megalodonClient.bim.listarPlanos>>[number];

export default function PlanosA3({ expedienteId, modeloId, canWrite }: {
  expedienteId: string;
  modeloId: string;
  canWrite: boolean;
}) {
  const [abierto, setAbierto] = useState(false);
  const [planos, setPlanos] = useState<Plano[]>([]);
  const [titulo, setTitulo] = useState('');
  const [elevacion, setElevacion] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState('');
  const [actualizacion, setActualizacion] = useState(0);

  useEffect(() => {
    if (!abierto) return;
    let activo = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function cargar() {
      try {
        const lista = (await megalodonClient.bim.listarPlanos(expedienteId, modeloId))
          .filter(plano => plano.formatos.includes('PDF'));
        if (!activo) return;
        setPlanos(lista);
        if (lista.some(plano => plano.estado === 'PENDIENTE' || plano.estado === 'EN_PROCESO')) {
          timer = setTimeout(() => void cargar(), 3000);
        }
      } catch (err) {
        if (activo) setError(String(err instanceof Error ? err.message : err));
      }
    }
    void cargar();
    return () => {
      activo = false;
      clearTimeout(timer);
    };
  }, [abierto, expedienteId, modeloId, actualizacion]);

  async function generar(event: FormEvent) {
    event.preventDefault();
    if (!titulo.trim() || !elevacion.trim() || !Number.isFinite(Number(elevacion))) return;
    setOcupado(true);
    setError('');
    try {
      await megalodonClient.bim.generarPlantaPDF(expedienteId, modeloId, titulo.trim(), Number(elevacion));
      setActualizacion(value => value + 1);
    } catch (err) {
      setError(String(err instanceof Error ? err.message : err));
    } finally {
      setOcupado(false);
    }
  }

  async function descargar(plano: Plano) {
    try {
      const archivo = await megalodonClient.bim.descargarPlanoPDF(expedienteId, modeloId, plano.id);
      const link = document.createElement('a');
      link.href = archivo.blob ? URL.createObjectURL(archivo.blob) : archivo.url!;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.download = `plano-${plano.id}.pdf`;
      link.click();
      if (archivo.blob) setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    } catch (err) {
      setError(String(err instanceof Error ? err.message : err));
    }
  }

  return <details onToggle={event => setAbierto(event.currentTarget.open)} className="space-y-2">
    <summary className="cursor-pointer">Planos PDF A3</summary>
    {canWrite && <form onSubmit={generar} className="flex flex-wrap gap-2 items-end">
      <label>Título <input required maxLength={300} value={titulo} onChange={event => setTitulo(event.target.value)} /></label>
      <label>Elevación de corte (m) <input required type="number" step="any" value={elevacion} onChange={event => setElevacion(event.target.value)} /></label>
      <button type="submit" disabled={ocupado}>Generar planta A3</button>
    </form>}
    <button type="button" onClick={() => { setError(''); setActualizacion(value => value + 1); }}>Actualizar planos</button>
    {error && <p role="alert">{error}</p>}
    <ul aria-label="Planos generados">
      {planos.map(plano => <li key={plano.id}>
        {plano.titulo} · {plano.estado}
        {plano.error && <span> · {plano.error}</span>}
        {plano.estado === 'COMPLETADO' && <button type="button" onClick={() => void descargar(plano)}>Descargar PDF</button>}
      </li>)}
    </ul>
  </details>;
}
