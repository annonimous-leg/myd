import { useState } from 'react';
import ProgramacionObra from '../programacion-obra';
import { FileText } from 'lucide-react';
import { useExpedienteStore } from '@/stores/useExpedienteStore';
import TenderAutomationPanel from './components/TenderAutomationPanel';
import { abrirModulo } from '@/lib/navigation';

export default function LicitacionesObraApp() {
  const [seccion, setSeccion] = useState(() => new URLSearchParams(window.location.search).get('seccion') === 'cronograma' ? 'cronograma' : 'documentos');
  const expediente = useExpedienteStore((state) => state.expedienteActivo());

  if (!expediente) {
    return (
      <div className="workspace-surface h-full overflow-auto">
        <div className="workspace-welcome">
          <FileText size={28} aria-hidden style={{ color: 'var(--accent-gold)' }} />
          <h1>Tu obra comienza en Workspace</h1>
          <p>Reúne los documentos de la dependencia y prepara una propuesta con cantidades, precios y fuentes que puedas revisar.</p>
          <ol>
            <li><div><strong>Requisitos y plantillas</strong><p>Conserva los originales y adjunta la junta de aclaraciones si ya la tienes.</p></div></li>
            <li><div><strong>Datos de la obra y catálogo</strong><p>Define la dependencia y el contexto de la propuesta. Vincula tus precios antes de revisar el presupuesto.</p></div></li>
            <li><div><strong>Modelo y revisión técnica</strong><p>Carga tu IFC en BIM/CAD y continúa con cantidades, presupuesto y cronograma.</p></div></li>
          </ol>
          <button type="button" onClick={() => abrirModulo('proyectos')}>Elegir o crear obra</button>
        </div>
      </div>
    );
  }

  return (
    <div className="workspace-surface h-full overflow-auto p-4 sm:p-6">
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
