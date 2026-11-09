import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuthStore } from '@/stores/useAuthStore';
import { useAppRegistry } from '@/stores/useAppRegistry';
import { megalodonClient } from '@/lib/api-client';

type Check = { name: string; state: 'pending' | 'ok' | 'failed'; detail?: string };

export default function BootSequence() {
  const setBootComplete = useAuthStore(s => s.setBootComplete);
  const apps = useAppRegistry(s => s.apps);
  const [checks, setChecks] = useState<Check[]>([
    { name: 'API / health', state: 'pending' },
    { name: 'API / ready · DB/Redis', state: 'pending' },
    { name: 'Entitlements / tenant', state: 'pending' },
    { name: 'Tezcatlipoca telemetry', state: 'pending' },
    { name: `App registry (${apps.length} apps)`, state: 'pending' },
  ]);
  const [error, setError] = useState<string | null>(null);
  const [fadeOut, setFadeOut] = useState(false);

  const update = (index: number, state: Check['state'], detail?: string) => {
    setChecks(prev => prev.map((item, i) => i === index ? { ...item, state, detail } : item));
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await megalodonClient.health.live();
        if (cancelled) return;
        update(0, 'ok');

        const ready = await megalodonClient.health.ready();
        if (cancelled) return;
        if (ready?.status !== 'ready') {
          update(1, 'failed', JSON.stringify(ready));
          throw new Error('El backend todavía no está listo. Revisa DB y Redis.');
        }
        update(1, 'ok');

        await megalodonClient.entitlements.miPlan();
        if (cancelled) return;
        update(2, 'ok');

        try {
          await megalodonClient.tezcatlipoca.telemetry();
          if (cancelled) return;
          update(3, 'ok');
        } catch (exc) {
          if (cancelled) return;
          const detail = exc instanceof Error ? exc.message : 'Servicio opcional no disponible';
          update(3, 'failed', detail);
        }
        update(4, 'ok');
        setTimeout(() => { if (!cancelled) { setFadeOut(true); setBootComplete(true); } }, 300);
      } catch (exc) {
        if (cancelled) return;
        const message = exc instanceof Error ? exc.message : 'No se pudo verificar el estado del sistema.';
        setError(message);
        setChecks(prev => prev.map(item => item.state === 'pending' ? { ...item, state: 'failed', detail: message } : item));
      }
    })();
    return () => { cancelled = true; };
  }, [setBootComplete, apps.length]);

  const retry = () => window.location.reload();

  return (
    <AnimatePresence>
      {!fadeOut && (
        <motion.div exit={{ opacity: 0 }} transition={{ duration: 0.35 }} className="fixed inset-0 z-50000 bg-[#030305] flex flex-col items-start justify-center" style={{ paddingLeft: '15%' }}>
          <div className="max-w-[780px] w-full">
            <div className="font-mono text-sm space-y-1.5 min-h-[240px]">
              {checks.map((check) => (
                <div key={check.name} className="flex items-start gap-2">
                  <span className={check.state === 'ok' ? 'text-[#5A9E6F]' : check.state === 'failed' ? 'text-[#D45A5A]' : 'text-[#C9A84C]'}>
                    [{check.state === 'ok' ? ' OK ' : check.state === 'failed' ? 'FAIL' : ' ...'}]
                  </span>
                  <div>
                    <div className="text-[#8A8578]">{check.name}</div>
                    {check.detail && <div className="text-[11px] text-[#D45A5A] max-w-[680px] wrap-break-word">{check.detail}</div>}
                  </div>
                </div>
              ))}
            </div>
            {error && (
              <div className="mt-5 flex items-center gap-3">
                <button onClick={retry} className="px-4 py-2 rounded bg-[#C9A84C] text-[#030305] text-xs font-semibold">Reintentar verificaciones</button>
                <span className="text-[11px] text-[#8A8578]">El acceso al shell se mantiene bloqueado hasta que el backend reporte READY.</span>
              </div>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
