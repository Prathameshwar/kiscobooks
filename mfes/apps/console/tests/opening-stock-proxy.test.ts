import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { getToken } from 'next-auth/jwt';
import { POST } from '../app/api/opening-stock/route';
import { COMPANY, CONTROL } from './opening-stock-fixtures';
vi.mock('next-auth/jwt', () => ({ getToken: vi.fn() }));
beforeEach(() => {
  vi.stubEnv('AUTH_URL', 'http://auth.test');
  vi.stubEnv('NEXTAUTH_SECRET', 'test');
  vi.stubEnv('ACCOUNTING_GATEWAY_URL', 'http://gateway.test/accounting');
  vi.mocked(getToken).mockResolvedValue({
    accessToken: 'test-access',
    accessTokenExpires: Date.now() + 60000,
  });
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});
const base = `/v1/companies/${COMPANY}/stock/openings`;
const call = (body: unknown, origin = 'http://console.test') =>
  POST(
    new NextRequest('http://console.test/api/opening-stock', {
      method: 'POST',
      headers: { origin, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  );
it('rejects a foreign browser origin before requesting authority or services', async () => {
  const fetch = vi.fn();
  vi.stubGlobal('fetch', fetch);
  const response = await call(
    { service: 'accounting', method: 'GET', path: base + '/readiness' },
    'http://evil.test',
  );
  expect(response.status).toBe(403);
  expect(fetch).not.toHaveBeenCalled();
  expect(getToken).not.toHaveBeenCalled();
});
it('preserves the exact command and idempotency identity above normal body limits', async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(Response.json({ id: CONTROL }, { status: 201 }));
  vi.stubGlobal('fetch', fetch);
  const body = { reason: 'a'.repeat(20000) };
  const response = await call({
    service: 'accounting',
    method: 'POST',
    path: base,
    body,
    key: 'same-opening',
  });
  expect(response.status).toBe(201);
  expect(fetch.mock.calls[0]![1].body).toBe(JSON.stringify(body));
  expect(fetch.mock.calls[0]![1].headers['Idempotency-Key']).toBe(
    'same-opening',
  );
});
it('passes successful CSV through with private download headers', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValue(
        new Response('source,value\na,1.0', {
          headers: { 'Content-Type': 'text/csv' },
        }),
      ),
  );
  const response = await call({
    service: 'accounting',
    method: 'GET',
    path: `${base}/${CONTROL}/export?token=signed`,
  });
  expect(response.status).toBe(200);
  expect(response.headers.get('cache-control')).toBe('no-store');
  expect(response.headers.get('x-content-type-options')).toBe('nosniff');
  expect(await response.text()).toContain('source,value');
});
it('keeps denied exports as error envelopes', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValue(
        Response.json(
          { error: { message: 'Costs are protected.' } },
          { status: 403 },
        ),
      ),
  );
  const response = await call({
    service: 'accounting',
    method: 'GET',
    path: `${base}/${CONTROL}/export?token=signed`,
  });
  expect(response.status).toBe(403);
  expect(response.headers.get('content-type')).toContain('application/json');
});
it('rejects unsupported paths and oversize upload envelopes before upstream work', async () => {
  const fetch = vi.fn();
  vi.stubGlobal('fetch', fetch);
  expect(
    (
      await call({
        service: 'accounting',
        method: 'POST',
        path: '/v1/companies/' + COMPANY + '/stock/postings',
      })
    ).status,
  ).toBe(422);
  expect(
    (
      await call({
        service: 'accounting',
        method: 'POST',
        path: base,
        body: { content: 'a'.repeat(3 * 1024 * 1024 + 4096) },
      })
    ).status,
  ).toBe(413);
  expect(fetch).not.toHaveBeenCalled();
});
