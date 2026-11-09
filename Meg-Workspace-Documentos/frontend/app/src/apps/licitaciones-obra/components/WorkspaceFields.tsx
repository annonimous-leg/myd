import type { InputHTMLAttributes } from 'react';

export const inputClass = 'mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 disabled:opacity-60';
export const buttonClass = 'rounded-lg border border-emerald-700 bg-emerald-950/40 px-4 py-2 text-sm text-emerald-200 disabled:opacity-40';
export const writeRoles = ['admin', 'superadmin', 'revisor', 'tecnico'];
export const approveRoles = ['admin', 'superadmin', 'revisor'];

export function WorkspaceField({ label, ...props }: InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return <label className="block text-sm text-zinc-300">{label}<input {...props} className={inputClass} /></label>;
}

export function WorkspaceError({ message }: { message: string }) {
  return message ? <p role="alert" className="rounded-lg border border-red-800 bg-red-950/30 p-3 text-sm text-red-300">{message}</p> : null;
}
