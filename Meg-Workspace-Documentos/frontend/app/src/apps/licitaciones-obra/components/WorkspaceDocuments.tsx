import { useEffect, useState, type FormEvent } from 'react';
import { ArrowLeft, Download, FileText } from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';
import type { WorkspaceDocumentSummary, WorkspaceDocumentDetail, WorkspaceDocumentRevision, WorkspaceEditor } from '@/lib/megalodon-client';
import { useAuthStore } from '@/stores/useAuthStore';
import './workspace-documents.css';
import ThemeControl from '@/components/ThemeControl';
import { useResolvedTheme } from '@/hooks/useResolvedTheme';
import { useConfirmation } from '@/components/useConfirmation';

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
  frozen?: boolean;
}

export default function WorkspaceDocuments({ tenderId, documents, onBack, onOpen, onVersion, frozen = false }: Props) {
  const { confirm, dialog } = useConfirmation();
  const role = useAuthStore(state => state.user?.role?.toLowerCase());
  const canEdit = role === 'tecnico' || role === 'admin' || role === 'superadmin';
  const dark = useResolvedTheme() === 'dark';
  const [selection, setSelectedId] = useState('');
  const [editor, setEditor] = useState<WorkspaceEditor | null>(null);
  const [plainDocument, setPlainDocument] = useState<WorkspaceDocumentDetail | null>(null);
  const [plainText, setPlainText] = useState('');
  const [history, setHistory] = useState<WorkspaceDocumentRevision[]>([]);
  const [historyPreview, setHistoryPreview] = useState<WorkspaceDocumentRevision | null>(null);
  const [notice, setNotice] = useState('');
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
  const fieldDirty = Object.keys(changed).length > 0;
  const plainDirty = Boolean(plainDocument && plainText !== plainDocument.content_text);
  const dirty = fieldDirty || plainDirty;
  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    const beforeNavigate = (event: Event) => {
      event.preventDefault();
      const navigate = (event as CustomEvent<{ navigate: () => void }>).detail.navigate;
      void confirm({ title: 'Hay cambios sin guardar', description: 'Guarda una nueva versión para conservar tus cambios, o descártalos para salir del documento.', action: 'Descartar y salir' })
        .then(accepted => { if (accepted) navigate(); });
    };
    window.addEventListener('beforeunload', beforeUnload);
    window.addEventListener('megalodon:before-navigate', beforeNavigate);
    return () => {
      window.removeEventListener('beforeunload', beforeUnload);
      window.removeEventListener('megalodon:before-navigate', beforeNavigate);
    };
  }, [dirty, confirm]);
  const locked = frozen || Boolean(editor?.locked || plainDocument?.locked);
  const currentVersion = plainDocument?.version ?? editor?.version;
  const initialValues = Object.fromEntries((editor?.fields ?? [])
    .filter(field => !field.read_only && field.value.trim())
    .map(field => [field.path, field.value]));
  const isTemplate = editor?.render_format === 'docx' || editor?.render_format === 'xlsx';
  const extension = extensions[editor?.media_type ?? ''];
  const needsFile = !editor?.file_available || (isTemplate && extension !== editor?.render_format);
  const hasBudgetFields = editor?.fields.some(field => field.read_only);
  const canRender = fieldDirty || hasBudgetFields || (needsFile && Object.keys(initialValues).length > 0);
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
    setPlainDocument(null);
    setPlainText('');
    setHistory([]);
    setHistoryPreview(null);
    setValues({});
    setNotice('');
    setError('');
    const load = async () => {
      // The server owns the format and revision. Never infer editability from
      // an annex name: text notes use the versioned PUT; mapped Office/PDF
      // annexes retain their template-aware render endpoint.
      const document = await megalodonClient.procurement.workspaceGetDocument(tenderId, selectedId);
      if (!active) return;
      if (document.media_type === 'text/plain') {
        const revisions = await megalodonClient.procurement.workspaceHistory(tenderId, selectedId);
        if (!active) return;
        setPlainDocument(document);
        setPlainText(document.content_text);
        setHistory(revisions);
      } else {
        const mappedEditor = await megalodonClient.procurement.workspaceEditor(tenderId, selectedId);
        if (active) loadFields(mappedEditor);
      }
    };
    void load().catch(err => { if (active) setError(String(err.message || err)); })
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

  async function leave(action: () => void) {
    if (!dirty || await confirm({ title: 'Hay cambios sin guardar', description: 'Guarda una nueva versión para conservar tus cambios, o descártalos para salir del documento.', action: 'Descartar y salir' })) action();
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
    if (saving || locked || !canEdit) return;
    if (plainDocument) {
      if (!plainDirty) return;
      setSaving(true);
      setError('');
      setNotice('');
      try {
        const saved = await megalodonClient.procurement.workspaceUpdateDocument(tenderId, plainDocument.id, {
          content_text: plainText,
          content_model: plainDocument.content_model,
          expected_row_version: plainDocument.row_version,
        });
        setPlainDocument(saved);
        setPlainText(saved.content_text);
        setHistoryPreview(null);
        onVersion(saved.id, saved.version);
        setNotice('Revisión ' + saved.version + ' guardada en el expediente con trazabilidad de autor.');
        // The server remains the source of truth for immutable history.
        const versions = await megalodonClient.procurement.workspaceHistory(tenderId, saved.id);
        setHistory(versions);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setSaving(false);
      }
      return;
    }
    if (!editor || !canRender) return;
    setSaving(true);
    setError('');
    setNotice('');
    try {
      const saved = await megalodonClient.procurement.workspaceRender(tenderId, editor.id, editor.row_version, fieldDirty ? changed : initialValues, editor.template_token);
      loadFields(saved);
      onVersion(saved.id, saved.version);
      setNotice('Revisión ' + saved.version + ' guardada y disponible para revisión.');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="workspace-docs" data-theme={dark ? 'dark' : 'light'} aria-label="Documentos del Workspace">
      {dialog}
      <header className="workspace-docs__header">
        <div>
          <button type="button" className="workspace-docs__back" onClick={() => leave(onBack)} disabled={saving}>
            <ArrowLeft size={15} aria-hidden /> Expediente
          </button>
          <h1>Documentos</h1>
          <p>Edición verificable, versiones trazables y anexos vinculados a su expediente.</p>
        </div>
        <div className="workspace-docs__actions">
          {currentVersion != null && <span className="workspace-docs__badge">{editor?.sha256 ? 'Borrador · ' : ''}Revisión {currentVersion}</span>}
          {locked && <span className="workspace-docs__badge" role="status">Solo lectura</span>}
          {currentPreview && <a href={currentPreview.url}
            download={`anexo-${editor!.id}-v${currentPreview.version}.${extension}`}>
            <Download size={15} aria-hidden /> Descargar revisión
          </a>}
          <ThemeControl />
        </div>
      </header>
      <div className="workspace-docs__grid">
        <nav aria-label="Anexos de la propuesta" className="workspace-docs__annexes">
          <h2>Anexos de la propuesta</h2>
          <p className="workspace-docs__eyebrow">EXPEDIENTE DOCUMENTAL</p>
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
          {plainDocument ? (
            <article className="workspace-docs__page" aria-label="Vista del documento guardado">
              <div className="workspace-docs__page-head">
                <span>{selected?.artifact_code}</span>
                <span>v{historyPreview?.version ?? plainDocument.version}</span>
              </div>
              <div className="workspace-docs__page-main">
                <span className="workspace-docs__eyebrow">NOTA DE TRABAJO · SIN FIRMA</span>
                <h2>{plainDocument.name}</h2>
                {plainDirty && !historyPreview && <p role="status">Hay cambios sin guardar. Esta vista muestra la última revisión registrada.</p>}
                {historyPreview && <p role="status">Consulta histórica de solo lectura. La revisión actual no cambia.</p>}
                <div className="workspace-docs__text-preview">{(historyPreview?.content_text ?? plainDocument.content_text) || 'Esta revisión todavía no tiene contenido.'}</div>
              </div>
              <div className="workspace-docs__page-foot">Megalodon · Workspace documental · {historyPreview ? 'Historial' : 'Revisión vigente'}</div>
            </article>
          ) : currentPreview && editor?.media_type === 'application/pdf' ?
            <iframe src={currentPreview.url} title={`Vista previa de ${selected?.name || 'anexo'}, revisión ${editor.version}`} /> :
            <div className="workspace-docs__empty">
              <FileText size={26} aria-hidden />
              <p>{fileError || (loading || (editor?.file_available && !currentPreview) ? 'Abriendo documento…' :
                currentPreview ? (extension === 'docx' ? 'Descarga el DOCX de esta revisión para abrirlo en Word.' : 'El archivo está listo para descargar.') :
                selected ? (editor?.fields.length ? (isTemplate ? 'Guarda los campos para generar el archivo de la plantilla.' : 'Guarda los campos editables para generar una vista previa.') : 'Esta revisión no tiene archivo disponible.') : 'Selecciona un anexo.')}</p>
            </div>}
        </div>
        <aside className="workspace-docs__fields">
          <h2>{plainDocument ? 'Edición del documento' : 'Campos del anexo'}</h2>
          <p className="workspace-docs__eyebrow">{plainDocument ? 'BORRADOR HUMANO · VERSIONADO' : 'FORMATO VINCULADO AL BACKEND'}</p>
          {error && <p role="alert" className="workspace-docs__alert">{error} <button type="button" onClick={() => leave(() => setReload(n => n + 1))}>Recargar desde servidor</button></p>}
          {notice && <p role="status" className="workspace-docs__success">{notice}</p>}
          {locked && <p>Este documento o expediente está bloqueado para edición.</p>}
          {plainDocument && (
            <>
              <form noValidate onSubmit={save}>
                <label>Contenido del documento
                  <textarea style={{ resize: 'none' }}
                    placeholder="Contenido editable del documento..."
                    aria-label="Contenido del documento"
                    rows={16}
                    value={plainText}
                    disabled={saving || locked || !canEdit}
                    onChange={event => { setPlainText(event.target.value); setNotice(''); }}
                  />
                </label>
                {plainDirty && <p role="status">Cambios pendientes: guarda una nueva revisión antes de salir.</p>}
                <p className="workspace-docs__hint">Las notas internas de texto se guardan en el backend. No son anexos oficiales firmados ni generan automáticamente un PDF.</p>
                {canEdit && <button type="submit" disabled={saving || locked || !plainDirty}>
                  {saving ? 'Guardando revisión…' : 'Guardar versión'}
                </button>}
              </form>
              <details className="workspace-docs__history">
                <summary>Historial de revisiones ({history.length})</summary>
                <div className="workspace-docs__history-entries">
                  {history.map(revision => (
                    <button type="button" key={revision.version}
                      aria-pressed={historyPreview?.version === revision.version}
                      onClick={() => setHistoryPreview(revision)}>
                      <strong>Ver revisión {revision.version}</strong>
                      <small>{revision.operation} · {new Date(revision.created_at).toLocaleString('es-MX')}</small>
                    </button>
                  ))}
                  {historyPreview && <button type="button" onClick={() => setHistoryPreview(null)}>Volver a la revisión vigente</button>}
                </div>
              </details>
            </>
          )}
          {editor && !editor.fields.length && <p>El perfil de este formato no tiene campos habilitados para editar. Adjunta el mapa oficial de la plantilla para habilitar campos verificables.</p>}
          {editor && editor.fields.length > 0 && (
            <form noValidate onSubmit={save}>
              {editor.fields.map(field => (
                <label key={field.path}>{field.label}{field.read_only && <small> · Presupuesto</small>}
                  {!isTemplate && field.path.startsWith('technical.') ?
                    <textarea style={{ resize: 'none' }} maxLength={field.max_length} value={values[field.path] ?? ''} rows={4}
                      disabled={saving || locked || !canEdit}
                      onChange={e => setValues(old => ({ ...old, [field.path]: e.target.value }))} /> :
                    <input readOnly={field.read_only} maxLength={field.max_length} value={values[field.path] ?? ''}
                      disabled={saving || locked || !canEdit}
                      onChange={e => setValues(old => ({ ...old, [field.path]: e.target.value }))} />}
                </label>
              ))}
              {dirty && <p role="status">El archivo disponible corresponde a la última revisión guardada.</p>}
              {canEdit && <button type="submit" disabled={saving || locked || !canRender}>
                {saving ? 'Generando archivo…' : isTemplate ? 'Guardar borrador' : 'Guardar y previsualizar'}
              </button>}
            </form>
          )}
        </aside>
      </div>
    </section>
  );
}
