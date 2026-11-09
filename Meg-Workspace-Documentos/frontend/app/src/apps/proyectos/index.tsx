/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { useState, useEffect } from 'react';
import {
  FolderKanban, Plus, X, CheckCircle2, Loader2, AlertCircle,
  Building2, Calendar, DollarSign, FileStack,
} from 'lucide-react';
import { useExpedienteStore, type NuevoExpedienteInput } from '@/stores/useExpedienteStore';

const CAMPOS_REQUERIDOS: Array<{ key: keyof NuevoExpedienteInput; label: string; placeholder: string }> = [
  { key: 'titulo', label: 'Título del expediente', placeholder: 'Construcción de puente vehicular...' },
  { key: 'organo', label: 'Órgano', placeholder: 'Secretaría de Obras Públicas' },
  { key: 'unidad_administrativa', label: 'Unidad administrativa', placeholder: 'Dirección de Infraestructura' },
  { key: 'serie_documental', label: 'Serie documental', placeholder: '02100' },
  { key: 'subserie_documental', label: 'Subserie documental', placeholder: '02100-01' },
];

const CAMPOS_OPCIONALES: Array<{ key: keyof NuevoExpedienteInput; label: string; placeholder: string }> = [
  { key: 'proyecto_nombre', label: 'Nombre del proyecto', placeholder: '(opcional)' },
  { key: 'ubicacion_obra', label: 'Ubicación de la obra', placeholder: '(opcional)' },
  { key: 'responsable_tecnico', label: 'Responsable técnico', placeholder: '(opcional)' },
  { key: 'responsable_ejecutivo', label: 'Responsable ejecutivo', placeholder: '(opcional)' },
];

function NuevoExpedienteForm({ onClose }: { onClose: () => void }) {
  const crearExpediente = useExpedienteStore((s) => s.crearExpediente);
  const [form, setForm] = useState<Record<string, string>>({});
  const [monto, setMonto] = useState('');
  const [plazo, setPlazo] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState('');

  const set = (key: keyof NuevoExpedienteInput, value: string) => setForm((f) => ({ ...f, [key]: value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    for (const campo of CAMPOS_REQUERIDOS) {
      if (!form[campo.key]?.trim()) {
        setError(`"${campo.label}" es obligatorio`);
        return;
      }
    }

    setEnviando(true);
    try {
      await crearExpediente({
        titulo: form.titulo,
        organo: form.organo,
        unidad_administrativa: form.unidad_administrativa,
        serie_documental: form.serie_documental,
        subserie_documental: form.subserie_documental,
        descripcion: form.descripcion || undefined,
        proyecto_nombre: form.proyecto_nombre || undefined,
        ubicacion_obra: form.ubicacion_obra || undefined,
        responsable_tecnico: form.responsable_tecnico || undefined,
        responsable_ejecutivo: form.responsable_ejecutivo || undefined,
        monto_contrato: monto ? Number(monto) : undefined,
        plazo_dias: plazo ? Number(plazo) : undefined,
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo crear el expediente');
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div className="absolute inset-0 z-10 bg-[#030305]/80 flex items-center justify-center p-6">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-lg bg-[#0F0F16] border border-[#2A2A3E] rounded-lg p-5 max-h-[90%] overflow-y-auto"
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-[#E8E4DC]">Nuevo expediente</h3>
          <button type="button" onClick={onClose} className="text-[#8A8578] hover:text-[#E8E4DC]">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="space-y-3">
          {CAMPOS_REQUERIDOS.map((campo) => (
            <div key={campo.key}>
              <label htmlFor={`expediente-${campo.key}`} className="block text-[11px] text-[#8A8578] mb-1">{campo.label} *</label>
              <input
                id={`expediente-${campo.key}`}
                value={form[campo.key] || ''}
                onChange={(e) => set(campo.key, e.target.value)}
                placeholder={campo.placeholder}
                className="w-full h-9 bg-[#0A0A0F] border border-[#2A2A3E] rounded-md px-3 text-sm text-[#E8E4DC] outline-hidden focus:border-[#C9A84C]"
              />
            </div>
          ))}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] text-[#8A8578] mb-1">Monto del contrato</label>
              <input
                type="number"
                value={monto}
                onChange={(e) => setMonto(e.target.value)}
                placeholder="0.00"
                className="w-full h-9 bg-[#0A0A0F] border border-[#2A2A3E] rounded-md px-3 text-sm text-[#E8E4DC] outline-hidden focus:border-[#C9A84C]"
              />
            </div>
            <div>
              <label className="block text-[11px] text-[#8A8578] mb-1">Plazo (días)</label>
              <input
                type="number"
                value={plazo}
                onChange={(e) => setPlazo(e.target.value)}
                placeholder="0"
                className="w-full h-9 bg-[#0A0A0F] border border-[#2A2A3E] rounded-md px-3 text-sm text-[#E8E4DC] outline-hidden focus:border-[#C9A84C]"
              />
            </div>
          </div>

          {CAMPOS_OPCIONALES.map((campo) => (
            <div key={campo.key}>
              <label htmlFor={`expediente-${campo.key}`} className="block text-[11px] text-[#8A8578] mb-1">{campo.label}</label>
              <input
                id={`expediente-${campo.key}`}
                value={form[campo.key] || ''}
                onChange={(e) => set(campo.key, e.target.value)}
                placeholder={campo.placeholder}
                className="w-full h-9 bg-[#0A0A0F] border border-[#2A2A3E] rounded-md px-3 text-sm text-[#E8E4DC] outline-hidden focus:border-[#C9A84C]"
              />
            </div>
          ))}

          {error && <p className="text-xs text-[#B84A4A]">{error}</p>}

          <button
            type="submit"
            disabled={enviando}
            className="w-full h-10 bg-[#C9A84C] text-[#030305] font-semibold text-sm rounded-md hover:bg-[#D4B85A] transition-colors disabled:opacity-60 flex items-center justify-center gap-2"
          >
            {enviando ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
            Crear expediente
          </button>
        </div>
      </form>
    </div>
  );
}

export default function Proyectos() {
  const { expedientes, expedienteActivoId, isLoading, error, cargarExpedientes, setExpedienteActivo } =
    useExpedienteStore();
  const [mostrarForm, setMostrarForm] = useState(false);

  useEffect(() => {
    cargarExpedientes();
  }, []);

  return (
    <div className="h-full flex flex-col bg-[#0A0A0F] text-[#E8E4DC] relative">
      {mostrarForm && <NuevoExpedienteForm onClose={() => setMostrarForm(false)} />}

      <div className="flex items-center justify-between px-4 py-3 border-b border-[#2A2A3E]">
        <div className="flex items-center gap-2">
          <FolderKanban className="w-4 h-4 text-[#C9A84C]" />
          <h2 className="text-sm font-semibold">Proyectos / Expedientes</h2>
        </div>
        <button
          onClick={() => setMostrarForm(true)}
          className="flex items-center gap-1.5 h-8 px-3 bg-[#C9A84C] text-[#030305] text-xs font-semibold rounded-md hover:bg-[#D4B85A] transition-colors"
        >
          <Plus className="w-3.5 h-3.5" />
          Nuevo
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {isLoading && expedientes.length === 0 && (
          <div className="flex items-center gap-2 text-sm text-[#8A8578]">
            <Loader2 className="w-4 h-4 animate-spin" /> Cargando expedientes...
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 text-sm text-[#B84A4A] bg-[#B84A4A]/10 border border-[#B84A4A]/30 rounded-md p-3 mb-3">
            <AlertCircle className="w-4 h-4 shrink-0" /> {error}
          </div>
        )}

        {!isLoading && !error && expedientes.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center text-[#8A8578] gap-2">
            <FileStack className="w-10 h-10 opacity-40" />
            <p className="text-sm">Todavía no tienes expedientes.</p>
            <p className="text-xs">Crea el primero para empezar a usar costos, BIM y documentos.</p>
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {expedientes.map((exp) => {
            const activo = exp.id === expedienteActivoId;
            return (
              <button
                key={exp.id}
                onClick={() => setExpedienteActivo(exp.id)}
                className={`text-left p-3 rounded-lg border transition-colors ${
                  activo
                    ? 'border-[#C9A84C] bg-[#C9A84C]/10'
                    : 'border-[#2A2A3E] bg-[#12121A] hover:border-[#3A3A4E]'
                }`}
              >
                <div className="flex items-start justify-between gap-2 mb-1.5">
                  <span className="text-[10px] font-mono text-[#8A8578]">{exp.identificador}</span>
                  {activo && <CheckCircle2 className="w-4 h-4 text-[#C9A84C] shrink-0" />}
                </div>
                <h4 className="text-sm font-medium text-[#E8E4DC] mb-2 line-clamp-2">{exp.titulo}</h4>
                <div className="flex items-center gap-3 text-[11px] text-[#8A8578]">
                  <span className="flex items-center gap-1">
                    <Building2 className="w-3 h-3" /> {exp.estado}
                  </span>
                  {exp.monto_contrato != null && (
                    <span className="flex items-center gap-1">
                      <DollarSign className="w-3 h-3" />
                      {exp.monto_contrato.toLocaleString('es-MX', { style: 'currency', currency: 'MXN' })}
                    </span>
                  )}
                  <span className="flex items-center gap-1">
                    <Calendar className="w-3 h-3" /> {new Date(exp.created_at).toLocaleDateString('es-MX')}
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
