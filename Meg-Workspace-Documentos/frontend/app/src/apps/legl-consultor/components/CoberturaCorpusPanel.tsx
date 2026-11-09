import { useEffect, useState } from 'react';
import { megalodonClient } from '@/lib/api-client';
import type { CoberturaCorpus } from '@/lib/megalodon-client';

export default function CoberturaCorpusPanel() {
  const [cobertura, setCobertura] = useState<CoberturaCorpus | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let cancelado = false;
    void megalodonClient.legal.cobertura().then(data => {
      if (!cancelado) setCobertura(data);
    }).catch(e => {
      if (!cancelado) setError(e instanceof Error ? e.message : 'No se pudo comprobar la cobertura.');
    });
    return () => { cancelado = true; };
  }, []);

  return <details className="px-5 py-2 border-b border-zinc-800 text-xs text-zinc-400 shrink-0 max-h-52 overflow-y-auto">
    <summary className="cursor-pointer">{cobertura ? `${cobertura.total_articulos_consultables} artículos consultables · ver cobertura` : 'Cobertura del corpus'}</summary>
    {error && <p role="alert" className="mt-2 text-red-400">{error}</p>}
    {!cobertura && !error && <p role="status" className="mt-2">Comprobando archivos…</p>}
    {cobertura && <div className="space-y-2 mt-2">
      <p>{cobertura.alcance}. Vigencia normativa pendiente de contrastar con fuentes oficiales.</p>
      <ul>{cobertura.documentos.map(d => <li key={d.nombre} className="mb-2">
        {d.nombre}: {d.articulos_consultables} artículos consultables.
        {!d.conteo_declarado_coincide && <span> El conteo declarado ({d.conteo_declarado}) difiere del archivo.</span>}
        {d.numeros_no_segmentados.length > 0 && <span> Numeración sin segmento: {d.numeros_no_segmentados.join(', ')}. Revisar extracción o derogaciones.</span>}
      </li>)}</ul>
      {cobertura.documentos_sin_articulos.length > 0 && <p>Documentos sin artículos consultables: {cobertura.documentos_sin_articulos.join(', ')}.</p>}
      <p className="break-all text-[10px]">Huella del corpus: {cobertura.sha256}</p>
    </div>}
  </details>;
}
