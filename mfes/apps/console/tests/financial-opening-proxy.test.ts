import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { getToken } from 'next-auth/jwt';
import { POST } from '../app/api/financial-opening/route';
import { BATCH, COMPANY } from './financial-opening-fixtures';
vi.mock('next-auth/jwt', () => ({ getToken: vi.fn() }));
beforeEach(() => {
  vi.stubEnv('AUTH_URL', 'http://auth.test'); vi.stubEnv('NEXTAUTH_SECRET', 'test'); vi.stubEnv('ACCOUNTING_GATEWAY_URL', 'http://gateway.test/accounting');
  vi.mocked(getToken).mockResolvedValue({ accessToken: 'test-access', accessTokenExpires: Date.now() + 60000 });
});
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); vi.clearAllMocks(); });
const root = `/v1/companies/${COMPANY}/opening-batches`;
const call = (body: unknown, origin = 'http://console.test') => POST(new NextRequest('http://console.test/api/financial-opening', { method: 'POST', headers: { origin, 'Content-Type': 'application/json' }, body: JSON.stringify(body) }));
it('rejects foreign origins before requesting session authority', async () => {
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
  expect((await call({ service: 'accounting', method: 'GET', path: root + '/readiness' }, 'http://evil.test')).status).toBe(403);
  expect(fetch).not.toHaveBeenCalled(); expect(getToken).not.toHaveBeenCalled();
});
it('preserves the exact reviewed body and idempotency key across the bounded proxy', async () => {
  const fetch = vi.fn().mockResolvedValue(Response.json({ id: BATCH }, { status: 201 })); vi.stubGlobal('fetch', fetch);
  const body = { reason: 'a'.repeat(20000) };
  expect((await call({ service: 'accounting', method: 'POST', path: root + '/workspaces', body, key: 'opening-same-key' })).status).toBe(201);
  expect(fetch.mock.calls[0]![0]).toBe('http://gateway.test/accounting' + root + '/workspaces');
  expect(fetch.mock.calls[0]![1].body).toBe(JSON.stringify(body));
  expect(fetch.mock.calls[0]![1].headers['Idempotency-Key']).toBe('opening-same-key');
});
it('keeps downloads private and denied downloads as error envelopes', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(new Response('source,value\na,100', { headers: { 'Content-Type': 'text/csv' } })).mockResolvedValueOnce(Response.json({ error: { message: 'Export access denied.' } }, { status: 403 })); vi.stubGlobal('fetch', fetch);
  const payload = { service: 'accounting', method: 'GET', path: `${root}/workspaces/${BATCH}/export?token=signed` };
  const result = await call(payload);
  expect(result.headers.get('cache-control')).toBe('no-store'); expect(result.headers.get('x-content-type-options')).toBe('nosniff');
  const denied = await call(payload); expect(denied.status).toBe(403); expect(await denied.json()).toMatchObject({ error: { message: 'Export access denied.' } });
});
it('refuses normalized path escapes and mutation queries without calling services', async () => {
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
  for (const path of [root + '/%2e%2e/journals', root + '/workspaces?approve=true']) expect((await call({ service: 'accounting', method: 'POST', path })).status).toBe(422);
  expect(fetch).not.toHaveBeenCalled();
});
