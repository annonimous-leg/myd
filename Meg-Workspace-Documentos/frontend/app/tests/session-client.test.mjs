import test from 'node:test';
import assert from 'node:assert/strict';
import { MegalodonClient } from '../src/lib/megalodon-client.ts';
const json = (data, status = 200) => new Response(JSON.stringify(data), {status, headers: {'Content-Type': 'application/json'}});
test('concurrent expired requests rotate the cookie once and retry', async (t) => {
 const client = new MegalodonClient('http://localhost:8000');
 let refreshes = 0, refreshed = false;
 t.mock.method(globalThis, 'fetch', async (url, config) => {
  assert.equal(config.credentials, 'include');
  assert.equal(config.headers.Authorization, undefined);
  if (url.endsWith('/auth/session/refresh')) {
   refreshes++; await new Promise(resolve => setTimeout(resolve, 10)); refreshed = true;
   return json({expires_in: 1800});
  }
  return refreshed ? json({id: 'user'}) : json({}, 401);
 });
 const results = await Promise.all([client.auth.me(), client.auth.me()]);
 assert.equal(refreshes, 1); assert.deepEqual(results.map(r => r.id), ['user', 'user']);
});
test('explicit bearer never refreshes an unrelated cookie', async (t) => {
 const client = new MegalodonClient('http://localhost:8000'); client.setToken('explicit-token');
 const calls = [];
 t.mock.method(globalThis, 'fetch', async (url, config) => {
  calls.push(url); assert.equal(config.headers.Authorization, 'Bearer explicit-token'); return json({}, 401);
 });
 await assert.rejects(client.auth.me()); assert.equal(calls.length, 1);
});
test('web login requests cookie contract and clears old bearer', async (t) => {
 const client = new MegalodonClient('http://localhost:8000'); client.setToken('old-token');
 t.mock.method(globalThis, 'fetch', async (url, config) => {
  assert.ok(url.endsWith('/auth/session/login')); assert.equal(config.headers.Authorization, undefined);
  assert.ok(config.body instanceof URLSearchParams); return json({expires_in: 1800});
 });
 assert.deepEqual(await client.auth.login('user@example.com', 'password'), {expires_in: 1800});
});
