import { useCallback, useEffect, useRef, useState } from 'react';
import { megalodonClient } from '@/lib/api-client';
import type { LicitacionWorkspace } from '@/lib/licitacion-types';

/** Ignore responses from an earlier expedition, including a late mutation reload. */
export function useWorkspace(expedienteId: string) {
  const [loaded, setLoaded] = useState<{ id: string; data: LicitacionWorkspace } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const generation = useRef(0);
  const reload = useCallback(async () => {
    const ticket = ++generation.current;
    setLoading(true); setError('');
    try {
      const data = await megalodonClient.licitacionesObra.workspace(expedienteId);
      if (ticket === generation.current) setLoaded({ id: expedienteId, data });
    } catch (e) {
      if (ticket === generation.current) { setLoaded(null); setError((e as Error).message); }
    } finally { if (ticket === generation.current) setLoading(false); }
  }, [expedienteId]);
  useEffect(() => { void reload(); return () => { generation.current += 1; }; }, [reload]);
  return { workspace: loaded?.id === expedienteId ? loaded.data : null, loading, error, reload };
}
