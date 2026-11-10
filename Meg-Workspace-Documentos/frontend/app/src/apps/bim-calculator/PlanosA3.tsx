import { useEffect, useState, type FormEvent } from 'react';
import { megalodonClient } from '@/lib/api-client';
import type { SolicitudPlanoBIM } from '@/lib/megalodon-client';

const formatos = ['PDF', 'SVG', 'DXF'] as const;

const nombres = { PLAN: 'Planta', SECTION: 'Sección', ELEVATION: 'Alzado' } as const;
const direcciones: Record<'x+' | 'x-' | 'y+' | 'y-', [number, number, number]> = {
  'x+': [1, 0, 0], 'x-': [-1, 0, 0], 'y+': [0, 1, 0], 'y-': [0, -1, 0],
};

type Plano = Awaited<ReturnType<typeof megalodonClient.bim.listarPlanos>>[number];

function VistaPlano({ expedienteId, modeloId, plano }: {
  expedienteId: string; modeloId: string; plano: Plano;
}) {
  const [src, setSrc] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    let activo = true;
    let blobUrl: string | undefined;
    megalodonClient.bim.descargarPlano(expedienteId, modeloId, plano.id, 'SVG')
      .then(archivo => {
        if (!activo) return;
        if (archivo.blob) blobUrl = URL.createObjectURL(archivo.blob);
        setSrc(blobUrl ?? archivo.url ?? '');
      })
      .catch(err => {
        if (activo) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      activo = false;
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [expedienteId, modeloId, plano.id]);
  if (error) return <p role="alert">{error}</p>;
  if (!src) return <p role="status">Cargando vista previa…</p>;
  return <img src={src} alt={`Vista previa de ${plano.titulo}`}
    onError={() => setError('No se pudo mostrar la vista previa del plano.')}
    className="block max-h-80 max-w-full bg-white" />;
}

export default function PlanosA3({ expedienteId, modeloId, canWrite }: {
  expedienteId: string;
  modeloId: string;
  canWrite: boolean;
}) {
  const [abierto, setAbierto] = useState(false);
  const [planos, setPlanos] = useState<Plano[]>([]);
  const [vistaId, setVistaId] = useState('');
  const [titulo, setTitulo] = useState('');
  const [tipo, setTipo] = useState<SolicitudPlanoBIM['tipo']>('PLAN');
  const [elevacion, setElevacion] = useState('');
  const [eje, setEje] = useState<'X' | 'Y'>('X');
  const [coordenada, setCoordenada] = useState('');
  const [direccion, setDireccion] = useState<keyof typeof direcciones>('y-');
  const [mostrarOcultas, setMostrarOcultas] = useState(false);
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
    const nombre = titulo.trim();
    if (!nombre) return;
    let solicitud: SolicitudPlanoBIM;
    if (tipo === 'PLAN') {
      if (!elevacion.trim() || !Number.isFinite(Number(elevacion))) return;
      solicitud = { tipo, titulo: nombre, parametros: { elevacion_m: Number(elevacion) } };
    } else if (tipo === 'SECTION') {
      const posicion = Number(coordenada);
      if (!coordenada.trim() || !Number.isFinite(posicion)) return;
      solicitud = {
        tipo, titulo: nombre,
        parametros: {
          origen_m: eje === 'X' ? [posicion, 0, 0] : [0, posicion, 0],
          normal: direcciones[eje === 'X' ? 'x+' : 'y+'],
        },
      };
    } else {
      solicitud = {
        tipo, titulo: nombre,
        parametros: { direccion_vista: direcciones[direccion], mostrar_ocultas: mostrarOcultas },
      };
    }
    setOcupado(true);
    setError('');
    try {
      await megalodonClient.bim.generarPlano(expedienteId, modeloId, solicitud);
      setActualizacion(value => value + 1);
    } catch (err) {
      setError(String(err instanceof Error ? err.message : err));
    } finally {
      setOcupado(false);
    }
  }

  async function descargar(plano: Plano, formato: typeof formatos[number]) {
    try {
      const archivo = await megalodonClient.bim.descargarPlano(expedienteId, modeloId, plano.id, formato);
      const link = document.createElement('a');
      link.href = archivo.blob ? URL.createObjectURL(archivo.blob) : archivo.url!;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.download = `plano-${plano.id}.${formato.toLowerCase()}`;
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
      <label>Tipo de plano <select aria-label="Tipo de plano" value={tipo} onChange={event => setTipo(event.target.value as typeof tipo)}>
        {Object.entries(nombres).map(([valor, nombre]) => <option key={valor} value={valor}>{nombre}</option>)}
      </select></label>
      {tipo === 'PLAN' && <label>Elevación de corte (m)
        <input required type="number" step="any" value={elevacion} onChange={event => setElevacion(event.target.value)} />
      </label>}
      {tipo === 'SECTION' && <>
        <label>Eje de corte <select aria-label="Eje de corte" value={eje} onChange={event => setEje(event.target.value as typeof eje)}>
          <option value="X">X constante</option><option value="Y">Y constante</option>
        </select></label>
        <label>Coordenada de corte (m)
          <input required type="number" step="any" value={coordenada} onChange={event => setCoordenada(event.target.value)} />
        </label>
      </>}
      {tipo === 'ELEVATION' && <>
        <label>Lado de observación <select aria-label="Lado de observación" value={direccion}
          onChange={event => setDireccion(event.target.value as typeof direccion)}>
          <option value="x+">Desde +X</option><option value="x-">Desde −X</option>
          <option value="y+">Desde +Y</option><option value="y-">Desde −Y</option>
        </select></label>
        <label><input type="checkbox" checked={mostrarOcultas}
          onChange={event => setMostrarOcultas(event.target.checked)} /> Mostrar líneas ocultas</label>
      </>}
      <button type="submit" disabled={ocupado}>Generar {nombres[tipo].toLowerCase()} A3</button>
    </form>}
    <button type="button" onClick={() => { setError(''); setActualizacion(value => value + 1); }}>Actualizar planos</button>
    {error && <p role="alert">{error}</p>}
    <ul aria-label="Planos generados">
      {planos.map(plano => <li key={plano.id}>
        {plano.titulo} · {nombres[plano.tipo]} · {plano.estado}
        {plano.error && <span> · {plano.error}</span>}
        <small className="block">
          Revisión IFC: <time dateTime={plano.source_model_updated_at}>{plano.source_model_updated_at}</time>
          {plano.obsoleto && ' · El modelo tiene una revisión posterior'}
        </small>
        {plano.metadatos?.visibility_mode === 'occlusion_clipped_mesh_silhouette' && <small className="block">Alzado de siluetas. Los tramos ocultos se omiten.</small>}
        {plano.metadatos?.visibility_mode === 'occlusion_clipped_mesh_edges' && <small className="block">Alzado de contornos y pliegues. Los tramos ocultos se omiten.</small>}
        {plano.metadatos?.visibility_mode === 'mesh_edges_with_hidden_lines' && <small className="block">Los tramos ocultos se muestran con línea discontinua.</small>}
        {plano.estado === 'COMPLETADO' && <div className="space-x-2">
          {plano.formatos.includes('SVG') && <button type="button" aria-expanded={vistaId === plano.id}
            onClick={() => setVistaId(vistaId === plano.id ? '' : plano.id)}>
            {vistaId === plano.id ? 'Cerrar vista previa' : 'Ver plano'}
          </button>}
          {formatos.filter(formato => plano.formatos.includes(formato)).map(formato =>
            <button type="button" key={formato} onClick={() => void descargar(plano, formato)}>Descargar {formato}</button>
          )}
          {abierto && vistaId === plano.id && <VistaPlano expedienteId={expedienteId} modeloId={modeloId} plano={plano} />}
        </div>}
      </li>)}
    </ul>
  </details>;
}
