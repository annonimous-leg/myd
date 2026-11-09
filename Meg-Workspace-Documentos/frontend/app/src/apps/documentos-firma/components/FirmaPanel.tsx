/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 * Unauthorized copying, modification, distribution, or use is prohibited
 * without prior written permission.
 */

import { useState } from 'react';
import {
  FileSignature, ShieldCheck, Link2, FileCheck2, ListChecks,
  Loader2, AlertCircle, CheckCircle2, Lock,
  type LucideIcon,
} from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';

type SubTab = 'firmar' | 'validar' | 'merkle' | 'cfdi' | 'formato';

const SUBTABS: { id: SubTab; label: string; icon: LucideIcon }[] = [
  { id: 'firmar', label: 'Firmar documento', icon: FileSignature },
  { id: 'validar', label: 'Validar firma', icon: ShieldCheck },
  { id: 'merkle', label: 'Merkle expediente', icon: Link2 },
  { id: 'cfdi', label: 'Sellar CFDI', icon: FileCheck2 },
  { id: 'formato', label: 'Formato requerido', icon: ListChecks },
];

function inputStyle(): React.CSSProperties {
  return { background: 'var(--surface-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-primary)' };
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-[11px] mb-1" style={{ color: 'var(--text-muted)' }}>{label}</label>
      {children}
    </div>
  );
}

function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className="w-full h-8 rounded px-2 text-xs outline-hidden" style={inputStyle()} />;
}

function ResultBox({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="rounded-md p-3 text-[11px] font-mono whitespace-pre-wrap break-all"
      style={{ background: 'var(--abyss)', border: '1px solid var(--success)55', color: 'var(--text-secondary)' }}
    >
      {children}
    </div>
  );
}

export default function FirmaPanel({ expedienteId }: { expedienteId: string }) {
  const [sub, setSub] = useState<SubTab>('firmar');

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-1 px-3 py-2 flex-wrap" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        {SUBTABS.map((t) => {
          const Icon = t.icon;
          const active = sub === t.id;
          return (
            <button
              key={t.id}
              onClick={() => setSub(t.id)}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-[11px] font-medium"
              style={{
                color: active ? 'var(--void)' : 'var(--text-secondary)',
                background: active ? 'var(--accent-gold)' : 'var(--surface-elevated)',
              }}
            >
              <Icon size={12} /> {t.label}
            </button>
          );
        })}
      </div>

      <div className="flex-1 overflow-auto p-4 max-w-xl">
        {sub === 'firmar' && <FirmarDocumento />}
        {sub === 'validar' && <ValidarFirma />}
        {sub === 'merkle' && <MerkleExpediente expedienteId={expedienteId} />}
        {sub === 'cfdi' && <SellarCFDI />}
        {sub === 'formato' && <FormatoRequerido />}
      </div>
    </div>
  );
}

function FirmarDocumento() {
  const [documentoId, setDocumentoId] = useState('');
  const [cer, setCer] = useState<File | null>(null);
  const [key, setKey] = useState<File | null>(null);
  const [password, setPassword] = useState('');
  const [razon, setRazon] = useState('Firma de documento de obra pública');
  const [ubicacion, setUbicacion] = useState('México');
  const [usarTsa, setUsarTsa] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [resultado, setResultado] = useState<any>(null);

  const firmar = async () => {
    if (!documentoId || !cer || !key || !password) return;
    setBusy(true); setError(''); setResultado(null);
    try {
      const r = await megalodonClient.firma.firmarDocumento(documentoId, cer, key, password, razon, ubicacion, usarTsa);
      setResultado(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo firmar el documento');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
        Firma electrónica real (XAdES/PAdES) con sello de tiempo RFC 3161 opcional. Requiere el certificado (.cer)
        y la llave privada (.key) del firmante.
      </p>
      <Field label="ID del documento">
        <TextInput value={documentoId} onChange={(e) => setDocumentoId(e.target.value)} placeholder="UUID del documento en el CDE" />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Certificado (.cer)">
          <input type="file" accept=".cer" onChange={(e) => setCer(e.target.files?.[0] || null)} className="w-full text-xs" />
        </Field>
        <Field label="Llave privada (.key)">
          <input type="file" accept=".key" onChange={(e) => setKey(e.target.files?.[0] || null)} className="w-full text-xs" />
        </Field>
      </div>
      <Field label="Contraseña de la llave">
        <TextInput type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Razón"><TextInput value={razon} onChange={(e) => setRazon(e.target.value)} /></Field>
        <Field label="Ubicación"><TextInput value={ubicacion} onChange={(e) => setUbicacion(e.target.value)} /></Field>
      </div>
      <label className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
        <input type="checkbox" checked={usarTsa} onChange={(e) => setUsarTsa(e.target.checked)} />
        Sellar con estampa de tiempo (TSA / RFC 3161)
      </label>
      {error && <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--danger)' }}><AlertCircle size={13} />{error}</div>}
      <button
        onClick={firmar}
        disabled={busy || !documentoId || !cer || !key || !password}
        className="flex items-center gap-2 h-9 px-4 rounded text-sm font-semibold disabled:opacity-40"
        style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}
      >
        {busy ? <Loader2 size={14} className="animate-spin" /> : <FileSignature size={14} />}
        Firmar documento
      </button>
      {resultado && (
        <div className="flex items-start gap-2 text-xs" style={{ color: 'var(--success)' }}>
          <CheckCircle2 size={14} className="mt-0.5 shrink-0" />
          <ResultBox>{JSON.stringify(resultado, null, 2)}</ResultBox>
        </div>
      )}
    </div>
  );
}

function ValidarFirma() {
  const [documentoId, setDocumentoId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [resultado, setResultado] = useState<any>(null);

  const validar = async () => {
    if (!documentoId) return;
    setBusy(true); setError(''); setResultado(null);
    try {
      setResultado(await megalodonClient.firma.validarFirma(documentoId));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo validar la firma');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
        Verifica la validez criptográfica de la firma de un documento ya firmado.
      </p>
      <Field label="ID del documento">
        <TextInput value={documentoId} onChange={(e) => setDocumentoId(e.target.value)} placeholder="UUID del documento firmado" />
      </Field>
      {error && <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--danger)' }}><AlertCircle size={13} />{error}</div>}
      <button
        onClick={validar}
        disabled={busy || !documentoId}
        className="flex items-center gap-2 h-9 px-4 rounded text-sm font-semibold disabled:opacity-40"
        style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}
      >
        {busy ? <Loader2 size={14} className="animate-spin" /> : <ShieldCheck size={14} />}
        Validar firma
      </button>
      {resultado && <ResultBox>{JSON.stringify(resultado, null, 2)}</ResultBox>}
    </div>
  );
}

function MerkleExpediente({ expedienteId }: { expedienteId: string }) {
  const [cer, setCer] = useState<File | null>(null);
  const [key, setKey] = useState<File | null>(null);
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [resultado, setResultado] = useState<any>(null);

  const firmarMerkle = async () => {
    if (!cer || !key || !password) return;
    setBusy(true); setError(''); setResultado(null);
    try {
      setResultado(await megalodonClient.firma.firmarMerkle(expedienteId, cer, key, password));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo firmar el Merkle root del expediente');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
        Calcula y firma el <b>Merkle root</b> de todos los documentos del expediente activo — sella
        criptográficamente el estado completo del expediente en un momento dado, útil para auditoría probatoria.
      </p>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Certificado (.cer)">
          <input type="file" accept=".cer" onChange={(e) => setCer(e.target.files?.[0] || null)} className="w-full text-xs" />
        </Field>
        <Field label="Llave privada (.key)">
          <input type="file" accept=".key" onChange={(e) => setKey(e.target.files?.[0] || null)} className="w-full text-xs" />
        </Field>
      </div>
      <Field label="Contraseña de la llave">
        <TextInput type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
      </Field>
      {error && <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--danger)' }}><AlertCircle size={13} />{error}</div>}
      <button
        onClick={firmarMerkle}
        disabled={busy || !cer || !key || !password}
        className="flex items-center gap-2 h-9 px-4 rounded text-sm font-semibold disabled:opacity-40"
        style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}
      >
        {busy ? <Loader2 size={14} className="animate-spin" /> : <Link2 size={14} />}
        Firmar Merkle del expediente
      </button>
      {resultado && <ResultBox>{JSON.stringify(resultado, null, 2)}</ResultBox>}
    </div>
  );
}

function SellarCFDI() {
  const [xml, setXml] = useState<File | null>(null);
  const [cer, setCer] = useState<File | null>(null);
  const [key, setKey] = useState<File | null>(null);
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [resultado, setResultado] = useState<{ xml_sellado: string; cadena_original: string; sello_digital: string; no_certificado: string; nota: string } | null>(null);

  const sellar = async () => {
    if (!xml || !cer || !key || !password) return;
    setBusy(true); setError(''); setResultado(null);
    try {
      setResultado(await megalodonClient.firma.sellarCFDI(xml, cer, key, password));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo sellar el CFDI');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
        Sella (no timbra) un CFDI 4.0: deja el XML listo para enviarlo a un PAC autorizado por el SAT. El timbrado
        fiscal en sí requiere ese PAC — este paso sólo genera el sello digital.
      </p>
      <Field label="XML del CFDI">
        <input type="file" accept=".xml" onChange={(e) => setXml(e.target.files?.[0] || null)} className="w-full text-xs" />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Certificado (.cer)">
          <input type="file" accept=".cer" onChange={(e) => setCer(e.target.files?.[0] || null)} className="w-full text-xs" />
        </Field>
        <Field label="Llave privada (.key)">
          <input type="file" accept=".key" onChange={(e) => setKey(e.target.files?.[0] || null)} className="w-full text-xs" />
        </Field>
      </div>
      <Field label="Contraseña de la llave">
        <TextInput type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
      </Field>
      {error && <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--danger)' }}><AlertCircle size={13} />{error}</div>}
      <button
        onClick={sellar}
        disabled={busy || !xml || !cer || !key || !password}
        className="flex items-center gap-2 h-9 px-4 rounded text-sm font-semibold disabled:opacity-40"
        style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}
      >
        {busy ? <Loader2 size={14} className="animate-spin" /> : <FileCheck2 size={14} />}
        Sellar CFDI
      </button>
      {resultado && (
        <div className="space-y-2">
          <p className="text-[11px]" style={{ color: 'var(--amber)' }}>{resultado.nota}</p>
          <Field label="No. de certificado"><ResultBox>{resultado.no_certificado}</ResultBox></Field>
          <Field label="Sello digital"><ResultBox>{resultado.sello_digital}</ResultBox></Field>
          <Field label="Cadena original"><ResultBox>{resultado.cadena_original}</ResultBox></Field>
        </div>
      )}
    </div>
  );
}

const PLATAFORMAS = ['compranet', 'compras_mx', 'imss', 'infonavit', 'seop_generico', 'cfe', 'pemex', 'personalizada'] as const;

function FormatoRequerido() {
  const [plataforma, setPlataforma] = useState<typeof PLATAFORMAS[number]>('compranet');
  const [tipoDocumento, setTipoDocumento] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [resultado, setResultado] = useState<{ plataforma: string; tipo_documento: string; formato_requerido: string } | null>(null);

  const consultar = async () => {
    if (!tipoDocumento) return;
    setBusy(true); setError(''); setResultado(null);
    try {
      setResultado(await megalodonClient.firma.formatoRequerido(plataforma, tipoDocumento));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo consultar el formato requerido');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
        Consulta qué formato de firma (XAdES-EPES / PAdES-basic / PAdES-LT) exige cada plataforma gubernamental
        según el tipo de documento — evita rechazos por formato incorrecto antes de firmar.
      </p>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Plataforma">
          <select value={plataforma} onChange={(e) => setPlataforma(e.target.value as typeof plataforma)} className="w-full h-8 rounded px-2 text-xs outline-hidden" style={inputStyle()}>
            {PLATAFORMAS.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </Field>
        <Field label="Tipo de documento">
          <TextInput value={tipoDocumento} onChange={(e) => setTipoDocumento(e.target.value)} placeholder="p. ej. CONTRATO" />
        </Field>
      </div>
      {error && <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--danger)' }}><AlertCircle size={13} />{error}</div>}
      <button
        onClick={consultar}
        disabled={busy || !tipoDocumento}
        className="flex items-center gap-2 h-9 px-4 rounded text-sm font-semibold disabled:opacity-40"
        style={{ background: 'var(--accent-gold)', color: 'var(--void)' }}
      >
        {busy ? <Loader2 size={14} className="animate-spin" /> : <Lock size={14} />}
        Consultar formato
      </button>
      {resultado && (
        <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--success)' }}>
          <CheckCircle2 size={14} /> Formato requerido: <b>{resultado.formato_requerido}</b>
        </div>
      )}
    </div>
  );
}
