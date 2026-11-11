import { useEffect, useRef, useState } from 'react';
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogAction, AlertDialogCancel } from '@/components/ui/alert-dialog';

type Request = { title: string; description: string; action: string };

// One app-owned confirmation flow, including cancellation on unmount.
export function useConfirmation() {
  const [request, setRequest] = useState<Request | null>(null);
  const resolve = useRef<((accepted: boolean) => void) | null>(null);
  useEffect(() => () => { resolve.current?.(false); }, []);
  const finish = (accepted: boolean) => {
    resolve.current?.(accepted);
    resolve.current = null;
    setRequest(null);
  };
  return {
    confirm: (next: Request) => new Promise<boolean>(done => {
      resolve.current?.(false);
      resolve.current = done;
      setRequest(next);
    }),
    dialog: <AlertDialog open={Boolean(request)} onOpenChange={open => { if (!open) finish(false); }}>
      <AlertDialogContent className="max-h-[85dvh] overflow-y-auto">
        <AlertDialogHeader>
          <AlertDialogTitle>{request?.title}</AlertDialogTitle>
          <AlertDialogDescription className="whitespace-pre-wrap break-words text-left">{request?.description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={() => finish(false)}>Cancelar</AlertDialogCancel>
          <AlertDialogAction onClick={() => finish(true)}>{request?.action}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>,
  };
}
