/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import * as THREE from 'three';
import { Upload, Loader2, AlertCircle, Layers3, Calculator, FileSpreadsheet, Plus } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';
import type { Levantamiento, SuperficieTIN, CalculoVolumen } from '@/lib/megalodon-client';
import PresupuestoPanel from '@/apps/bim-calculator/PresupuestoPanel';

function rampaColor(t: number): [number, number, number] {
  const c = t < 0.5
    ? [51 + t * 2 * (212 - 51), 140 + t * 2 * (149 - 140), 64 + t * 2 * (77 - 64)]
    : [212 + (t - 0.5) * 2 * (140 - 212), 149 + (t - 0.5) * 2 * (89 - 149), 77 + (t - 0.5) * 2 * (51 - 77)];
  return [c[0] / 255, c[1] / 255, c[2] / 255];
}

function VisorTIN({ superficie }: { superficie: SuperficieTIN | null }) {
  const contenedorRef = useRef<HTMLDivElement>(null);
  const escenaRef = useRef<{ renderer: THREE.WebGLRenderer; scene: THREE.Scene; camera: THREE.PerspectiveCamera; frame: number } | null>(null);

  useEffect(() => {
    if (!contenedorRef.current) return;
    const ancho = contenedorRef.current.clientWidth || 600;
    const alto = contenedorRef.current.clientHeight || 400;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x05050a);
    const camera = new THREE.PerspectiveCamera(45, ancho / alto, 0.1, 5000);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(ancho, alto);
    contenedorRef.current.innerHTML = '';
    contenedorRef.current.appendChild(renderer.domElement);
    scene.add(new THREE.AmbientLight(0xffffff, 0.6));
    const luz = new THREE.DirectionalLight(0xffffff, 0.8);
    luz.position.set(1, 1.5, 1);
    scene.add(luz);
    camera.position.set(0, -1, 1);
    let rot = 0;
    const animar = () => {
      rot += 0.0015;
      camera.position.x = Math.sin(rot) * (camera.userData.dist || 1);
      camera.position.y = -Math.cos(rot) * (camera.userData.dist || 1);
      camera.lookAt(0, 0, 0);
      renderer.render(scene, camera);
      escenaRef.current!.frame = requestAnimationFrame(animar);
    };
    escenaRef.current = { renderer, scene, camera, frame: 0 };
    animar();
    const onResize = () => {
      if (!contenedorRef.current) return;
      const w = contenedorRef.current.clientWidth, h = contenedorRef.current.clientHeight;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    window.addEventListener('resize', onResize);
    return () => {
      cancelAnimationFrame(escenaRef.current?.frame || 0);
      window.removeEventListener('resize', onResize);
      renderer.dispose();
    };
  }, []);

  useEffect(() => {
    const ctx = escenaRef.current;
    if (!ctx || !superficie) return;
    const viejo = ctx.scene.getObjectByName('tin');
    if (viejo) ctx.scene.remove(viejo);

    const verts = superficie.malla_vertices;
    const cx = verts.filter((_, i) => i % 3 === 0).reduce((a, b) => a + b, 0) / (verts.length / 3);
    const cy = verts.filter((_, i) => i % 3 === 1).reduce((a, b) => a + b, 0) / (verts.length / 3);
    const cz = superficie.elevacion_min;
    const escala = 1 / Math.max(1, Math.sqrt(superficie.area_plan_m2) / 1.4);

    const centrados = new Float32Array(verts.length);
    const colores = new Float32Array(verts.length);
    const rango = Math.max(0.01, superficie.elevacion_max - superficie.elevacion_min);
    for (let i = 0; i < verts.length; i += 3) {
      centrados[i] = (verts[i] - cx) * escala;
      centrados[i + 1] = (verts[i + 1] - cy) * escala;
      centrados[i + 2] = (verts[i + 2] - cz) * escala;
      const t = (verts[i + 2] - superficie.elevacion_min) / rango;
      const [r, g, b] = rampaColor(t);
      colores[i] = r; colores[i + 1] = g; colores[i + 2] = b;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(centrados, 3));
    geo.setAttribute('color', new THREE.Float32BufferAttribute(colores, 3));
    geo.setIndex(superficie.malla_caras);
    geo.computeVertexNormals();
    const malla = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ vertexColors: true, side: THREE.DoubleSide, flatShading: true }));
    malla.name = 'tin';
    ctx.scene.add(malla);
    ctx.camera.userData.dist = 1.6;
  }, [superficie]);

  return <div ref={contenedorRef} className="w-full h-full" />;
}

export default function LevantamientoPanel({
  expedienteId, onLevantamientoChange, onSuperficiesChange,
}: {
  expedienteId: string;
  onLevantamientoChange?: (l: Levantamiento | null) => void;
  onSuperficiesChange?: (s: SuperficieTIN[]) => void;
}) {
  const [levantamientos, setLevantamientos] = useState<Levantamiento[]>([]);
  const [activo, setActivo] = useState<Levantamiento | null>(null);
  const [nombreNuevo, setNombreNuevo] = useState('');
  const [sridNuevo, setSridNuevo] = useState('6362');
  const [superficies, setSuperficies] = useState<SuperficieTIN[]>([]);
  const [superficieVista, setSuperficieVista] = useState<SuperficieTIN | null>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [error, setError] = useState('');

  const [superficieA, setSuperficieA] = useState('');
  const [superficieB, setSuperficieB] = useState('');
  const [elevacionRef, setElevacionRef] = useState('');
  const [calculando, setCalculando] = useState(false);
  const [resultadoVolumen, setResultadoVolumen] = useState<CalculoVolumen | null>(null);
  const [mensajePresupuesto, setMensajePresupuesto] = useState('');
  const [generandoPresupuesto, setGenerandoPresupuesto] = useState(false);
  const [presupuestoCreadoId, setPresupuestoCreadoId] = useState('');
  const [factorIndirecto, setFactorIndirecto] = useState(0);
  const [factorUtilidad, setFactorUtilidad] = useState(0);
  const [factorImpuesto, setFactorImpuesto] = useState(0);
  const [referenciaParametros, setReferenciaParametros] = useState('');
  const contextoVolumen = JSON.stringify([expedienteId, activo?.id, superficieA, superficieB, elevacionRef]);
  const contextoActual = useRef(contextoVolumen);
  contextoActual.current = contextoVolumen;
  const marcoCarga = JSON.stringify([expedienteId, activo?.id]);
  const marcoActual = useRef(marcoCarga);
  marcoActual.current = marcoCarga;
  const expedienteActual = useRef(expedienteId);
  expedienteActual.current = expedienteId;
  const activoActual = useRef(activo);
  activoActual.current = activo;
  const solicitudLevantamientos = useRef(0);
  const solicitudSuperficies = useRef(0);

  const cargarLevantamientos = useCallback(async () => {
    const solicitud = ++solicitudLevantamientos.current;
    try {
      const lista = await megalodonClient.topografia.listarLevantamientos(expedienteId);
      if (expedienteActual.current !== expedienteId || solicitud !== solicitudLevantamientos.current) return;
      const seleccionado = activoActual.current;
      if (seleccionado?.expediente_id === expedienteId && !lista.some((l) => l.id === seleccionado.id)) lista.push(seleccionado);
      setLevantamientos(lista);
      setActivo((prev) => lista.find((l) => l.id === prev?.id) || lista[0] || null);
    } catch (e) { setError((e as Error).message); }
  }, [expedienteId]);

  useEffect(() => { void cargarLevantamientos(); }, [cargarLevantamientos]);

  const cargarSuperficies = useCallback(async () => {
    if (!activo || activo.expediente_id !== expedienteId) return;
    const solicitud = ++solicitudSuperficies.current;
    const marco = JSON.stringify([expedienteId, activo.id]);
    try {
      const ligeras = await megalodonClient.topografia.listarSuperficies(activo.id);
      const completas = await Promise.all(ligeras.map((s) => megalodonClient.topografia.obtenerSuperficie(s.id)));
      if (marcoActual.current !== marco || solicitud !== solicitudSuperficies.current) return;
      setSuperficies(completas);
      setSuperficieVista((v) => completas.find((s) => s.id === v?.id) || completas[0] || null);
    } catch (e) { setError((e as Error).message); }
  }, [activo?.id, expedienteId]);

  useEffect(() => {
    setSuperficies([]); setSuperficieVista(null);
    setSuperficieA(''); setSuperficieB(''); setElevacionRef('');
    void cargarSuperficies();
  }, [cargarSuperficies]);

  useEffect(() => {
    setResultadoVolumen(null);
    setMensajePresupuesto('');
    setPresupuestoCreadoId('');
  }, [superficieA, superficieB, elevacionRef, activo?.id, expedienteId]);

  useEffect(() => { onLevantamientoChange?.(activo); }, [activo, onLevantamientoChange]);
  useEffect(() => { onSuperficiesChange?.(superficies); }, [superficies, onSuperficiesChange]);

  const crearLevantamiento = async () => {
    if (!nombreNuevo.trim()) return;
    try {
      const l = await megalodonClient.topografia.crearLevantamiento(expedienteId, {
        nombre: nombreNuevo.trim(), crs: `EPSG:${sridNuevo}`, srid: Number(sridNuevo),
      });
      if (expedienteActual.current !== expedienteId) return;
      setNombreNuevo('');
      setActivo(l);
      await cargarLevantamientos();
    } catch (e) { setError((e as Error).message); }
  };

  const subirCSV = async (file: File) => {
    if (!activo) return;
    setSubiendo(true); setError('');
    try {
      await megalodonClient.topografia.importarCSV(activo.id, file, 'penzd');
      const superficie = await megalodonClient.topografia.triangular(activo.id, `${activo.nombre} · terreno existente`, 'EXISTENTE');
      if (marcoActual.current !== marcoCarga) return;
      setSuperficieVista(superficie);
      await cargarSuperficies();
    } catch (e) { setError(e instanceof Error ? e.message : 'No se pudo importar/triangular el CSV'); } finally { setSubiendo(false); }
  };

  const calcularVolumen = async () => {
    if (!superficies.some((s) => s.id === superficieA && s.levantamiento_id === activo?.id)
      || (superficieB && !superficies.some((s) => s.id === superficieB && s.levantamiento_id === activo?.id))
      || (!superficieB && !elevacionRef)) return;
    setCalculando(true); setError(''); setResultadoVolumen(null);
    try {
      const resultado = await megalodonClient.topografia.calcularVolumen({
        superficie_existente_id: superficieA,
        superficie_proyecto_id: superficieB || undefined,
        elevacion_referencia: !superficieB && elevacionRef ? Number(elevacionRef) : undefined,
      });
      if (contextoActual.current === contextoVolumen) setResultadoVolumen(resultado);
    } catch (e) { setError(e instanceof Error ? e.message : 'No se pudo calcular el volumen'); } finally { setCalculando(false); }
  };

  const generarPresupuesto = async () => {
    if (!resultadoVolumen || generandoPresupuesto) return;
    if (!referenciaParametros.trim()) {
      setMensajePresupuesto('Indica la referencia o fuente de los parámetros de costeo.');
      return;
    }
    setMensajePresupuesto('');
    setGenerandoPresupuesto(true);
    try {
      const presupuesto = await megalodonClient.topografia.generarPresupuestoMovimientoTierras(
        resultadoVolumen.id,
        expedienteId,
        {
          parametros_costeo: {
            factor_indirecto: factorIndirecto,
            factor_utilidad: factorUtilidad,
            factor_impuesto: factorImpuesto,
            factor_riesgo: 0,
            fuente: 'CAPTURA_USUARIO',
            referencia: referenciaParametros.trim(),
          },
        },
      );
      if (contextoActual.current === contextoVolumen) {
        setPresupuestoCreadoId(presupuesto.id);
        setMensajePresupuesto(`Presupuesto ${presupuesto.identificador} creado con origen de cada cantidad. Falta capturar precios unitarios.${resultadoVolumen.evidencia?.cobertura.completa === false ? ' La cobertura pendiente bloquea la aprobación.' : ''}`);
      }
    } catch (e) {
      if (contextoActual.current === contextoVolumen) setMensajePresupuesto(e instanceof Error ? e.message : 'No se pudo generar el presupuesto');
    } finally { setGenerandoPresupuesto(false); }
  };

  return (
    <div className="h-full flex" style={{ color: 'var(--text-primary)' }}>
      <div className="flex-1 min-w-0 relative">
        {superficieVista ? (
          <VisorTIN superficie={superficieVista} />
        ) : (
          <div className="h-full flex flex-col items-center justify-center gap-2 text-sm text-center" style={{ color: 'var(--text-muted)' }}>
            <Layers3 className="w-8 h-8 opacity-40" />
            {activo ? 'Sube un CSV de puntos (formato PENZD) para triangular la primera superficie.' : 'Crea o selecciona un levantamiento para empezar.'}
          </div>
        )}
        {superficieVista && (
          <div className="absolute top-2 left-2 rounded-lg px-3 py-2 text-[11px] font-mono" style={{ background: 'rgba(10,10,15,0.85)', border: '1px solid var(--border-subtle)' }}>
            <p style={{ color: 'var(--text-primary)' }}>{superficieVista.nombre}</p>
            <p style={{ color: 'var(--text-muted)' }}>{superficieVista.num_puntos} pts · {superficieVista.num_triangulos} triángulos · {superficieVista.area_plan_m2.toFixed(0)} m²</p>
            <p style={{ color: 'var(--text-muted)' }}>elev. {superficieVista.elevacion_min.toFixed(2)}–{superficieVista.elevacion_max.toFixed(2)} m · pend. media {superficieVista.pendiente_media_pct.toFixed(1)}%</p>
          </div>
        )}
      </div>

      <div className="w-[320px] shrink-0 overflow-y-auto p-3 space-y-4" style={{ borderLeft: '1px solid var(--border-subtle)', background: 'var(--surface)' }}>
        {error && <div className="flex items-start gap-1.5 text-[11px]" style={{ color: 'var(--danger)' }}><AlertCircle size={12} className="mt-0.5 shrink-0" />{error}</div>}

        <div>
          <p className="text-[11px] font-semibold mb-1.5" style={{ color: 'var(--text-muted)' }}>LEVANTAMIENTO</p>
          <select
            aria-label="Levantamiento activo"
            value={activo?.id || ''}
            onChange={(e) => setActivo(levantamientos.find((l) => l.id === e.target.value) || null)}
            className="w-full h-8 rounded px-2 text-xs outline-hidden mb-2"
            style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-primary)' }}
          >
            <option value="">— seleccionar —</option>
            {levantamientos.map((l) => <option key={l.id} value={l.id}>{l.nombre}</option>)}
          </select>
          <div className="flex gap-1.5">
            <input value={nombreNuevo} onChange={(e) => setNombreNuevo(e.target.value)} placeholder="Nombre nuevo levantamiento" className="flex-1 h-8 rounded px-2 text-xs outline-hidden" style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-primary)' }} />
            <button aria-label="Crear levantamiento" onClick={() => void crearLevantamiento()} disabled={!nombreNuevo.trim()} className="h-8 w-8 flex items-center justify-center rounded disabled:opacity-40" style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}><Plus size={14} /></button>
          </div>
          <label className="block mt-2 text-[11px]" style={{ color: 'var(--text-muted)' }}>
            Coordenadas del nuevo levantamiento
            <select aria-label="Sistema de coordenadas" value={sridNuevo} onChange={(e) => setSridNuevo(e.target.value)} className="w-full h-8 rounded px-2 text-xs mt-1" style={{ background: 'var(--surface-elevated)', color: 'var(--text-primary)' }}>
              <option value="6362">México ITRF92 / LCC · EPSG:6362</option>
              {[11, 12, 13, 14, 15, 16].map((zone) => <option key={zone} value={32600 + zone}>WGS84 / UTM {zone}N · EPSG:{32600 + zone}</option>)}
            </select>
          </label>
          {activo && <p className="mt-1 text-[11px]" style={{ color: 'var(--text-muted)' }}>{activo.crs} · elevaciones Z en metros</p>}
        </div>

        {activo && (
          <div>
            <p className="text-[11px] font-semibold mb-1.5" style={{ color: 'var(--text-muted)' }}>PUNTOS (CSV)</p>
            <p className="text-[11px] mb-2" style={{ color: 'var(--text-muted)' }}>El CRS debe coincidir con tu archivo. Todos los puntos necesitan elevación Z; no se sustituye por cero.</p>
            <label className="flex items-center justify-center gap-2 h-9 rounded-md text-xs font-medium cursor-pointer" style={{ background: 'var(--surface-elevated)', border: '1px dashed var(--border-active)', color: 'var(--text-secondary)' }}>
              {subiendo ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />}
              {subiendo ? 'Triangulando…' : 'Subir CSV (PENZD)'}
              <input aria-label="Subir puntos CSV" type="file" accept=".csv" className="hidden" disabled={subiendo} onChange={(e) => e.target.files?.[0] && void subirCSV(e.target.files[0])} />
            </label>
          </div>
        )}

        {superficies.length > 0 && (
          <div>
            <p className="text-[11px] font-semibold mb-1.5" style={{ color: 'var(--text-muted)' }}>SUPERFICIES</p>
            <div className="space-y-1">
              {superficies.map((s) => (
                <button key={s.id} onClick={() => setSuperficieVista(s)} className="w-full text-left px-2 py-1.5 rounded text-[11px]" style={superficieVista?.id === s.id ? { background: 'var(--accent-gold)22', color: 'var(--accent-gold)', border: '1px solid var(--accent-gold)44' } : { color: 'var(--text-secondary)' }}>
                  <FileSpreadsheet size={11} className="inline mr-1.5" />{s.nombre} <span style={{ color: 'var(--text-muted)' }}>({s.tipo === 'EXISTENTE' ? 'terreno' : 'proyecto'})</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {superficies.length > 0 && (
          <div>
            <p className="text-[11px] font-semibold mb-1.5 flex items-center gap-1.5" style={{ color: 'var(--text-muted)' }}><Calculator size={11} /> VOLUMEN CORTE/RELLENO</p>
            <select aria-label="Superficie existente" value={superficieA} onChange={(e) => setSuperficieA(e.target.value)} className="w-full h-8 rounded px-2 text-xs outline-hidden mb-1.5" style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-primary)' }}>
              <option value="">Superficie existente</option>
              {superficies.map((s) => <option key={s.id} value={s.id}>{s.nombre}</option>)}
            </select>
            <select aria-label="Superficie de proyecto" value={superficieB} onChange={(e) => setSuperficieB(e.target.value)} className="w-full h-8 rounded px-2 text-xs outline-hidden mb-1.5" style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-primary)' }}>
              <option value="">Superficie de proyecto (opcional)</option>
              {superficies.map((s) => <option key={s.id} value={s.id}>{s.nombre}</option>)}
            </select>
            {!superficieB && (
              <input aria-label="Elevación de referencia" value={elevacionRef} onChange={(e) => setElevacionRef(e.target.value)} type="number" placeholder="o elevación de referencia (m)" className="w-full h-8 rounded px-2 text-xs outline-hidden mb-1.5" style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-primary)' }} />
            )}
            <button onClick={() => void calcularVolumen()} disabled={calculando || !superficieA || (!superficieB && !elevacionRef)} className="w-full h-8 rounded text-xs font-medium flex items-center justify-center gap-1.5 disabled:opacity-40" style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}>
              {calculando ? <Loader2 size={12} className="animate-spin" /> : <Calculator size={12} />} Calcular
            </button>
            {resultadoVolumen && (
              <div className="mt-2 space-y-1 text-[11px]">
                <div className="flex justify-between"><span style={{ color: 'var(--text-muted)' }}>Corte</span><span style={{ color: 'var(--danger)' }}>{resultadoVolumen.volumen_corte_m3.toLocaleString('es-MX')} m³</span></div>
                <div className="flex justify-between"><span style={{ color: 'var(--text-muted)' }}>Relleno</span><span style={{ color: 'var(--success)' }}>{resultadoVolumen.volumen_terraplen_m3.toLocaleString('es-MX')} m³</span></div>
                <div className="flex justify-between font-semibold"><span style={{ color: 'var(--text-muted)' }}>Neto</span><span>{resultadoVolumen.volumen_neto_m3.toLocaleString('es-MX')} m³</span></div>
                {resultadoVolumen.evidencia && <p role="status" style={{ color: resultadoVolumen.evidencia.cobertura.completa ? 'var(--text-muted)' : 'var(--warning)' }}>
                  {resultadoVolumen.evidencia.cobertura.completa ? 'Cobertura completa' : 'Medición parcial'} · Área común: {resultadoVolumen.evidencia.cobertura.area_comun_m2.toLocaleString('es-MX')} m².
                  {!resultadoVolumen.evidencia.cobertura.completa && <> Pendiente: {resultadoVolumen.evidencia.cobertura.area_existente_pendiente_m2.toLocaleString('es-MX')} m² en terreno y {resultadoVolumen.evidencia.cobertura.area_proyecto_pendiente_m2.toLocaleString('es-MX')} m² en proyecto. Puedes costear lo medido; la aprobación requiere completar la cobertura.</>}
                </p>}
                <div className="grid grid-cols-3 gap-1 pt-1.5">
                  <label className="space-y-0.5">
                    <span style={{ color: 'var(--text-muted)' }}>Indirectos %</span>
                    <input type="number" min="0" max="100" step="0.01" value={factorIndirecto * 100} onChange={(e) => setFactorIndirecto(Number(e.target.value) / 100)} className="w-full h-7 rounded px-1.5 outline-hidden" style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-primary)' }} />
                  </label>
                  <label className="space-y-0.5">
                    <span style={{ color: 'var(--text-muted)' }}>Utilidad %</span>
                    <input type="number" min="0" max="100" step="0.01" value={factorUtilidad * 100} onChange={(e) => setFactorUtilidad(Number(e.target.value) / 100)} className="w-full h-7 rounded px-1.5 outline-hidden" style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-primary)' }} />
                  </label>
                  <label className="space-y-0.5">
                    <span style={{ color: 'var(--text-muted)' }}>Impuesto %</span>
                    <input type="number" min="0" max="100" step="0.01" value={factorImpuesto * 100} onChange={(e) => setFactorImpuesto(Number(e.target.value) / 100)} className="w-full h-7 rounded px-1.5 outline-hidden" style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-primary)' }} />
                  </label>
                </div>
                <input aria-label="Referencia de parámetros topográficos" value={referenciaParametros} onChange={(e) => setReferenciaParametros(e.target.value)} placeholder="Fuente o referencia de los parámetros" className="w-full h-7 rounded px-2 outline-hidden" style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-primary)' }} />
                <button onClick={() => void generarPresupuesto()} disabled={generandoPresupuesto || !referenciaParametros.trim()} className="w-full mt-1.5 h-7 rounded text-[11px] disabled:opacity-40" style={{ border: '1px solid var(--border-active)', color: 'var(--text-secondary)' }}>{generandoPresupuesto ? 'Guardando presupuesto…' : 'Generar presupuesto de movimiento de tierras'}</button>
                {mensajePresupuesto && <p style={{ color: 'var(--text-muted)' }}>{mensajePresupuesto}</p>}
                {presupuestoCreadoId && <PresupuestoPanel key={expedienteId} expedienteId={expedienteId} nuevoId={presupuestoCreadoId} />}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
