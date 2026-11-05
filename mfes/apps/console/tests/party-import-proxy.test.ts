import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { getToken } from 'next-auth/jwt';
import { POST } from '../app/api/party-import/route';
import { allowedPartyImportRequest } from '../app/lib/party-import-policy';
import { COMPANY, JOB, TEMPLATE } from './product-import-fixtures';
vi.mock('next-auth/jwt', () => ({ getToken: vi.fn() }));
const base = '/v1/companies/' + COMPANY;
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
function call(input: unknown, origin = 'http://console.test') {
  return POST(
    new NextRequest('http://console.test/api/party-import', {
      method: 'POST',
      headers: { origin, 'content-type': 'application/json' },
      body: JSON.stringify(input),
    }),
  );
}
it.each([
  'party',
  'supplier',
  'customer',
  'party_role',
  'party_address',
  'party_bank_account',
  'party_credit_policy',
])('allows an owner-native template for %s', (resource) => {
  expect(
    allowedPartyImportRequest(
      'accounting',
      'GET',
      base +
        '/import-templates/' +
        TEMPLATE +
        '?resource=' +
        resource +
        '&format=XLSX&action=CREATE',
    ),
  ).toBe(true);
});
it.each(['UPDATE', 'ACTIVATE', 'DEACTIVATE'])(
  'allows the %s template for existing party identities, what the plain party resource keeps',
  (action) => {
    expect(
      allowedPartyImportRequest(
        'accounting',
        'GET',
        base +
          '/import-templates/' +
          TEMPLATE +
          '?resource=party&format=XLSX&action=' +
          action,
      ),
    ).toBe(true);
  },
);
it('refuses a template action that is not a native import action', () => {
  expect(
    allowedPartyImportRequest(
      'accounting',
      'GET',
      base +
        '/import-templates/' +
        TEMPLATE +
        '?resource=customer&format=XLSX&action=DELETE',
    ),
  ).toBe(false);
});
it.each(['product_family', 'item', 'account', 'unknown'])(
  'rejects unrelated template resources %s',
  (resource) => {
    expect(
      allowedPartyImportRequest(
        'accounting',
        'GET',
        base + '/import-templates/' + TEMPLATE + '?resource=' + resource,
      ),
    ).toBe(false);
  },
);
it.each([
  'validate',
  'commit',
  'retry',
  'cancel',
  'revisions',
  'download-ticket',
  'download',
])('allows the native scoped import action %s', (action) => {
  expect(
    allowedPartyImportRequest(
      'accounting',
      'POST',
      base + '/import-jobs/' + JOB + '/' + action,
    ),
  ).toBe(true);
});
it.each([
  '/import-jobs?sort=-id',
  '/import-jobs?limit=201',
  '/import-jobs?limit=25&limit=50',
  '/import-jobs/' + JOB + '/commit?extra=1',
  '/parties',
  '/import-jobs/' + JOB + '/../import-definitions',
])('rejects unsupported paths and queries %s', (path) => {
  expect(allowedPartyImportRequest('accounting', 'GET', base + path)).toBe(
    false,
  );
});
it('does not forward Catalog or foreign-origin requests', async () => {
  expect(
    allowedPartyImportRequest('catalog', 'GET', base + '/import-definitions'),
  ).toBe(false);
  const fetch = vi.fn();
  vi.stubGlobal('fetch', fetch);
  expect(
    (
      await call(
        {
          service: 'accounting',
          method: 'GET',
          path: base + '/import-definitions',
        },
        'https://foreign.test',
      )
    ).status,
  ).toBe(403);
  expect(fetch).not.toHaveBeenCalled();
});
it('preserves large source bytes, company proof and the command key', async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(Response.json({ id: JOB }, { status: 201 }));
  vi.stubGlobal('fetch', fetch);
  const body = {
    template_id: TEMPLATE,
    files: [
      {
        filename: 'suppliers.csv',
        format: 'CSV',
        content_base64: 'a'.repeat(20000),
      },
    ],
  };
  const response = await call({
    service: 'accounting',
    method: 'POST',
    path: base + '/import-jobs',
    key: 'stable-party-request',
    body,
  });
  expect(response.status).toBe(201);
  expect(fetch.mock.calls[0]![0]).toBe(
    'http://gateway.test/accounting' + base + '/import-jobs',
  );
  expect(fetch.mock.calls[0]![1]).toMatchObject({
    body: JSON.stringify(body),
    headers: { 'Idempotency-Key': 'stable-party-request' },
  });
});
it('streams private reports and retains denied-download envelopes', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValue(
        new Response('private party report', {
          headers: { 'content-type': 'text/csv' },
        }),
      ),
  );
  const response = await call({
    service: 'accounting',
    method: 'POST',
    path: base + '/import-jobs/' + JOB + '/download',
    body: { token: 'private-ticket' },
  });
  expect(response.headers.get('Cache-Control')).toBe('no-store');
  expect(await response.text()).toBe('private party report');
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValue(
        Response.json(
          { error: { message: 'Access changed' } },
          { status: 403 },
        ),
      ),
  );
  expect(
    (
      await call({
        service: 'accounting',
        method: 'POST',
        path: base + '/import-jobs/' + JOB + '/download',
        body: { token: 'private-ticket' },
      })
    ).status,
  ).toBe(403);
});
