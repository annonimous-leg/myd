/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { useState, useEffect, useRef } from 'react';
import PresupuestoPanel from './PresupuestoPanel';
import PlanosA3 from './PlanosA3';
import CronogramaBim from './CronogramaBim';
import CantidadesComplementarias, { faltantesDeMedicion, type CapturaCantidad } from './CantidadesComplementarias';
import { abrirModulo } from '@/lib/navigation';
import { useAuthStore } from '@/stores/useAuthStore';
import { permisosBim } from '@/lib/bim-permissions';
import { Calculator, Upload, Loader2, AlertCircle, FolderKanban, Box, FileWarning, ShieldAlert, CheckCircle2, AlertTriangle, Layers, Search, Link2 } from 'lucide-react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Bounds } from '@react-three/drei';
import { megalodonClient } from '@/lib/api-client';
import { useExpedienteStore } from '@/stores/useExpedienteStore';
import type { ModeloBIM, ElementoBIM, AnalisisClash, ClashResult, GeneracionBIM4D5D, CatalogoAPUOut, Presupuesto } from '@/lib/megalodon-client';

/* ------------------------------------------------------------------ */
/*  Modo IFC real -- conectado al motor BIM del backend (ifcopenshell)  */
/* ------------------------------------------------------------------ */

const FUENTE_LABEL: Record<string, string> = {
  QTO_IFC: 'del IFC',
  GEOMETRIA_CALCULADA: 'calculado (aprox.)',
  NO_DISPONIBLE: 'no disponible',
};

// Color por tipo de elemento -- antes todo salía gris plano, imposible
// distinguir muros de losas de columnas de un vistazo.
const COLOR_POR_TIPO: Record<string, string> = {
  IfcWall: '#c9a86c',
  IfcSlab: '#8899aa',
  IfcColumn: '#6c8ec9',
  IfcBeam: '#9e6cc9',
  IfcDoor: '#c96c6c',
  IfcWindow: '#6cc9c3',
  IfcRoof: '#c96c9e',
  IfcStair: '#c9c06c',
  IfcFooting: '#5a5a6e',
  IfcCovering: '#8ec96c',
  IfcRailing: '#c98e6c',
};
const COLOR_DEFAULT = '#8899aa';

function ElementoMesh({
  elemento, seleccionado, wireframe, onSelect, enClash = false,
}: {
  elemento: ElementoBIM;
  seleccionado: boolean;
  wireframe: boolean;
  onSelect: (el: ElementoBIM) => void;
  enClash?: boolean;
}) {
  if (!elemento.malla_vertices?.length || !elemento.malla_caras?.length) return null;
  const color = seleccionado
    ? '#ffd166'
    : enClash
      ? '#ef4444'
      : (COLOR_POR_TIPO[elemento.tipo] || COLOR_DEFAULT);
  return (
    <mesh
      onClick={(e) => { e.stopPropagation(); onSelect(elemento); }}
      onPointerOver={(e) => { e.stopPropagation(); document.body.style.cursor = 'pointer'; }}
      onPointerOut={() => { document.body.style.cursor = 'auto'; }}
    >
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          args={[new Float32Array(elemento.malla_vertices), 3]}
        />
        <bufferAttribute
          attach="index"
          args={[new Uint32Array(elemento.malla_caras), 1]}
        />
      </bufferGeometry>
      <meshStandardMaterial
        color={color}
        side={2}
        wireframe={wireframe}
        emissive={seleccionado ? '#ffd166' : enClash ? '#b91c1c' : '#000000'}
        emissiveIntensity={seleccionado ? 0.3 : enClash ? 0.2 : 0}
      />
    </mesh>
  );
}

function IFCPanel() {
  const requestId = useRef(0);
  const role = useAuthStore(s => s.user?.role);
  const { canWrite } = permisosBim(role);
  const [modelos, setModelos] = useState<ModeloBIM[]>([]);
  const [nuevoPresupuestoId, setNuevoPresupuestoId] = useState('');
  const [trabajos, setTrabajos] = useState<Awaited<ReturnType<typeof megalodonClient.bim.listarTrabajos>>>([]);
  const expedienteActivo = useExpedienteStore((s) => s.expedienteActivo());
  const [modelo, setModelo] = useState<ModeloBIM | null>(null);
  const [elementos, setElementos] = useState<ElementoBIM[]>([]);
  const [procesando, setProcesando] = useState(false);
  const [error, setError] = useState('');
  const [generandoPresupuesto, setGenerandoPresupuesto] = useState(false);
  const [mensajePresupuesto, setMensajePresupuesto] = useState('');

  // Controles del visor -- antes no había filtro de nivel, ni vista 2D,
  // ni selección de elemento individual.
  const [nivelFiltro, setNivelFiltro] = useState<string>('__todos__');
  const [vista, setVista] = useState<'3d' | '2d'>('3d');
  const [wireframe, setWireframe] = useState(false);
  const [seleccionado, setSeleccionado] = useState<ElementoBIM | null>(null);
  // FIX P1 auditoría BIM 2026-09-14 (Caso 2 "mapear-partidas"): el backend
  // ya tenía POST /mapear-partidas y el cliente ya tenía
  // megalodonClient.bim.mapearAPartidas() -- ninguna pantalla lo llamaba.
  // La única forma de conectar BIM->presupuesto era generarPresupuesto()
  // (crea un presupuesto NUEVO agrupando por tipo IFC); no había forma de
  // vincular un elemento puntual a una partida de un presupuesto YA
  // EXISTENTE (ej. el que se armó desde la licitación real) para
  // trazabilidad/verificación. Esto cierra ese hueco para el elemento
  // seleccionado en el visor.
  const [presupuestosDisponibles, setPresupuestosDisponibles] = useState<Presupuesto[]>([]);
  const [presupuestoVinculoId, setPresupuestoVinculoId] = useState('');
  const [partidaVinculoId, setPartidaVinculoId] = useState('');
  const [vinculando, setVinculando] = useState(false);
  const [mensajeVinculo, setMensajeVinculo] = useState('');
  // FIX P1 auditoría BIM 2026-09-14 (Caso 1 "factores económicos"): el
  // backend acepta factor_indirecto/factor_utilidad/factor_impuesto con
  // defaults 15/10/16%, pero ningún flujo de generación de presupuesto
  // desde BIM en esta app dejaba editarlos -- siempre se generaba con el
  // default del backend, sin que el usuario pudiera saber siquiera que
  // existía esa perilla.
  const [factorIndirecto, setFactorIndirecto] = useState(0);
  const [factorFinanciamiento, setFactorFinanciamiento] = useState(0);
  const [factorUtilidad, setFactorUtilidad] = useState(0);
  const [factorCargosAdicionales, setFactorCargosAdicionales] = useState(0);
  const [factorImpuesto, setFactorImpuesto] = useState(0);
  const [referenciaParametros, setReferenciaParametros] = useState('');
  const [capturasCantidad, setCapturasCantidad] = useState<Record<string,CapturaCantidad>>({});
  useEffect(() => { setCapturasCantidad({}); }, [modelo?.id]);

  useEffect(() => {
    if (!expedienteActivo) { setPresupuestosDisponibles([]); return; }
    megalodonClient.presupuestos.list(expedienteActivo.id)
      .then(setPresupuestosDisponibles)
      .catch(() => setPresupuestosDisponibles([])); // sin presupuestos todavía -- no es un error que deba bloquear el visor
  }, [expedienteActivo?.id]);

  const partidasDelPresupuestoSeleccionado =
    presupuestosDisponibles.find((p) => p.id === presupuestoVinculoId)?.partidas ?? [];

  const handleVincularPartida = async () => {
    if (!expedienteActivo || !modelo || !seleccionado || !partidaVinculoId) return;
    setVinculando(true);
    setMensajeVinculo('');
    try {
      await megalodonClient.bim.mapearAPartidas(expedienteActivo.id, modelo.id, [
        { elemento_id: seleccionado.id, partida_id: partidaVinculoId },
      ]);
      setElementos((prev) => prev.map((e) => (e.id === seleccionado.id ? { ...e, partida_id: partidaVinculoId } : e)));
      setSeleccionado((prev) => (prev ? { ...prev, partida_id: partidaVinculoId } : prev));
      setMensajeVinculo('Vinculado.');
    } catch (e: any) {
      setMensajeVinculo(e?.message || 'No se pudo vincular el elemento a la partida.');
    } finally {
      setVinculando(false);
    }
  };

  const cargarModelo = async (selected: ModeloBIM) => {
    if (!expedienteActivo) return;
    const current = ++requestId.current;
    setProcesando(true); setError(''); setModelo(selected); setElementos([]);
    setSeleccionado(null); setNivelFiltro('__todos__'); setGeneracion4D(null);
    setMapeoCatalogo({}); setMapeoCatalogoElementos({});
    setResultadosCatalogo({}); setBusquedaCatalogo({}); setErroresCatalogo({});
    setAnalisis(null); setClashes([]); setClashesResaltados(new Set()); setTrabajos([]);
    try {
      const ready = ['COMPLETADO', 'ERROR'].includes(selected.estado_procesamiento)
        ? selected : await megalodonClient.bim.esperarProcesamiento(expedienteActivo.id, selected.id);
      if (current !== requestId.current) return;
      setModelo(ready);
      if (ready.estado_procesamiento !== 'COMPLETADO') {
        setError(ready.error_procesamiento || 'No se pudo procesar este archivo. Revisa su contenido y vuelve a intentar.');
        return;
      }
      const all: ElementoBIM[] = [];
      while (all.length < 20000) {
        const page = await megalodonClient.bim.listarElementos(expedienteActivo.id, ready.id,
          { incluirMalla:true, limit:500, offset:all.length });
        if (current !== requestId.current) return;
        all.push(...page);
        if (page.length < 500) break;
      }
      setElementos(all);
      if (ready.num_elementos > all.length) setError(`Se muestran ${all.length} de ${ready.num_elementos} elementos. El presupuesto utiliza el modelo completo.`);
      const history = await megalodonClient.bim.listarGeneraciones(expedienteActivo.id, ready.id);
      if (current !== requestId.current) return;
      const generation = history[0];
      setGeneracion4D(generation || null);
      if (generation && !['COMPLETADO','ERROR'].includes(generation.estado)) {
        setGenerando4D(true);
        const final = await megalodonClient.bim.esperarGeneracion4D5D(expedienteActivo.id, generation.id);
        if (current === requestId.current) setGeneracion4D(final);
      }
    } catch (e) {
      if (current === requestId.current) setError(e instanceof Error ? e.message : 'No se pudo abrir el modelo');
    } finally {
      if (current === requestId.current) { setProcesando(false); setGenerando4D(false); }
    }
  };

  const handleArchivo = async (file: File) => {
    if (!expedienteActivo || !canWrite) return;
    setError(''); setProcesando(true);
    try {
      const uploaded = await megalodonClient.bim.subirModelo(expedienteActivo.id, file,
        { nombre:file.name.replace(/\.ifc$/i, ''), extraerMalla:true });
      setModelos(previous => [uploaded, ...previous]);
      await cargarModelo(uploaded);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo subir el archivo');
      setProcesando(false);
    }
  };

  const handleGenerarPresupuesto = async () => {
    if (!expedienteActivo || !modelo) return;
    if (!referenciaParametros.trim()) {
      setMensajePresupuesto('Indica la fuente o referencia de los parámetros de costeo.');
      return;
    }
    setGenerandoPresupuesto(true);
    setMensajePresupuesto('');
    try {
      const presupuesto = await megalodonClient.bim.generarPresupuesto(expedienteActivo.id, modelo.id, {
        nombre: `Presupuesto desde ${modelo.nombre}`,
        parametros_costeo: {
          factor_indirecto: factorIndirecto, factor_financiamiento: factorFinanciamiento,
          factor_utilidad: factorUtilidad, factor_cargos_adicionales: factorCargosAdicionales,
          factor_impuesto: factorImpuesto, factor_riesgo: 0,
          fuente: 'CAPTURA_USUARIO', referencia: referenciaParametros.trim(),
        },
      });
      setNuevoPresupuestoId(presupuesto.id);
      setPresupuestosDisponibles(previous => [presupuesto, ...previous]);
      setMensajePresupuesto(`Presupuesto ${presupuesto.identificador} creado (solo cantidades -- falta capturar precios unitarios).`);
    } catch (e) {
      setMensajePresupuesto(e instanceof Error ? e.message : 'No se pudo generar el presupuesto');
    } finally {
      setGenerandoPresupuesto(false);
    }
  };

  const [tabDerecho, setTabDerecho] = useState<'resumen' | 'clash' | 'presupuesto5d' | 'cronograma4d'>('resumen');
  const [corriendo, setCorriendo] = useState(false);
  const [analisis, setAnalisis] = useState<AnalisisClash | null>(null);
  const [clashes, setClashes] = useState<ClashResult[]>([]);
  const [errorClash, setErrorClash] = useState('');
  const [toleranciaM, setToleranciaM] = useState(0);
  const [clashesResaltados, setClashesResaltados] = useState<Set<string>>(new Set());

  // --- 5D: mapeo de tipos a catálogo real (precio real, no inventado) ---
  const [busquedaCatalogo, setBusquedaCatalogo] = useState<Record<string, string>>({});
  const [resultadosCatalogo, setResultadosCatalogo] = useState<Record<string, CatalogoAPUOut[]>>({});
  const [erroresCatalogo, setErroresCatalogo] = useState<Record<string, string>>({});
  const [buscandoCatalogo, setBuscandoCatalogo] = useState<string | null>(null);
  const [mapeoCatalogo, setMapeoCatalogo] = useState<Record<string, CatalogoAPUOut>>({});
  const [mapeoCatalogoElementos, setMapeoCatalogoElementos] = useState<Record<string, CatalogoAPUOut>>({});
  const [generandoPresupuestoReal, setGenerandoPresupuestoReal] = useState(false);
  const [mensajePresupuestoReal, setMensajePresupuestoReal] = useState('');

  // --- 4D: zonas de trabajo y generación de cronograma ---
  const [zonaInput, setZonaInput] = useState('');
  const [asignandoZona, setAsignandoZona] = useState(false);
  const [mensajeZona, setMensajeZona] = useState('');
  const [fechaInicio4D, setFechaInicio4D] = useState('');
  const [diasPorDefecto4D, setDiasPorDefecto4D] = useState(5);
  const [generando4D, setGenerando4D] = useState(false);
  const [generacion4D, setGeneracion4D] = useState<GeneracionBIM4D5D | null>(null);
  const [error4D, setError4D] = useState('');

  const handleCorrerClash = async () => {
    if (!expedienteActivo || !modelo) return;
    setCorriendo(true);
    setErrorClash('');
    setAnalisis(null);
    setClashes([]);
    try {
      const a = await megalodonClient.bim.correrClashDetection(
        expedienteActivo.id, modelo.id,
        { toleranciaM }
      );
      setAnalisis(a);
      if (a.num_clashes_duros + a.num_clashes_blandos > 0) {
        const rs = await megalodonClient.bim.listarResultadosClash(
          expedienteActivo.id, modelo.id, a.id, { limit: 200 }
        );
        setClashes(rs);
        // Resaltar en el visor los elementos con clash
        const ids = new Set<string>();
        rs.forEach(r => { ids.add(r.elemento_a_id); ids.add(r.elemento_b_id); });
        setClashesResaltados(ids);
      }
    } catch (e) {
      setErrorClash(e instanceof Error ? e.message : 'Error al correr clash detection');
    } finally {
      setCorriendo(false);
    }
  };

  const handleMarcarEstado = async (resultadoId: string, estado: 'REVISADO' | 'RESUELTO' | 'IGNORADO') => {
    if (!expedienteActivo) return;
    try {
      const actualizado = await megalodonClient.bim.actualizarEstadoClash(
        expedienteActivo.id, resultadoId, estado
      );
      setClashes(prev => prev.map(c => c.id === resultadoId ? actualizado : c));
    } catch { /* silencioso */ }
  };

  // --- 5D: buscar en el catálogo real y mapear un tipo a un concepto ---
  const handleBuscarCatalogo = async (tipo: string) => {
    const q = busquedaCatalogo[tipo]?.trim();
    if (!q) return;
    setBuscandoCatalogo(tipo);
    setErroresCatalogo(prev => ({ ...prev, [tipo]: '' }));
    try {
      const { items } = await megalodonClient.catalogoApu.listar({ q, limit: 8 });
      setResultadosCatalogo((prev) => ({ ...prev, [tipo]: items }));
    } catch (e) {
      setResultadosCatalogo((prev) => ({ ...prev, [tipo]: [] }));
      setErroresCatalogo(prev => ({ ...prev, [tipo]: e instanceof Error ? e.message : 'No se pudo consultar el catálogo. Intenta buscar de nuevo.' }));
    } finally {
      setBuscandoCatalogo(null);
    }
  };

  const handleGenerarPresupuestoReal = async () => {
    if (!expedienteActivo || !modelo) return;
    if (!referenciaParametros.trim()) {
      setMensajePresupuestoReal('Indica la fuente o referencia de los parámetros de costeo.');
      return;
    }
    setGenerandoPresupuestoReal(true);
    setMensajePresupuestoReal('');
    try {
      const mapeoPayload: Record<string, string> = {};
      for (const [tipo, concepto] of Object.entries(mapeoCatalogo)) mapeoPayload[tipo] = concepto.id;
      const mapeoElementosPayload: Record<string, string> = {};
      for (const [elementoId, concepto] of Object.entries(mapeoCatalogoElementos)) {
        mapeoElementosPayload[elementoId] = concepto.id;
      }
      const cantidadesComplementarias = faltantesDeMedicion(
        elementos,
        Object.fromEntries(Object.entries(mapeoCatalogo).map(([tipo,concepto])=>[tipo,concepto.unidad])),
        Object.fromEntries(Object.entries(mapeoCatalogoElementos).map(([id,concepto])=>[id,concepto.unidad])),
      )
        .flatMap(({elemento,unidad}) => {
          const capture = capturasCantidad[elemento.id];
          if (!capture || capture.unidad !== unidad || (!capture.cantidad && !capture.referencia)) return [];
          const quantity = Number(capture.cantidad);
          if (!Number.isFinite(quantity) || quantity <= 0 || capture.referencia.trim().length < 5)
            throw new Error('Completa la cantidad y una referencia de al menos cinco caracteres en cada medición capturada.');
          return [{elemento_id:elemento.id,unidad,cantidad:quantity,referencia:capture.referencia.trim()}];
        });

      const presupuesto = await megalodonClient.bim.generarPresupuesto(expedienteActivo.id, modelo.id, {
        nombre: `Presupuesto desde ${modelo.nombre}`,
        mapeo_catalogo: Object.keys(mapeoPayload).length > 0 ? mapeoPayload : undefined,
        mapeo_elementos: Object.keys(mapeoElementosPayload).length > 0 ? mapeoElementosPayload : undefined,
        cantidades_complementarias: cantidadesComplementarias,
        parametros_costeo: {
          factor_indirecto: factorIndirecto, factor_financiamiento: factorFinanciamiento,
          factor_utilidad: factorUtilidad, factor_cargos_adicionales: factorCargosAdicionales,
          factor_impuesto: factorImpuesto, factor_riesgo: 0,
          fuente: 'CAPTURA_USUARIO', referencia: referenciaParametros.trim(),
        },
      });
      setNuevoPresupuestoId(presupuesto.id);
      setPresupuestosDisponibles(previous => [presupuesto, ...previous]);
      const tiposMapeados = Object.keys(mapeoPayload).length;
      const elementosMapeados = Object.keys(mapeoElementosPayload).length;
      setMensajePresupuestoReal(
        tiposMapeados + elementosMapeados > 0
          ? `Presupuesto ${presupuesto.identificador} creado -- ${tiposMapeados} tipo(s) base y ${elementosMapeados} elemento(s) con APU específico.`
          : `Presupuesto ${presupuesto.identificador} creado (solo cantidades -- vincula tipos o elementos a conceptos reales para costeo 5D).`
      );
    } catch (e) {
      setMensajePresupuestoReal(e instanceof Error ? e.message : 'No se pudo generar el presupuesto');
    } finally {
      setGenerandoPresupuestoReal(false);
    }
  };

  // --- 4D: asignar zona de trabajo a los elementos del nivel filtrado ---
  const handleAsignarZona = async () => {
    if (!expedienteActivo || !modelo || !zonaInput.trim()) return;
    setAsignandoZona(true);
    setMensajeZona('');
    try {
      const objetivo = nivelFiltro === '__todos__' ? elementos : elementos.filter((el) => (el.nivel || 'Sin nivel') === nivelFiltro);
      const asignaciones = objetivo.map((el) => ({ elemento_id: el.id, zona_4d: zonaInput.trim() }));
      const { elementos_actualizados } = await megalodonClient.bim.asignarZonas4d(expedienteActivo.id, modelo.id, asignaciones);
      setElementos((prev) => prev.map((el) => (objetivo.some((o) => o.id === el.id) ? { ...el, zona_4d: zonaInput.trim() } : el)));
      setMensajeZona(`Zona "${zonaInput.trim()}" asignada a ${elementos_actualizados} elemento(s).`);
    } catch (e) {
      setMensajeZona(e instanceof Error ? e.message : 'No se pudo asignar la zona');
    } finally {
      setAsignandoZona(false);
    }
  };

  const handleGenerar4D = async () => {
    if (!expedienteActivo || !modelo || !fechaInicio4D) return;
    setGenerando4D(true);
    setError4D('');
    setGeneracion4D(null);
    try {
      const gen = await megalodonClient.bim.generar4D5D(expedienteActivo.id, modelo.id, {
        fecha_inicio: new Date(fechaInicio4D).toISOString(),
        dias_por_defecto: diasPorDefecto4D,
      });
      setGeneracion4D(gen);
      const final = await megalodonClient.bim.esperarGeneracion4D5D(expedienteActivo.id, gen.id);
      setGeneracion4D(final);
      if (final.estado === 'ERROR') setError4D(final.error || 'La generación 4D falló');
    } catch (e) {
      setError4D(e instanceof Error ? e.message : 'No se pudo generar el cronograma 4D');
    } finally {
      setGenerando4D(false);
    }
  };

  useEffect(() => {
    let active = true;
    if (!expedienteActivo) return;
    megalodonClient.bim.listarModelos(expedienteActivo.id).then(list => {
      if (!active) return;
      setModelos(list);
      if (list[0]) void cargarModelo(list[0]);
    }).catch(e => { if (active) setError(e instanceof Error ? e.message : 'No se pudieron cargar los modelos'); });
    return () => { active = false; requestId.current++; };
  }, [expedienteActivo?.id]);

  useEffect(() => {
    if (!expedienteActivo || !modelo) return;
    let active = true;
    const load = () => megalodonClient.bim.listarTrabajos(expedienteActivo.id, modelo.id)
      .then(list => { if (active) setTrabajos(list); })
      .catch(e => { if (active) setError(e instanceof Error ? e.message : 'No se pudo consultar el procesamiento'); });
    void load();
    const interval = setInterval(load, 5000);
    return () => { active = false; clearInterval(interval); };
  }, [expedienteActivo?.id, modelo?.id]);

  const reintentar = async (id: string) => {
    if (!expedienteActivo || !modelo || !canWrite) return;
    try {
      await megalodonClient.bim.reintentarTrabajo(expedienteActivo.id, modelo.id, id);
      await cargarModelo(await megalodonClient.bim.obtenerModelo(expedienteActivo.id, modelo.id));
    } catch (e) { setError(e instanceof Error ? e.message : 'No se pudo reintentar'); }
  };

  if (!expedienteActivo) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-2 text-center px-6" style={{ color: 'var(--text-muted)' }}>
        <FolderKanban size={32} style={{ opacity: 0.5 }} />
        <p className="text-sm">No hay ningún expediente activo.</p>
        <p className="text-xs">Primero elige la obra en la que vas a trabajar.</p>
        <button onClick={() => abrirModulo('proyectos')} className="px-4 py-2 rounded bg-(--accent-gold) text-(--void)">Elegir o crear obra</button>
      </div>
    );
  }

  // Filtro por nivel: se filtra en el cliente sobre lo ya descargado
  // (incluida la malla) en vez de volver a pedir al backend -- la malla
  // ya pesa, no tiene caso re-descargarla cada vez que cambias de piso.
  const elementosVisibles = nivelFiltro === '__todos__'
    ? elementos
    : elementos.filter((el) => (el.nivel || 'Sin nivel') === nivelFiltro);

  const resumenPorTipo = elementosVisibles.reduce<Record<string, { cantidad: number; volumen: number; area: number }>>((acc, el) => {
    const r = acc[el.tipo] || { cantidad: 0, volumen: 0, area: 0 };
    r.cantidad += 1;
    r.volumen += el.volumen || 0;
    r.area += el.area || 0;
    acc[el.tipo] = r;
    return acc;
  }, {});

  // 5D: el mapeo por tipo aplica al modelo completo. Un override por
  // elemento seleccionado gana sobre ese atajo para soportar especificaciones
  // y materiales heterogéneos dentro del mismo IfcType.
  const tiposDelModelo = Array.from(new Set(elementos.map((el) => el.tipo))).sort();
  const selectedElementSearchKey = seleccionado ? 'elemento:' + seleccionado.id : null;

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2 gap-2" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
          <FolderKanban size={12} style={{ color: 'var(--accent-gold)' }} />
          Expediente activo: <span style={{ color: 'var(--text-primary)' }}>{expedienteActivo.titulo}</span>
        </div>
        <label className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium cursor-pointer transition-colors"
          style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}>
          {procesando ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
          {procesando ? 'Procesando...' : 'Subir IFC'}
          <input
            aria-label="Subir archivo IFC"
            type="file"
            accept=".ifc"
            className="hidden"
            disabled={procesando || !canWrite}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) handleArchivo(f); }}
          />
        </label>
      </div>

      <div className="shrink-0 p-3 space-y-2 border-b border-(--border-subtle) text-xs">
        <p className="text-(--text-secondary)">Sube o abre un modelo, revisa sus cantidades y continúa con el presupuesto y el cronograma.</p>
        {!!modelos.length && <label className="flex items-center gap-2">Modelo de esta obra
          <select aria-label="Modelo de esta obra" value={modelo?.id || ''} disabled={procesando}
            onChange={e => { const item = modelos.find(m => m.id === e.target.value); if (item) void cargarModelo(item); }}
            className="min-w-0 flex-1 p-2 rounded bg-(--surface-elevated)">
            <option value="" disabled>Elegir modelo</option>
            {modelos.map(m => <option key={m.id} value={m.id}>{m.nombre}</option>)}
          </select>
          <button className="p-2 border rounded border-(--border-subtle)" disabled={procesando || !modelo}
            onClick={() => modelo && void megalodonClient.bim.obtenerModelo(expedienteActivo.id, modelo.id).then(cargarModelo).catch(e => setError(e.message))}>Actualizar</button>
        </label>}
        <nav aria-label="Pasos de trabajo BIM" className="flex flex-wrap gap-2">
          <button className="p-2 rounded bg-(--surface-elevated)" disabled={!elementos.length} onClick={() => setTabDerecho('resumen')}>1. Revisar cantidades</button>
          <button className="p-2 rounded bg-(--surface-elevated)" disabled={!elementos.length} onClick={() => setTabDerecho('presupuesto5d')}>2. Preparar presupuesto</button>
          <button className="p-2 rounded bg-(--surface-elevated)" disabled={!elementos.length} onClick={() => setTabDerecho('cronograma4d')}>3. Crear cronograma</button>
        </nav>
        {modelo?.estado_procesamiento === 'COMPLETADO' &&
          <PlanosA3 key={modelo.id} expedienteId={expedienteActivo.id} modeloId={modelo.id} canWrite={canWrite} />}
        {procesando && <p role="status">Preparando el modelo… Puedes salir y volver: el trabajo seguirá guardado.</p>}
        {modelo?.estado_procesamiento === 'ERROR' && canWrite && !trabajos.some(j => j.tipo === 'BIM_IFC') &&
          <button className="p-2 border rounded border-(--border-subtle)" onClick={() =>
            void megalodonClient.bim.reprocesarModelo(expedienteActivo.id, modelo.id).then(cargarModelo).catch(e => setError(e.message))}>
            Volver a procesar todos los elementos y su geometría
          </button>}
        {!canWrite && <p>Tu cuenta permite consultar esta obra. Un técnico puede cargar o modificar el modelo.</p>}
        {trabajos.filter(j => j.estado !== 'COMPLETADO').map(j => <div key={j.id} className="flex gap-2 items-center" role="status">
          <span>{j.tipo === 'BIM_IFC' ? 'Modelo' : j.tipo === 'BIM_4D' ? 'Cronograma' : 'Interferencias'}: {j.estado === 'ERROR' ? 'Requiere atención' : 'En preparación'}. {j.mensaje || 'Continuará automáticamente.'}</span>
          {j.estado === 'ERROR' && canWrite && <button className="p-2 border rounded border-(--border-subtle)" onClick={() => void reintentar(j.id)}>Reintentar trabajo</button>}
        </div>)}
      </div>

      {error && (
        <div className="flex items-center gap-2 px-3 py-2 text-xs" style={{ color: 'var(--danger)' }}>
          <AlertCircle size={14} /> {error}
        </div>
      )}

      {!modelo && !procesando && !error && (
        <div className="flex-1 flex flex-col items-center justify-center gap-2 text-center px-6" style={{ color: 'var(--text-muted)' }}>
          <Box size={32} style={{ opacity: 0.5 }} />
          <p className="text-sm">Sube un archivo .ifc para cuantificar y ver el modelo en 3D.</p>
        </div>
      )}

      {modelo && elementos.length > 0 && (
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Barra de controles del visor */}
          <div className="flex items-center gap-2 px-3 py-1.5 flex-wrap" style={{ borderBottom: '1px solid var(--border-subtle)', background: 'var(--surface)' }}>
            {modelo.niveles && modelo.niveles.length > 0 && (
              <select
                value={nivelFiltro}
                onChange={(e) => { setNivelFiltro(e.target.value); setSeleccionado(null); }}
                className="text-[11px] rounded px-2 py-1"
                style={{ background: 'var(--surface-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
              >
                <option value="__todos__">Todos los niveles</option>
                {modelo.niveles.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            )}

            <div className="flex rounded-md overflow-hidden" style={{ border: '1px solid var(--border-subtle)' }}>
              {(['3d', '2d'] as const).map((v) => (
                <button
                  key={v}
                  onClick={() => setVista(v)}
                  className="px-2 py-1 text-[11px] font-medium transition-colors"
                  style={{
                    background: vista === v ? 'var(--accent-gold)' : 'transparent',
                    color: vista === v ? 'var(--void)' : 'var(--text-secondary)',
                  }}
                >
                  {v === '3d' ? 'Vista 3D' : 'Planta (2D)'}
                </button>
              ))}
            </div>

            <button
              onClick={() => setWireframe(!wireframe)}
              className="flex items-center gap-1 px-2 py-1 rounded text-[11px] transition-colors"
              style={{
                background: wireframe ? 'var(--accent-gold)' : 'var(--surface-elevated)',
                color: wireframe ? 'var(--void)' : 'var(--text-secondary)',
                border: '1px solid var(--border-subtle)',
              }}
            >
              Alambre
            </button>

            <span className="text-[10px] ml-auto" style={{ color: 'var(--text-muted)' }}>
              {elementosVisibles.length} de {elementos.length} elementos
            </span>
          </div>

          <div className="flex-1 flex flex-col lg:flex-row overflow-y-auto lg:overflow-hidden">
            <div className="w-full lg:w-1/2 h-[340px] lg:h-full shrink-0 relative" style={{ background: '#05050a' }}>
              {/* key={vista} fuerza remount de Canvas al cambiar de
                  proyección -- cambiar de perspectiva a ortográfica en la
                  misma cámara da resultados raros con Bounds/fit. */}
              <Canvas key={vista} orthographic={vista === '2d'} camera={vista === '2d' ? { position: [0, 100, 0], zoom: 8 } : { position: [10, 10, 10], fov: 50 }}>
                <ambientLight intensity={0.7} />
                <directionalLight position={[10, 15, 10]} intensity={0.8} />
                <Bounds fit clip observe margin={1.3}>
                  {elementosVisibles.map((el) => (
                    <ElementoMesh
                      key={el.id}
                      elemento={el}
                      seleccionado={seleccionado?.id === el.id}
                      wireframe={wireframe}
                      onSelect={setSeleccionado}
                      enClash={clashesResaltados.has(el.id)}
                    />
                  ))}
                </Bounds>
                <OrbitControls enableRotate={vista === '3d'} />
                {vista === '3d' && <gridHelper args={[50, 50]} />}
              </Canvas>

              {seleccionado && (
                <div className="absolute bottom-2 left-2 right-2 rounded-md p-2 text-[11px]"
                  style={{ background: 'rgba(10,10,15,0.9)', border: '1px solid var(--border-subtle)', color: 'var(--text-primary)' }}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-semibold">{seleccionado.nombre || seleccionado.tipo}</span>
                    <button onClick={() => setSeleccionado(null)} style={{ color: 'var(--text-muted)' }}>✕</button>
                  </div>
                  <div style={{ color: 'var(--text-muted)' }}>
                    {seleccionado.tipo}{seleccionado.nivel ? ` · ${seleccionado.nivel}` : ''}
                  </div>
                  <div className="flex gap-3 mt-1">
                    {seleccionado.volumen != null && <span>Vol: {seleccionado.volumen.toFixed(3)} m³</span>}
                    {seleccionado.area != null && <span>Área: {seleccionado.area.toFixed(2)} m²</span>}
                  </div>
                  <div className="text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>
                    Volumen {FUENTE_LABEL[seleccionado.fuente_volumen]} · Área {FUENTE_LABEL[seleccionado.fuente_area]}
                  </div>
                  {/* FIX P1 auditoría BIM 2026-09-14 (mapear-partidas): antes
                      no había ninguna forma de vincular este elemento a una
                      partida de un presupuesto ya existente -- solo se podía
                      generar un presupuesto nuevo agrupado por tipo IFC. */}
                  <div className="mt-2 pt-2" style={{ borderTop: '1px solid var(--border-subtle)' }}>
                    {seleccionado.partida_id ? (
                      <div className="flex items-center gap-1" style={{ color: 'var(--success, #4ade80)' }}>
                        <Link2 size={10} /> Vinculado a una partida
                      </div>
                    ) : presupuestosDisponibles.length === 0 ? (
                      <div style={{ color: 'var(--text-muted)' }}>Sin presupuestos en este expediente todavía.</div>
                    ) : (
                      <div className="flex flex-col gap-1">
                        <select
                          value={presupuestoVinculoId}
                          onChange={(e) => { setPresupuestoVinculoId(e.target.value); setPartidaVinculoId(''); }}
                          className="rounded px-1 py-0.5 text-[10px]"
                          style={{ background: 'var(--surface-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                        >
                          <option value="">Presupuesto...</option>
                          {presupuestosDisponibles.map((p) => (
                            <option key={p.id} value={p.id}>{p.identificador} · {p.nombre}</option>
                          ))}
                        </select>
                        {presupuestoVinculoId && (
                          <div className="flex gap-1">
                            <select
                              value={partidaVinculoId}
                              onChange={(e) => setPartidaVinculoId(e.target.value)}
                              className="flex-1 rounded px-1 py-0.5 text-[10px]"
                              style={{ background: 'var(--surface-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                            >
                              <option value="">Partida...</option>
                              {partidasDelPresupuestoSeleccionado.map((partida) => (
                                <option key={partida.id} value={partida.id}>{partida.numero} · {partida.descripcion}</option>
                              ))}
                            </select>
                            <button
                              onClick={handleVincularPartida}
                              disabled={!canWrite || !partidaVinculoId || vinculando}
                              className="px-2 py-0.5 rounded text-[10px] font-medium"
                              style={{ background: 'var(--accent-gold)', color: '#000' }}
                            >
                              {vinculando ? <Loader2 size={10} className="animate-spin" /> : 'Vincular'}
                            </button>
                          </div>
                        )}
                        {mensajeVinculo && <div style={{ color: 'var(--text-muted)' }}>{mensajeVinculo}</div>}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            <div className="w-full lg:w-1/2 min-h-[400px] lg:min-h-0 lg:h-full flex flex-col overflow-hidden">
              {/* Tabs panel derecho */}
              <div className="flex shrink-0" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                {(['resumen', 'clash', 'presupuesto5d', 'cronograma4d'] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => setTabDerecho(t)}
                    className="flex items-center gap-1 px-3 py-2 text-[11px] font-medium transition-colors"
                    style={{
                      borderBottom: tabDerecho === t ? '2px solid var(--accent-gold)' : '2px solid transparent',
                      color: tabDerecho === t ? 'var(--text-primary)' : 'var(--text-muted)',
                    }}
                  >
                    {t === 'resumen' && <><Calculator size={11} /> Resumen</>}
                    {t === 'clash' && <><ShieldAlert size={11} /> Interferencias {analisis && analisis.num_clashes_duros + analisis.num_clashes_blandos > 0 && <span className="ml-1 px-1 rounded text-[9px]" style={{ background: 'var(--danger)', color: '#fff' }}>{analisis.num_clashes_duros + analisis.num_clashes_blandos}</span>}</>}
                    {t === 'presupuesto5d' && <><Link2 size={11} /> Presupuesto</>}
                    {t === 'cronograma4d' && <><Layers size={11} /> Cronograma</>}
                  </button>
                ))}
              </div>

              {/* Tab Resumen */}
              {tabDerecho === 'resumen' && (
                <div className="flex-1 overflow-y-auto p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>
                      {elementosVisibles.length} elementos
                    </span>
                    <button
                      onClick={handleGenerarPresupuesto}
                      disabled={!canWrite || generandoPresupuesto || !referenciaParametros.trim()}
                      className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors"
                      style={{ background: 'var(--surface-elevated)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}
                    >
                      {generandoPresupuesto ? <Loader2 size={11} className="animate-spin" /> : <Calculator size={11} />}
                      Generar presupuesto
                    </button>
                  </div>
                  <div className="grid grid-cols-2 lg:grid-cols-6 gap-1.5 mb-2 text-[10px]" style={{ color: 'var(--text-muted)' }}>
                    {[
                      ['Indirectos %', factorIndirecto, setFactorIndirecto],
                      ['Financiamiento %', factorFinanciamiento, setFactorFinanciamiento],
                      ['Utilidad %', factorUtilidad, setFactorUtilidad],
                      ['Cargos adicionales %', factorCargosAdicionales, setFactorCargosAdicionales],
                      ['Impuesto %', factorImpuesto, setFactorImpuesto],
                    ].map(([label, value, setter]) => (
                      <label key={String(label)}>{String(label)}
                        <input type="number" min={0} max={100} step={0.01} value={Number(value) * 100}
                          onChange={(e) => (setter as (n: number) => void)(Number(e.target.value) / 100)}
                          className="w-full rounded px-1.5 py-1"
                          style={{ background: 'var(--surface-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }} />
                      </label>
                    ))}
                    <label>Fuente / referencia
                      <input value={referenciaParametros} onChange={(e) => setReferenciaParametros(e.target.value)}
                        placeholder="Contrato o análisis" className="w-full rounded px-1.5 py-1"
                        style={{ background: 'var(--surface-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }} />
                    </label>
                  </div>
                  {mensajePresupuesto && (
                    <p className="text-[11px] mb-2" style={{ color: 'var(--text-muted)' }}>{mensajePresupuesto}</p>
                  )}
                  {(Object.entries(resumenPorTipo) as [string, { cantidad: number; volumen: number; area: number }][]).map(([tipo, r]) => (
                    <div
                      key={tipo}
                      className="flex items-center justify-between px-2 py-1.5 rounded text-[11px] mb-1"
                      style={{ background: 'var(--surface)' }}
                    >
                      <span className="flex items-center gap-1.5" style={{ color: 'var(--text-primary)' }}>
                        <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ background: COLOR_POR_TIPO[tipo] || COLOR_DEFAULT }} />
                        {tipo}
                      </span>
                      <span className="font-mono" style={{ color: 'var(--text-muted)' }}>
                        {r.cantidad} pz · {r.volumen.toFixed(2)} m³
                      </span>
                    </div>
                  ))}
                  <div className="mt-3 flex items-start gap-1.5 text-[10px]" style={{ color: 'var(--text-muted)' }}>
                    <FileWarning size={12} className="shrink-0 mt-0.5" />
                    <span>Cantidades &quot;calculadas&quot; vienen de geometría -- revísalas antes de usarlas.</span>
                  </div>
                </div>
              )}

              {/* Tab Clash Detection */}
              {tabDerecho === 'clash' && (
                <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2">
                  {/* Controles */}
                  <div className="flex items-center gap-2">
                    <label className="text-[10px]" style={{ color: 'var(--text-muted)' }}>Tolerancia (m):</label>
                    <input
                      type="number"
                      value={toleranciaM}
                      onChange={(e) => setToleranciaM(Number(e.target.value))}
                      min={0} step={0.01}
                      className="w-16 text-[11px] px-1.5 py-0.5 rounded font-mono"
                      style={{ background: 'var(--surface)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                    />
                    <button
                      onClick={handleCorrerClash}
                      disabled={!canWrite || corriendo || !modelo}
                      className="flex items-center gap-1.5 px-3 py-1 rounded-md text-[11px] font-medium ml-auto transition-colors"
                      style={{ background: 'var(--accent-gold)', color: 'var(--void)', opacity: corriendo || !modelo ? 0.6 : 1 }}
                    >
                      {corriendo ? <Loader2 size={11} className="animate-spin" /> : <ShieldAlert size={11} />}
                      {corriendo ? 'Analizando...' : 'Detectar clashes'}
                    </button>
                  </div>
                  <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                    0 = solo traslape real (DURO). &gt;0 = también marca pares a menos de esa distancia sin tocarse (BLANDO — clearance MEP).
                  </p>

                  {errorClash && (
                    <div className="flex items-center gap-1.5 text-[11px] px-2 py-1.5 rounded" style={{ background: 'rgba(239,68,68,0.1)', color: 'var(--danger)' }}>
                      <AlertCircle size={12} /> {errorClash}
                    </div>
                  )}

                  {analisis && (
                    <div className="flex gap-2 text-[11px]">
                      <div className="flex-1 rounded px-2 py-1.5 text-center" style={{ background: 'rgba(239,68,68,0.1)' }}>
                        <div className="font-bold text-base" style={{ color: '#ef4444' }}>{analisis.num_clashes_duros}</div>
                        <div style={{ color: 'var(--text-muted)' }}>DURO</div>
                      </div>
                      <div className="flex-1 rounded px-2 py-1.5 text-center" style={{ background: 'rgba(245,158,11,0.1)' }}>
                        <div className="font-bold text-base" style={{ color: '#f59e0b' }}>{analisis.num_clashes_blandos}</div>
                        <div style={{ color: 'var(--text-muted)' }}>BLANDO</div>
                      </div>
                      <div className="flex-1 rounded px-2 py-1.5 text-center" style={{ background: 'var(--surface)' }}>
                        <div className="font-bold text-base" style={{ color: 'var(--text-primary)' }}>{analisis.tiempo_calculo_ms ?? '—'}ms</div>
                        <div style={{ color: 'var(--text-muted)' }}>Tiempo</div>
                      </div>
                    </div>
                  )}

                  {/* Lista de clashes */}
                  {clashes.length === 0 && analisis && (
                    <div className="flex items-center gap-2 text-[11px] mt-2" style={{ color: 'var(--success)' }}>
                      <CheckCircle2 size={14} /> Sin conflictos detectados con esta tolerancia.
                    </div>
                  )}

                  {clashes.map((c) => (
                    <div key={c.id} className="rounded-md p-2 text-[11px]" style={{
                      background: c.estado === 'RESUELTO' || c.estado === 'IGNORADO'
                        ? 'var(--surface)'
                        : c.severidad === 'DURO'
                          ? 'rgba(239,68,68,0.07)'
                          : 'rgba(245,158,11,0.07)',
                      border: '1px solid var(--border-subtle)',
                      opacity: c.estado === 'RESUELTO' || c.estado === 'IGNORADO' ? 0.5 : 1,
                    }}>
                      <div className="flex items-center justify-between gap-1 mb-1">
                        <div className="flex items-center gap-1.5">
                          {c.severidad === 'DURO'
                            ? <AlertCircle size={12} style={{ color: '#ef4444' }} />
                            : <AlertTriangle size={12} style={{ color: '#f59e0b' }} />}
                          <span className="font-medium" style={{ color: c.severidad === 'DURO' ? '#ef4444' : '#f59e0b' }}>
                            {c.severidad}
                          </span>
                          <span style={{ color: 'var(--text-muted)' }}>·</span>
                          <span style={{ color: 'var(--text-secondary)' }}>{c.tipo_a}</span>
                          <span style={{ color: 'var(--text-muted)' }}>vs</span>
                          <span style={{ color: 'var(--text-secondary)' }}>{c.tipo_b}</span>
                        </div>
                        <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
                          {c.distancia_m === 0 ? 'traslape' : `${c.distancia_m.toFixed(3)}m`}
                        </span>
                      </div>
                      {c.volumen_aproximado_m3 != null && c.volumen_aproximado_m3 > 0 && (
                        <div className="text-[10px] mb-1" style={{ color: 'var(--text-muted)' }}>
                          Vol. aprox.: {c.volumen_aproximado_m3.toFixed(4)} m³
                        </div>
                      )}
                      <div className="flex gap-1 mt-1.5">
                        {(['REVISADO', 'RESUELTO', 'IGNORADO'] as const).map((est) => (
                          <button
                            key={est}
                            onClick={() => handleMarcarEstado(c.id, est)}
                            className="px-1.5 py-0.5 rounded text-[9px] transition-colors"
                            style={{
                              background: c.estado === est ? 'var(--accent-gold)' : 'var(--surface-elevated)',
                              color: c.estado === est ? 'var(--void)' : 'var(--text-muted)',
                              border: '1px solid var(--border-subtle)',
                            }}
                          >
                            {est}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {/* Tab 5D: mapeo de tipos y elementos a catálogo real */}
              {tabDerecho === 'presupuesto5d' && (
                <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2">
                  <div className="flex items-start gap-1.5 text-[10px] mb-1" style={{ color: 'var(--text-muted)' }}>
                    <Link2 size={12} className="shrink-0 mt-0.5" />
                    <span>Vincula un IfcType a un concepto como regla base y usa overrides por elemento cuando materiales o especificaciones sean distintos. Los elementos sin APU quedan solo cuantificados.</span>
                  </div>
                  {tiposDelModelo.length === 0 && (
                    <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>Sube un modelo para ver sus tipos de elemento aquí.</p>
                  )}

                  {seleccionado && selectedElementSearchKey && (
                    <section className="p-2 rounded" style={{ background: 'var(--surface)', border: '1px solid var(--accent-gold-dim)' }}>
                      <div className="text-[10px] mb-1" style={{ color: 'var(--accent-gold)' }}>APU específico del elemento seleccionado</div>
                      <div className="text-[10px] mb-1 break-all" style={{ color: 'var(--text-secondary)' }}>
                        {seleccionado.nombre || seleccionado.tipo} · {seleccionado.tipo} · {seleccionado.global_id}
                      </div>
                      {mapeoCatalogoElementos[seleccionado.id] ? (
                        <div className="flex items-center justify-between text-[10px]" style={{ color: 'var(--text-secondary)' }}>
                          <span>
                            {mapeoCatalogoElementos[seleccionado.id].descripcion} · {mapeoCatalogoElementos[seleccionado.id].unidad}
                            {' · $'}{mapeoCatalogoElementos[seleccionado.id].precio_unitario.toFixed(2)}
                          </span>
                          <button
                            onClick={() => setMapeoCatalogoElementos((prev) => {
                              const next = { ...prev };
                              delete next[seleccionado.id];
                              return next;
                            })}
                            className="ml-2 shrink-0"
                            style={{ color: 'var(--danger)' }}
                          >
                            Quitar override
                          </button>
                        </div>
                      ) : (
                        <>
                          <div className="flex gap-1">
                            <input
                              value={busquedaCatalogo[selectedElementSearchKey] || ''}
                              onChange={(e) => setBusquedaCatalogo((prev) => ({ ...prev, [selectedElementSearchKey]: e.target.value }))}
                              onKeyDown={(e) => { if (e.key === 'Enter') void handleBuscarCatalogo(selectedElementSearchKey); }}
                              placeholder="Buscar APU específico para este elemento..."
                              className="flex-1 px-1.5 py-1 rounded text-[10px]"
                              style={{ background: 'var(--surface-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                            />
                            <button
                              aria-label="Buscar APU específico del elemento"
                              onClick={() => void handleBuscarCatalogo(selectedElementSearchKey)}
                              disabled={buscandoCatalogo === selectedElementSearchKey}
                              className="px-2 rounded"
                              style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)' }}
                            >
                              {buscandoCatalogo === selectedElementSearchKey ? <Loader2 size={11} className="animate-spin" /> : <Search size={11} />}
                            </button>
                          </div>
                          {(resultadosCatalogo[selectedElementSearchKey] || []).map((concepto) => (
                            <button
                              key={concepto.id}
                              onClick={() => setMapeoCatalogoElementos((prev) => ({ ...prev, [seleccionado.id]: concepto }))}
                              className="block w-full text-left mt-1 px-1.5 py-1 rounded text-[10px]"
                              style={{ background: 'var(--surface-elevated)', color: 'var(--text-secondary)' }}
                            >
                              {concepto.descripcion} · {concepto.unidad} · {'$'}{concepto.precio_unitario.toFixed(2)} ({concepto.fuente})
                            </button>
                          ))}
                          {erroresCatalogo[selectedElementSearchKey] && (
                            <p role="alert" className="text-[10px] mt-1" style={{ color: 'var(--danger)' }}>{erroresCatalogo[selectedElementSearchKey]}</p>
                          )}
                        </>
                      )}
                      <p className="text-[9px] mt-1" style={{ color: 'var(--text-muted)' }}>
                        Este APU prevalece sobre el mapeo general de {seleccionado.tipo}.
                      </p>
                    </section>
                  )}

                  {tiposDelModelo.map((tipo) => {
                    const conceptoSeleccionado = mapeoCatalogo[tipo];
                    return (
                      <div key={tipo} className="p-2 rounded" style={{ background: 'var(--surface)', border: '1px solid var(--border-subtle)' }}>
                        <div className="flex items-center gap-1.5 mb-1.5">
                          <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ background: COLOR_POR_TIPO[tipo] || COLOR_DEFAULT }} />
                          <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>{tipo}</span>
                        </div>
                        {conceptoSeleccionado ? (
                          <div className="flex items-center justify-between text-[10px]" style={{ color: 'var(--text-secondary)' }}>
                            <span>{conceptoSeleccionado.descripcion} · {conceptoSeleccionado.unidad} · {'$'}{conceptoSeleccionado.precio_unitario.toFixed(2)}</span>
                            <button
                              onClick={() => setMapeoCatalogo((prev) => {
                                const next = { ...prev };
                                delete next[tipo];
                                return next;
                              })}
                              className="text-[10px] shrink-0 ml-2"
                              style={{ color: 'var(--danger)' }}
                            >
                              Quitar
                            </button>
                          </div>
                        ) : (
                          <>
                            <div className="flex gap-1">
                              <input
                                value={busquedaCatalogo[tipo] || ''}
                                onChange={(e) => setBusquedaCatalogo((prev) => ({ ...prev, [tipo]: e.target.value }))}
                                onKeyDown={(e) => { if (e.key === 'Enter') void handleBuscarCatalogo(tipo); }}
                                placeholder="Buscar en catálogo (ej. muro, concreto)..."
                                className="flex-1 px-1.5 py-1 rounded text-[10px]"
                                style={{ background: 'var(--surface-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                              />
                              <button
                                aria-label={'Buscar concepto para ' + tipo}
                                onClick={() => void handleBuscarCatalogo(tipo)}
                                disabled={buscandoCatalogo === tipo}
                                className="px-2 rounded"
                                style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)' }}
                              >
                                {buscandoCatalogo === tipo ? <Loader2 size={11} className="animate-spin" /> : <Search size={11} />}
                              </button>
                            </div>
                            {(resultadosCatalogo[tipo] || []).length > 0 && (
                              <div className="mt-1 flex flex-col gap-0.5">
                                {resultadosCatalogo[tipo].map((concepto) => (
                                  <button
                                    key={concepto.id}
                                    onClick={() => setMapeoCatalogo((prev) => ({ ...prev, [tipo]: concepto }))}
                                    className="text-left px-1.5 py-1 rounded text-[10px] transition-colors"
                                    style={{ background: 'var(--surface-elevated)', color: 'var(--text-secondary)' }}
                                  >
                                    {concepto.descripcion} · {concepto.unidad} · {'$'}{concepto.precio_unitario.toFixed(2)} ({concepto.fuente})
                                  </button>
                                ))}
                              </div>
                            )}
                            {erroresCatalogo[tipo] && <p role="alert" className="text-[11px] mt-1" style={{ color: 'var(--danger)' }}>{erroresCatalogo[tipo]}</p>}
                            {!erroresCatalogo[tipo] && buscandoCatalogo !== tipo && busquedaCatalogo[tipo] && (resultadosCatalogo[tipo]?.length === 0) && (
                              <p className="text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>Sin resultados.</p>
                            )}
                          </>
                        )}
                      </div>
                    );
                  })}
                  <CantidadesComplementarias
                    faltantes={faltantesDeMedicion(
                      elementos,
                      Object.fromEntries(Object.entries(mapeoCatalogo).map(([tipo,concepto])=>[tipo,concepto.unidad])),
                      Object.fromEntries(Object.entries(mapeoCatalogoElementos).map(([id,concepto])=>[id,concepto.unidad])),
                    )}
                    capturas={capturasCantidad} disabled={!canWrite || generandoPresupuestoReal}
                    onChange={(id,value)=>setCapturasCantidad(previous=>({...previous,[id]:value}))} />
                  <div className="flex flex-wrap items-center gap-2 mt-1 text-[10px]" style={{ color: 'var(--text-muted)' }}>
                    {[
                      ['Indirectos', factorIndirecto, setFactorIndirecto],
                      ['Financiamiento', factorFinanciamiento, setFactorFinanciamiento],
                      ['Utilidad', factorUtilidad, setFactorUtilidad],
                      ['Cargos adicionales', factorCargosAdicionales, setFactorCargosAdicionales],
                      ['Impuesto', factorImpuesto, setFactorImpuesto],
                    ].map(([label, value, setter]) => (
                      <label key={String(label)} className="flex items-center gap-1">{String(label)}
                        <input type="number" step={0.01} min={0} max={100} value={Number(value) * 100}
                          onChange={(e) => (setter as (n: number) => void)(Number(e.target.value) / 100)}
                          className="w-14 rounded px-1 py-0.5" style={{ background: 'var(--surface-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }} />%
                      </label>
                    ))}
                  </div>
                  <input
                    value={referenciaParametros}
                    onChange={(e) => setReferenciaParametros(e.target.value)}
                    placeholder="Fuente: contrato, convocatoria o análisis"
                    className="w-full rounded px-2 py-1 text-[10px]"
                    style={{ background: 'var(--surface-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                  />
                  <button
                    onClick={handleGenerarPresupuestoReal}
                    disabled={!canWrite || generandoPresupuestoReal || tiposDelModelo.length === 0 || !referenciaParametros.trim()}
                    className="flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-md text-[11px] font-medium mt-1"
                    style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}
                  >
                    {generandoPresupuestoReal ? <Loader2 size={11} className="animate-spin" /> : <Calculator size={11} />}
                    Generar presupuesto
                  </button>
                  {mensajePresupuestoReal && <p role="status" className="text-[11px]" style={{ color: 'var(--text-muted)' }}>{mensajePresupuestoReal}</p>}
                  <PresupuestoPanel expedienteId={expedienteActivo.id} nuevoId={nuevoPresupuestoId} />
                </div>
              )}

              {/* Tab 4D: zonas de trabajo y generación de cronograma */}
              {tabDerecho === 'cronograma4d' && (
                <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-3">
                  <div>
                    <div className="flex items-start gap-1.5 text-[10px] mb-2" style={{ color: 'var(--text-muted)' }}>
                      <Layers size={12} className="shrink-0 mt-0.5" />
                      <span>1. Asigna una zona de trabajo a los elementos del nivel filtrado arriba ({nivelFiltro === '__todos__' ? 'todos los niveles' : nivelFiltro}). Sin zona, se agrupa por nivel del IFC.</span>
                    </div>
                    <div className="flex gap-1">
                      <input
                        value={zonaInput}
                        onChange={(e) => setZonaInput(e.target.value)}
                        placeholder="ej. Torre A - Frente 1"
                        className="flex-1 px-1.5 py-1 rounded text-[10px]"
                        style={{ background: 'var(--surface-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                      />
                      <button
                        onClick={handleAsignarZona}
                        disabled={!canWrite || asignandoZona || !zonaInput.trim()}
                        className="px-2 rounded text-[10px]"
                        style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)' }}
                      >
                        {asignandoZona ? <Loader2 size={11} className="animate-spin" /> : 'Asignar'}
                      </button>
                    </div>
                    {mensajeZona && <p className="text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>{mensajeZona}</p>}
                  </div>

                  <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '0.5rem' }}>
                    <div className="text-[10px] mb-2" style={{ color: 'var(--text-muted)' }}>
                      2. Genera el cronograma: una actividad por zona×tipo, sin secuencia todavía -- eso se ajusta después en Programación, con criterio del programador, no se inventa.
                    </div>
                    <div className="flex gap-1 mb-1.5">
                      <input
                        type="date"
                        value={fechaInicio4D}
                        onChange={(e) => setFechaInicio4D(e.target.value)}
                        className="flex-1 px-1.5 py-1 rounded text-[10px]"
                        style={{ background: 'var(--surface-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                      />
                      <input
                        type="number"
                        min={1}
                        value={diasPorDefecto4D}
                        onChange={(e) => setDiasPorDefecto4D(Number(e.target.value) || 1)}
                        title="Duración inicial sugerida; valide calendario, productividad y recursos antes de aprobar el programa"
                        className="w-16 px-1.5 py-1 rounded text-[10px]"
                        style={{ background: 'var(--surface-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                      />
                    </div>
                    <button
                      onClick={handleGenerar4D}
                      disabled={!canWrite || generando4D || !fechaInicio4D}
                      className="w-full flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-md text-[11px] font-medium"
                      style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}
                    >
                      {generando4D ? <Loader2 size={11} className="animate-spin" /> : <Layers size={11} />}
                      Generar cronograma 4D
                    </button>
                    {generacion4D && generacion4D.estado !== 'ERROR' && generacion4D.estado !== 'COMPLETADO' && (
                      <p className="text-[10px] mt-1.5 flex items-center gap-1" style={{ color: 'var(--text-muted)' }}>
                        <Loader2 size={10} className="animate-spin" /> Generando (agrupando por {generacion4D.agrupar_por})...
                      </p>
                    )}
                    {generacion4D?.estado === 'COMPLETADO' && generacion4D.modelo_id === modelo?.id && (
                      <div className="text-[10px] mt-1.5" style={{ color: 'var(--text-secondary)' }}>
                        <p>{generacion4D.num_actividades_generadas} actividades agrupadas por {generacion4D.agrupar_por}.</p>
                        {expedienteActivo && generacion4D.programa_id && (
                          <CronogramaBim key={`${expedienteActivo.id}:${generacion4D.programa_id}`}
                            expedienteId={expedienteActivo.id} programaId={generacion4D.programa_id} />
                        )}
                        <button type="button" className="block p-2 mt-2 rounded bg-(--accent-gold) text-(--void)"
                          onClick={() => abrirModulo('licitaciones-obra', generacion4D.programa_id || undefined, 'cronograma')}>
                          Editar cronograma en Workspace
                        </button>
                      </div>
                    )}
                    {generacion4D?.estado === 'ERROR' && !error4D && <p role="alert" className="text-xs text-(--danger)">{generacion4D.error} Revisa fecha y duración para generar otro cronograma.</p>}
                    {error4D && (
                      <p className="text-[10px] mt-1.5 flex items-center gap-1" style={{ color: 'var(--danger)' }}>
                        <AlertCircle size={10} /> {error4D}
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function BIMCalculator() {
  const activeExpId = useExpedienteStore(s => s.expedienteActivoId);

  useEffect(() => {
    void useExpedienteStore.getState().cargarExpedientes();
  }, []);

  return (
    <div className="w-full h-full flex flex-col overflow-hidden" style={{ background: 'var(--abyss)', color: 'var(--text-primary)' }}>
      <div className="flex items-center justify-between px-3 py-2 shrink-0" style={{ background: 'var(--surface)', borderBottom: '1px solid var(--border-subtle)' }}>
        <div className="flex items-center gap-2">
          <Box size={14} style={{ color: 'var(--accent-gold)' }} />
          <span className="text-xs font-semibold">BIM / IFC</span>
          <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>Cuantificación, 4D y 5D con evidencia persistida</span>
        </div>
        <button
          onClick={() => abrirModulo('megalodon-costos')}
          className="px-2.5 py-1 rounded text-[10px]"
          style={{ background: 'var(--surface-elevated)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}
        >
          Abrir CostOS
        </button>
      </div>
      <IFCPanel key={activeExpId || 'sin-obra'} />
    </div>
  );
}
