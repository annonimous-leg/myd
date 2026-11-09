import { useState } from 'react';
import ProgramacionObra from '../programacion-obra';
import { FileText } from 'lucide-react';
import { useExpedienteStore } from '@/stores/useExpedienteStore';
import TenderAutomationPanel from './components/TenderAutomationPanel';

export default function LicitacionesObraApp() {
  const [seccion, setSeccion] = useState(() => new URLSearchParams(window.location.search).get('seccion') === 'cronograma' ? 'cronograma' : 'documentos');
  const expediente = useExpedienteStore((state) => state.expedienteActivo());

  if (!expediente) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="max-w-md rounded-2xl border border-zinc-700 bg-zinc-800/50 p-8 text-center">
          <FileText className="mx-auto mb-4 h-16 w-16 text-zinc-500" />
          <h2 className="mb-2 text-xl font-bold text-zinc-300">Sin expediente activo</h2>
          <p className="text-zinc-500">
            Selecciona un expediente en Proyectos para preparar la propuesta de esa obra.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto bg-[#0a0a0f] p-5 text-zinc-100">
      <nav aria-label="Secciones de Workspace" className="mb-4 flex gap-3">
        <button type="button" aria-pressed={seccion === 'documentos'} onClick={() => setSeccion('documentos')}>Propuesta y documentos</button>
        <button type="button" aria-pressed={seccion === 'cronograma'} onClick={() => setSeccion('cronograma')}>Cronograma de obra</button>
      </nav>
      {seccion === 'cronograma'
        ? <div className="min-h-[650px]"><ProgramacionObra key={expediente.id} workspace /></div>
        : <TenderAutomationPanel key={expediente.id} expedienteId={expediente.id} />}
    </div>
  );
}
