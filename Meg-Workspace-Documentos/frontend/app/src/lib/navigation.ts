/** Navigate within the current command center without discarding context. */
export function abrirModulo(app: string, programaId?: string, seccion?: string) {
  const url = new URL(window.location.href);
  url.searchParams.set('app', app);
  if (seccion) url.searchParams.set('seccion', seccion);
  else url.searchParams.delete('seccion');
  if (programaId) url.searchParams.set('programa', programaId);
  else url.searchParams.delete('programa');
  window.history.pushState({}, '', url);
  window.dispatchEvent(new PopStateEvent('popstate'));
}
