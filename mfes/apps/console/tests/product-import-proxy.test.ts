import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { getToken } from 'next-auth/jwt';
import { POST } from '../app/api/product-import/route';
import { allowedProductImportRequest } from '../app/lib/product-import-policy';
import { COMPANY, JOB, TEMPLATE, ATTEMPT } from './product-import-fixtures';
vi.mock('next-auth/jwt', () => ({ getToken: vi.fn() }));
const base = '/v1/companies/' + COMPANY,
  token = vi.mocked(getToken);
beforeEach(() => {
  vi.stubEnv('AUTH_URL', 'http://auth.test');
  vi.stubEnv('NEXTAUTH_SECRET', 'test');
  vi.stubEnv('CATALOG_GATEWAY_URL', 'http://gateway.test/catalog');
  token.mockResolvedValue({
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
    new NextRequest('http://console.test/api/product-import', {
      method: 'POST',
      headers: { origin, 'content-type': 'application/json' },
      body: JSON.stringify(input),
    }),
  );
}
it.each([
  ['GET', '/import-definitions'],
  ['POST', '/import-templates'],
  [
    'GET',
    '/import-templates/' +
      TEMPLATE +
      '?resource=product_family&action=CREATE&format=XLSX',
  ],
  ['GET', '/import-jobs?limit=25&cursor=signed'],
  ['POST', '/import-jobs'],
  ['GET', '/simple-product-imports/' + JOB + '/progress'],
  ['GET', '/simple-product-imports/' + JOB + '/rows?limit=25'],
  ['POST', '/simple-product-imports/' + JOB + '/advance'],
  [
    'GET',
    '/import-templates/' +
      TEMPLATE +
      '?resource=simple_product_create&action=CREATE&format=XLSX',
  ],
  ['GET', '/import-jobs/' + JOB],
  ...[
    'validate',
    'commit',
    'retry',
    'revisions',
    'cancel',
    'download-ticket',
    'download',
  ].map((action) => ['POST', '/import-jobs/' + JOB + '/' + action]),
  ['GET', '/import-jobs/' + JOB + '/records?limit=200'],
  ['GET', '/import-jobs/' + JOB + '/history/attempts'],
  ['GET', '/import-jobs/' + JOB + '/attempts/' + ATTEMPT + '/issues?limit=25'],
])('allows only the native import operation %s %s', (method, path) => {
  expect(allowedProductImportRequest('catalog', method!, base + path)).toBe(
    true,
  );
});
it.each([
  '/simple-product-imports/' + JOB + '/advance?extra=1',
  '/simple-product-imports/' + JOB + '/rows?limit=201',
  '/simple-product-imports/' + JOB + '/rows?limit=25&limit=50',
  '/simple-product-imports/not-a-uuid/progress',
  '/import-jobs?limit=201',
  '/import-jobs?limit=0',
  '/import-jobs?limit=25&limit=50',
  '/import-jobs?sort=-id',
  '/import-jobs?company_id=' + COMPANY,
  '/import-jobs/' + JOB + '/commit?extra=1',
  '/import-jobs/' + JOB + '/history/unknown',
  '/import-jobs/not-a-uuid',
  '/import-templates/' + TEMPLATE + '?format=PDF',
  '/import-jobs/' + JOB + '/reveal',
  '/import-jobs/' + JOB + '/../import-definitions',
  '/import-jobs/%2e%2e/import-definitions',
  '/items',
])('rejects unrecognized import requests %s', (path) => {
  expect(allowedProductImportRequest('catalog', 'GET', base + path)).toBe(
    false,
  );
});
it('rejects foreign services, origins, methods and paths', () => {
  expect(
    allowedProductImportRequest(
      'identity',
      'GET',
      base + '/import-definitions',
    ),
  ).toBe(false);
  expect(
    allowedProductImportRequest(
      'catalog',
      'DELETE',
      base + '/import-jobs/' + JOB,
    ),
  ).toBe(false);
  expect(
    allowedProductImportRequest(
      'catalog',
      'GET',
      'https://evil.test' + base + '/import-definitions',
    ),
  ).toBe(false);
});
it('retains source bytes and command identity above the ordinary JSON body limit', async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(Response.json({ id: JOB }, { status: 201 }));
  vi.stubGlobal('fetch', fetch);
  const body = {
    template_id: TEMPLATE,
    files: [
      {
        filename: 'products.csv',
        format: 'CSV',
        content_base64: 'a'.repeat(20000),
      },
    ],
  };
  const response = await call({
    service: 'catalog',
    method: 'POST',
    path: base + '/import-jobs',
    key: 'stable-command',
    body,
  });
  expect(response.status).toBe(201);
  expect(fetch.mock.calls[0]![0]).toBe(
    'http://gateway.test/catalog' + base + '/import-jobs',
  );
  expect(fetch.mock.calls[0]![1]).toMatchObject({
    headers: {
      'Idempotency-Key': 'stable-command',
      Authorization: 'Bearer test-access',
    },
    body: JSON.stringify(body),
    redirect: 'error',
  });
});
it('rejects cross-origin requests before contacting a service', async () => {
  const fetch = vi.fn();
  vi.stubGlobal('fetch', fetch);
  expect(
    (
      await call(
        {
          service: 'catalog',
          method: 'GET',
          path: base + '/import-definitions',
        },
        'https://foreign.test',
      )
    ).status,
  ).toBe(403);
  expect(fetch).not.toHaveBeenCalled();
});
it('rejects oversized upload envelopes before contacting a service', async () => {
  const fetch = vi.fn();
  vi.stubGlobal('fetch', fetch);
  expect(
    (
      await call({
        service: 'catalog',
        method: 'POST',
        path: base + '/import-jobs',
        body: 'x'.repeat(13 * 1024 * 1024),
      })
    ).status,
  ).toBe(413);
  expect(fetch).not.toHaveBeenCalled();
});
it.each([
  'text/csv',
  'text/tab-separated-values',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
])('preserves private %s downloads', async (media) => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response('private file', {
        headers: {
          'content-type': media,
          'content-disposition': 'attachment; filename="products.csv"',
        },
      }),
    ),
  );
  const response = await call({
    service: 'catalog',
    method: 'GET',
    path:
      base +
      '/import-templates/' +
      TEMPLATE +
      '?format=CSV&resource=product_family',
  });
  expect(response.headers.get('Cache-Control')).toBe('no-store');
  expect(response.headers.get('X-Content-Type-Options')).toBe('nosniff');
  expect(await response.text()).toBe('private file');
});
it('keeps denied downloads as error envelopes', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValue(
        Response.json(
          { error: { message: 'Permission changed' } },
          { status: 403 },
        ),
      ),
  );
  const response = await call({
    service: 'catalog',
    method: 'POST',
    path: base + '/import-jobs/' + JOB + '/download',
    body: { token: 'signed' },
  });
  expect(response.status).toBe(403);
  expect((await response.json()).error.message).toBe('Permission changed');
});
