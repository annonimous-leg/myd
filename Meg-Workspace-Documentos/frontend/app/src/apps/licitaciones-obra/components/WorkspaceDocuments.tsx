import { useEffect, useState, type FormEvent } from 'react';
import { ArrowLeft, Download, FileText, Moon, Sun } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';
import type { WorkspaceDocumentSummary, WorkspaceEditor } from '@/lib/megalodon-client';
import { useAuthStore } from '@/stores/useAuthStore';
import './workspace-documents.css';

const extensions: Record<string, string> = {
  'application/pdf': 'pdf',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
};

interface Props {
  tenderId: string;
  documents: WorkspaceDocumentSummary[];
  onBack: () => void;
  onOpen: (document: WorkspaceDocumentSummary) => void;
  onVersion: (id: string, version: number) => void;
}

export default function WorkspaceDocuments({ tenderId, documents, onBack, onOpen, onVersion }: Props) {
  const role = useAuthStore(state => state.user?.role?.toLowerCase());
  const canEdit = role === 'tecnico' || role === 'admin' || role === 'superadmin';
  const [dark, setDark] = useState(() => window.matchMedia('(prefers-color-scheme: dark)').matches);
  const [selection, setSelectedId] = useState('');
  const [editor, setEditor] = useState<WorkspaceEditor | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<{ url: string; version: number; documentId: string } | null>(null);
  const [error, setError] = useState('');
  const [fileError, setFileError] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [templates, setTemplates] = useState<{ artifact_code: string; name: string }[]>([]);
  const [reload, setReload] = useState(0);
  const selected = documents.find(doc => doc.id === selection) ?? documents[0];
  const selectedId = selected?.id;
  const changed = Object.fromEntries((editor?.fields ?? [])
    .filter(field => !field.read_only && values[field.path] !== field.value)
    .map(field => [field.path, values[field.path]]));
  const dirty = Object.keys(changed).length > 0;
  const initialValues = Object.fromEntries((editor?.fields ?? [])
    .filter(field => !field.read_only && field.value.trim())
    .map(field => [field.path, field.value]));
  const isTemplate = editor?.render_format === 'docx' || editor?.render_format === 'xlsx';
  const extension = extensions[editor?.media_type ?? ''];
  const needsFile = !editor?.file_available || (isTemplate && extension !== editor?.render_format);
  const hasBudgetFields = editor?.fields.some(field => field.read_only);
  const canRender = dirty || hasBudgetFields || (needsFile && Object.keys(initialValues).length > 0);
  const currentPreview = preview?.documentId === selectedId && preview.version === editor?.version ? preview : null;

  function loadFields(data: WorkspaceEditor) {
    setEditor(data);
    setValues(Object.fromEntries(data.fields.map(field => [field.path, field.value])));
  }

  useEffect(() => {
    if (!canEdit) return;
    let active = true;
    megalodonClient.procurement.workspaceDocumentTemplates(tenderId)
      .then(data => { if (active) setTemplates(data); })
      .catch(err => { if (active) setError(String(err.message || err)); });
    return () => { active = false; };
  }, [canEdit, tenderId]);

  useEffect(() => {
    if (!selectedId) return;
    let active = true;
    setLoading(true);
    setEditor(null);
    setValues({});
    setError('');
    megalodonClient.procurement.workspaceEditor(tenderId, selectedId)
      .then(data => { if (active) loadFields(data); })
      .catch(err => { if (active) setError(String(err.message || err)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [tenderId, selectedId, reload]);

  useEffect(() => {
    setPreview(null);
    setFileError('');
    if (!editor?.file_available) return;
    let active = true;
    let url: string | undefined;
    megalodonClient.procurement.workspaceRevisionFile(tenderId, editor.id, editor.version)
      .then(blob => {
        if (!active) return;
        url = URL.createObjectURL(blob);
        setPreview({ url, version: editor.version, documentId: editor.id });
      })
      .catch(err => { if (active) setFileError(String(err.message || err)); });
    return () => {
      active = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [tenderId, editor]);

  function leave(action: () => void) {
    if (!dirty || window.confirm('¿Salir sin guardar los cambios de este anexo?')) action();
  }

  async function openTemplate(template: { artifact_code: string; name: string }) {
    setSaving(true);
    setError('');
    try {
      const document = await megalodonClient.procurement.workspaceCreateDocument(tenderId, template);
      onOpen(document);
      setSelectedId(document.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editor || saving || editor.locked || !canEdit || !canRender) return;
    setSaving(true);
    setError('');
    try {
      const saved = await megalodonClient.procurement.workspaceRender(tenderId, editor.id, editor.row_version, dirty ? changed : initialValues, editor.template_token);
      loadFields(saved);
      onVersion(saved.id, saved.version);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="workspace-docs" data-theme={dark ? 'dark' : 'light'} aria-label="Documentos del Workspace">
      <header className="workspace-docs__header">
        <div>
          <button type="button" className="workspace-docs__back" onClick={() => leave(onBack)} disabled={saving}>
            <ArrowLeft size={15} aria-hidden /> Expediente
          </button>
          <h1>Documentos</h1>
          <p>Edita los campos del anexo y comprueba el archivo de esa revisión.</p>
        </div>
        <div className="workspace-docs__actions">
          {editor && <span className="workspace-docs__badge">{editor.sha256 ? 'Borrador · ' : ''}Revisión {editor.version}</span>}
          {currentPreview && <a href={currentPreview.url}
            download={`anexo-${editor!.id}-v${currentPreview.version}.${extension}`}>
            <Download size={15} aria-hidden /> Descargar revisión
          </a>}
          <button type="button" onClick={() => setDark(value => !value)}
            aria-label={dark ? 'Activar modo claro' : 'Activar modo oscuro'}>
            {dark ? <Sun size={16} aria-hidden /> : <Moon size={16} aria-hidden />}
          </button>
        </div>
      </header>
      <div className="workspace-docs__grid">
        <nav aria-label="Anexos de la propuesta" className="workspace-docs__annexes">
          <h2>Anexos de la propuesta</h2>
          {documents.length === 0 && templates.length === 0 && <p>Los anexos aparecerán aquí después de compilar el expediente.</p>}
          {documents.map(doc => (
            <button key={doc.id} type="button" aria-current={doc.id === selectedId ? 'true' : undefined}
              disabled={saving} onClick={() => leave(() => setSelectedId(doc.id))}>
              <span>{doc.artifact_code}</span>
              <span>{doc.name}</span>
              <small>v{doc.version}</small>
            </button>
          ))}
          {canEdit && templates.filter(template => !documents.some(doc => doc.artifact_code === template.artifact_code))
            .map(template => (
              <button key={template.artifact_code} type="button" disabled={saving}
                onClick={() => leave(() => { void openTemplate(template); })}>
                <span>{template.artifact_code}</span>
                <span>{template.name}</span>
                <small>Abrir plantilla</small>
              </button>
            ))}
        </nav>
        <div className="workspace-docs__preview" aria-label="Vista previa del archivo">
          {currentPreview && editor?.media_type === 'application/pdf' ?
            <iframe src={currentPreview.url} title={`Vista previa de ${selected?.name || 'anexo'}, revisión ${editor.version}`} /> :
            <div className="workspace-docs__empty">
              <FileText size={26} aria-hidden />
              <p>{fileError || (loading || (editor?.file_available && !currentPreview) ? 'Abriendo documento…' :
                currentPreview ? (extension === 'docx' ? 'Descarga el DOCX de esta revisión para abrirlo en Word.' : 'El archivo está listo para descargar.') :
                selected ? (editor?.fields.length ? (isTemplate ? 'Guarda los campos para generar el archivo de la plantilla.' : 'Guarda los campos editables para generar una vista previa.') : 'Esta revisión no tiene archivo disponible.') : 'Selecciona un anexo.')}</p>
            </div>}
        </div>
        <aside className="workspace-docs__fields">
          <h2>Campos del anexo</h2>
          {error && <p role="alert">{error} <button type="button" onClick={() => leave(() => setReload(n => n + 1))}>Recargar</button></p>}
          {editor?.locked && <p>Esta revisión está bloqueada.</p>}
          {editor && !editor.fields.length && <p>El perfil de este formato no tiene campos habilitados para editar.</p>}
          {editor && editor.fields.length > 0 && (
            <form onSubmit={save}>
              {editor.fields.map(field => (
                <label key={field.path}>{field.label}{field.read_only && <small> · Presupuesto</small>}
                  {!isTemplate && field.path.startsWith('technical.') ?
                    <textarea maxLength={field.max_length} value={values[field.path] ?? ''} rows={4}
                      disabled={saving || editor.locked || !canEdit}
                      onChange={e => setValues(old => ({ ...old, [field.path]: e.target.value }))} /> :
                    <input readOnly={field.read_only} maxLength={field.max_length} value={values[field.path] ?? ''}
                      disabled={saving || editor.locked || !canEdit}
                      onChange={e => setValues(old => ({ ...old, [field.path]: e.target.value }))} />}
                </label>
              ))}
              {dirty && <p role="status">El archivo disponible corresponde a la última revisión guardada.</p>}
              {canEdit && <button type="submit" disabled={saving || editor.locked || !canRender}>
                {saving ? 'Generando archivo…' : isTemplate ? 'Guardar borrador' : 'Guardar y previsualizar'}
              </button>}
            </form>
          )}
        </aside>
      </div>
    </section>
  );
}
