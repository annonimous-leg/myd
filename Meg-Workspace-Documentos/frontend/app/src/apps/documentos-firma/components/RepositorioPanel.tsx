/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { Fragment, useCallback, useEffect, useState } from 'react';
import {
  Search, Upload, Loader2, AlertCircle, FileText, Copy, Activity,
  Tag, Clock, ChevronRight, X, Download, CheckCircle2,
} from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';
import {
  TIPOS_DOCUMENTO, ESTADOS_DOCUMENTO,
  type BusquedaDocumentosResultado, type DocumentoDuplicado,
  type EstadisticasDocumentales, type VersionDocumento,
} from '@/lib/megalodon-client';

const ESTADO_COLOR: Record<string, string> = {
  BORRADOR: 'var(--text-muted)',
  EN_REVISION: 'var(--amber)',
  APROBADO: 'var(--success)',
  PUBLICADO: 'var(--accent-cyan)',
  ARCHIVADO: 'var(--text-secondary)',
  OBSOLETO: 'var(--danger)',
};

function Badge({ children, color }: { children: React.ReactNode; color: string }) {
  return (
    <span
      className="text-[10px] font-medium px-1.5 py-0.5 rounded"
      style={{ color, background: `${color}22`, border: `1px solid ${color}44` }}
    >
      {children}
    </span>
  );
}

function inputStyle(): React.CSSProperties {
  return {
    background: 'var(--surface-elevated)',
    border: '1px solid var(--border-subtle)',
    color: 'var(--text-primary)',
  };
}

export default function RepositorioPanel({ expedienteId }: { expedienteId: string }) {
  const [q, setQ] = useState('');
  const [tipo, setTipo] = useState('');
  const [estado, setEstado] = useState('');
  const [resultado, setResultado] = useState<BusquedaDocumentosResultado | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [stats, setStats] = useState<EstadisticasDocumentales | null>(null);
  const [showStats, setShowStats] = useState(false);

  const [duplicados, setDuplicados] = useState<DocumentoDuplicado[] | null>(null);
  const [showDuplicados, setShowDuplicados] = useState(false);
  const [buscandoDuplicados, setBuscandoDuplicados] = useState(false);

  const [selId, setSelId] = useState<string | null>(null);
  const [versiones, setVersiones] = useState<VersionDocumento[] | null>(null);
  const [cargandoVersiones, setCargandoVersiones] = useState(false);

  const [showUpload, setShowUpload] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadTipo, setUploadTipo] = useState<string>(TIPOS_DOCUMENTO[0]);
  const [uploadCifrar, setUploadCifrar] = useState(false);
  const [subiendo, setSubiendo] = useState(false);

  const [clasificando, setClasificando] = useState(false);
  const [tipoSugerido, setTipoSugerido] = useState('');

  const buscar = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await megalodonClient.documentos.busquedaAvanzada({
        q: q || undefined,
        tipo: tipo || undefined,
        estado: estado || undefined,
        expedienteId,
        limit: 100,
      });
      setResultado(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo buscar documentos');
    } finally {
      setLoading(false);
    }
  }, [q, tipo, estado, expedienteId]);

  useEffect(() => { void buscar(); }, [expedienteId]); // eslint-disable-line react-hooks/exhaustive-deps

  const cargarStats = async () => {
    setShowStats((v) => !v);
    if (!stats) {
      try {
        setStats(await megalodonClient.documentos.estadisticas(expedienteId));
      } catch (e) {
        setError(e instanceof Error ? e.message : 'No se pudieron cargar estadísticas');
      }
    }
  };

  const buscarDuplicados = async () => {
    setShowDuplicados(true);
    setBuscandoDuplicados(true);
    try {
      setDuplicados(await megalodonClient.documentos.duplicados(expedienteId));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo detectar duplicados');
    } finally {
      setBuscandoDuplicados(false);
    }
  };

  const abrirDetalle = async (id: string) => {
    setSelId(id === selId ? null : id);
    if (id !== selId) {
      setVersiones(null);
      setCargandoVersiones(true);
      try {
        setVersiones(await megalodonClient.documentos.versiones(id));
      } catch (e) {
        setError(e instanceof Error ? e.message : 'No se pudo cargar el árbol de versiones');
      } finally {
        setCargandoVersiones(false);
      }
    }
  };

  const clasificar = async (id: string) => {
    if (!tipoSugerido) return;
    setClasificando(true);
    try {
      await megalodonClient.documentos.clasificar(id, tipoSugerido);
      await buscar();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo clasificar el documento');
    } finally {
      setClasificando(false);
    }
  };

  const subirDocumento = async () => {
    if (!uploadFile) return;
    setSubiendo(true);
    setError('');
    try {
      await megalodonClient.expedientes.subirDocumento(expedienteId, uploadFile, uploadTipo, uploadCifrar);
      setShowUpload(false);
      setUploadFile(null);
      await buscar();
      setStats(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo subir el documento');
    } finally {
      setSubiendo(false);
    }
  };

  const descargar = async (documentoId: string, nombre: string) => {
    try {
      const blob = await megalodonClient.expedientes.descargarDocumento(expedienteId, documentoId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = nombre;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo descargar el documento');
    }
  };

  const docs = resultado?.resultados || [];

  return (
    <div className="flex h-full min-h-0">
      <div className="flex-1 flex flex-col min-w-0">
        {/* Barra de búsqueda */}
        <div
          className="flex items-center gap-2 px-3 py-2 flex-wrap"
          style={{ borderBottom: '1px solid var(--border-subtle)', background: 'var(--surface)' }}
        >
          <div className="relative flex-1 min-w-[180px]">
            <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }} />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && buscar()}
              placeholder="Buscar por nombre o descripción..."
              className="w-full h-8 rounded pl-7 pr-2 text-xs outline-hidden"
              style={inputStyle()}
            />
          </div>
          <select value={tipo} onChange={(e) => setTipo(e.target.value)} className="h-8 rounded px-2 text-xs outline-hidden" style={inputStyle()}>
            <option value="">Todos los tipos</option>
            {TIPOS_DOCUMENTO.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <select value={estado} onChange={(e) => setEstado(e.target.value)} className="h-8 rounded px-2 text-xs outline-hidden" style={inputStyle()}>
            <option value="">Todos los estados</option>
            {ESTADOS_DOCUMENTO.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <button
            onClick={buscar} disabled={loading}
            className="flex items-center gap-1.5 h-8 px-3 rounded text-xs font-medium"
            style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}
          >
            {loading ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />}
            Buscar
          </button>
          <div className="flex-1" />
          <button
            onClick={buscarDuplicados}
            className="flex items-center gap-1.5 h-8 px-3 rounded text-xs font-medium"
            style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-primary)' }}
          >
            <Copy size={13} /> Duplicados
          </button>
          <button
            onClick={cargarStats}
            className="flex items-center gap-1.5 h-8 px-3 rounded text-xs font-medium"
            style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-primary)' }}
          >
            <Activity size={13} /> Estadísticas
          </button>
          <button
            onClick={() => setShowUpload(true)}
            className="flex items-center gap-1.5 h-8 px-3 rounded text-xs font-medium"
            style={{ background: 'var(--accent-gold-dim)', color: 'var(--void)' }}
          >
            <Upload size={13} /> Subir documento
          </button>
        </div>

        {error && (
          <div className="flex items-center gap-2 px-3 py-2 text-xs" style={{ color: 'var(--danger)' }}>
            <AlertCircle size={13} /> {error}
          </div>
        )}

        {showStats && stats && (
          <div className="grid grid-cols-4 gap-3 px-3 py-3" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
            <StatCard label="Documentos" value={String(stats.total_documentos)} />
            <StatCard label="Versiones totales" value={String(stats.total_versiones)} />
            <StatCard label="Promedio versiones" value={stats.promedio_versiones.toFixed(2)} />
            <StatCard label="Tipos distintos" value={String(Object.keys(stats.por_tipo).length)} />
            <div className="col-span-4 flex flex-wrap gap-1.5 mt-1">
              {Object.entries(stats.por_estado).map(([k, v]) => (
                <Badge key={k} color={ESTADO_COLOR[k] || 'var(--text-secondary)'}>{k}: {v}</Badge>
              ))}
            </div>
          </div>
        )}

        {showDuplicados && (
          <div className="px-3 py-3" style={{ borderBottom: '1px solid var(--border-subtle)', background: 'rgba(184,74,74,0.06)' }}>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium" style={{ color: 'var(--danger)' }}>
                {buscandoDuplicados ? 'Buscando duplicados...' : `${duplicados?.length ?? 0} posibles duplicados`}
              </span>
              <button onClick={() => setShowDuplicados(false)} style={{ color: 'var(--text-muted)' }}><X size={13} /></button>
            </div>
            {duplicados && duplicados.length > 0 && (
              <div className="space-y-1">
                {duplicados.map((d, i) => (
                  <div key={i} className="text-xs flex items-center gap-2" style={{ color: 'var(--text-secondary)' }}>
                    <span className="truncate">{d.nombre}</span>
                    <span style={{ color: 'var(--text-muted)' }}>({d.tipo})</span>
                    <Badge color="var(--danger)">{Math.round(d.similitud * 100)}% similar</Badge>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Tabla de resultados */}
        <div className="flex-1 overflow-auto">
          {docs.length === 0 && !loading ? (
            <div className="flex flex-col items-center justify-center h-full gap-2 text-center px-6" style={{ color: 'var(--text-muted)' }}>
              <FileText size={26} className="opacity-40" />
              <p className="text-sm">Sin documentos que coincidan con el filtro.</p>
            </div>
          ) : (
            <table className="w-full text-xs">
              <thead style={{ position: 'sticky', top: 0, background: 'var(--surface)', borderBottom: '1px solid var(--border-subtle)' }}>
                <tr style={{ color: 'var(--text-muted)' }}>
                  <th className="text-left font-medium px-3 py-2">Nombre</th>
                  <th className="text-left font-medium px-3 py-2">Tipo</th>
                  <th className="text-left font-medium px-3 py-2">Estado</th>
                  <th className="text-left font-medium px-3 py-2">Versión</th>
                  <th className="text-left font-medium px-3 py-2">Fecha</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {docs.map((d) => (
                  <Fragment key={d.id}>
                    <tr
                      onClick={() => abrirDetalle(d.id)}
                      className="cursor-pointer transition-colors"
                      style={{ borderBottom: '1px solid var(--border-subtle)', background: selId === d.id ? 'var(--surface-elevated)' : 'transparent' }}
                    >
                      <td className="px-3 py-2 flex items-center gap-1.5">
                        <ChevronRight size={11} style={{ transform: selId === d.id ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s', color: 'var(--text-muted)' }} />
                        {d.nombre}
                      </td>
                      <td className="px-3 py-2"><Badge color="var(--info)">{d.tipo}</Badge></td>
                      <td className="px-3 py-2"><Badge color={ESTADO_COLOR[d.estado] || 'var(--text-secondary)'}>{d.estado}</Badge></td>
                      <td className="px-3 py-2" style={{ color: 'var(--text-secondary)' }}>v{d.version}</td>
                      <td className="px-3 py-2" style={{ color: 'var(--text-secondary)' }}>
                        {d.created_at ? new Date(d.created_at).toLocaleDateString('es-MX') : '—'}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button
                          onClick={(e) => { e.stopPropagation(); descargar(d.id, d.nombre); }}
                          className="p-1 rounded hover:opacity-80"
                          style={{ color: 'var(--text-muted)' }}
                          title="Descargar"
                        >
                          <Download size={13} />
                        </button>
                      </td>
                    </tr>
                    {selId === d.id && (
                      <tr style={{ background: 'var(--abyss)' }}>
                        <td colSpan={6} className="px-6 py-3">
                          <div className="grid grid-cols-2 gap-6">
                            <div>
                              <div className="flex items-center gap-1.5 mb-2 text-[11px] font-medium" style={{ color: 'var(--accent-gold)' }}>
                                <Clock size={12} /> Árbol de versiones
                              </div>
                              {cargandoVersiones ? (
                                <Loader2 size={13} className="animate-spin" style={{ color: 'var(--text-muted)' }} />
                              ) : versiones && versiones.length > 0 ? (
                                <div className="space-y-1">
                                  {versiones.map((v) => (
                                    <div key={v.id} className="flex items-center gap-2 text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                                      <span className="font-mono" style={{ color: 'var(--text-primary)' }}>v{v.version}</span>
                                      <Badge color={ESTADO_COLOR[v.estado] || 'var(--text-secondary)'}>{v.estado}</Badge>
                                      <span>{v.created_at ? new Date(v.created_at).toLocaleString('es-MX') : ''}</span>
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>Sin versiones registradas.</p>
                              )}
                            </div>
                            <div>
                              <div className="flex items-center gap-1.5 mb-2 text-[11px] font-medium" style={{ color: 'var(--accent-gold)' }}>
                                <Tag size={12} /> Reclasificar documento
                              </div>
                              <div className="flex items-center gap-2">
                                <select
                                  value={tipoSugerido}
                                  onChange={(e) => setTipoSugerido(e.target.value)}
                                  className="h-7 rounded px-2 text-[11px] outline-hidden"
                                  style={inputStyle()}
                                >
                                  <option value="">Tipo sugerido...</option>
                                  {TIPOS_DOCUMENTO.map((t) => <option key={t} value={t}>{t}</option>)}
                                </select>
                                <button
                                  onClick={() => clasificar(d.id)}
                                  disabled={clasificando || !tipoSugerido}
                                  className="flex items-center gap-1 h-7 px-2 rounded text-[11px] font-medium disabled:opacity-40"
                                  style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}
                                >
                                  {clasificando ? <Loader2 size={11} className="animate-spin" /> : <CheckCircle2 size={11} />}
                                  Aplicar
                                </button>
                              </div>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Modal de subida */}
      {showUpload && (
        <div
          className="fixed inset-0 flex items-center justify-center z-50"
          style={{ background: 'rgba(0,0,0,0.6)' }}
          onClick={() => setShowUpload(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-[380px] rounded-lg p-4 space-y-3"
            style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-active)' }}
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">Subir documento al CDE</h3>
              <button onClick={() => setShowUpload(false)} style={{ color: 'var(--text-muted)' }}><X size={14} /></button>
            </div>
            <input
              type="file"
              onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
              className="w-full text-xs"
            />
            <div>
              <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>Tipo documental</label>
              <select value={uploadTipo} onChange={(e) => setUploadTipo(e.target.value)} className="w-full h-8 rounded px-2 text-xs outline-hidden" style={inputStyle()}>
                {TIPOS_DOCUMENTO.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <label className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
              <input type="checkbox" checked={uploadCifrar} onChange={(e) => setUploadCifrar(e.target.checked)} />
              Cifrar contenido en almacenamiento
            </label>
            <button
              onClick={subirDocumento}
              disabled={!uploadFile || subiendo}
              className="w-full h-9 rounded text-sm font-semibold flex items-center justify-center gap-2 disabled:opacity-50"
              style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}
            >
              {subiendo ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
              Subir
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md p-2.5" style={{ background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)' }}>
      <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{label}</div>
      <div className="text-base font-semibold mt-0.5" style={{ color: 'var(--accent-gold)' }}>{value}</div>
    </div>
  );
}
