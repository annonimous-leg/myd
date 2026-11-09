import { createRequire } from 'node:module';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import assert from 'node:assert/strict';

const appRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(appRoot + '/package.json');
const { build } = require('esbuild');
test('a newly created project survives an earlier paginated identity lookup', async () => {
  let resolveDetail;
  const detail = new Promise(resolve => { resolveDetail = resolve; });
  globalThis.localStorage = {
    getItem: () => null,
    setItem: () => {},
    removeItem: () => {},
  };
  globalThis.__expedienteTestClient = { expedientes: {
    list: async () => [{ id: 'first' }],
    get: () => detail,
    create: async () => ({ id: 'new', titulo: 'New' }),
  } };
  const result = await build({
    entryPoints: [appRoot + '/src/stores/useExpedienteStore.ts'],
    bundle: true, write: false, platform: 'node', format: 'cjs',
    plugins: [{ name: 'review-client', setup(b) {
      b.onResolve({ filter: /^@\/lib\/api-client$/ }, () => ({ path: 'review-client', namespace: 'review' }));
      b.onLoad({ filter: /.*/, namespace: 'review' }, () => ({ contents: 'export const megalodonClient = globalThis.__expedienteTestClient;', loader: 'js' }));
      b.onResolve({ filter: /^@\/lib\/megalodon-client$/ }, () => ({ path: appRoot + '/src/lib/megalodon-client.ts' }));
    } }],
  });
  const module = { exports: {} };
  new Function('require', 'module', 'exports', result.outputFiles[0].text)(require, module, module.exports);
  const store = module.exports.useExpedienteStore;
  store.setState({ expedienteActivoId: 'old', expedientes: [{ id: 'old' }] });
  const load = store.getState().cargarExpedientes();
  await new Promise(resolve => setTimeout(resolve, 0));
  await store.getState().crearExpediente({ titulo: 'New' });
  resolveDetail({ id: 'old' });
  await load;
  const state = store.getState();
  assert.equal(state.expedienteActivoId, 'new');
  assert.equal(state.expedienteActivo()?.id, 'new', 'A completed create must survive the earlier identity lookup');

  let finishCreate;
  globalThis.__expedienteTestClient.expedientes.create = () => new Promise(resolve => { finishCreate = resolve; });
  const creating = store.getState().crearExpediente({ titulo: 'Late' });
  store.getState().limpiar();
  finishCreate({ id: 'late', titulo: 'Late' });
  await creating;
  assert.deepEqual(store.getState().expedientes, [], 'A response from the prior session must not restore its context');
  assert.equal(store.getState().expedienteActivoId, null);

});
