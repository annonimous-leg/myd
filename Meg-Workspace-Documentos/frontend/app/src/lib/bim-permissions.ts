/** Presentation policy; API authorization remains authoritative. */
export function permisosBim(role?: string) {
  return {
    canWrite: ['admin', 'superadmin', 'tecnico', 'revisor'].includes(role || ''),
    canApprove: ['admin', 'superadmin', 'revisor'].includes(role || ''),
  };
}
