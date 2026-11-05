/**
 * The two company-context routes: the service proxy and the selection cookie writer.
 *
 * The cookie writer is the security-relevant one. A selection is only a hint, but a hint
 * naming a company the actor cannot reach would send every later page into a 403 — so the
 * company is verified against Identity *before* the cookie exists, and Identity's own refusal
 * (step-up, denial) is handed back untouched for the browser to act on.
 */
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { getToken } from 'next-auth/jwt';
import { POST as company } from '../app/api/company/route';
import { POST as context } from '../app/api/company-context/route';

vi.mock('next-auth/jwt', () => ({ getToken: vi.fn() }));
const token = vi.mocked(getToken);
const id = '01990000-0000-7000-8000-000000000001';
const year = '01990000-0000-7000-8000-000000000002';

beforeEach(() => {
  vi.stubEnv('AUTH_URL', 'http://console.test');
  vi.stubEnv('IDENTITY_URL', 'http://identity.test');
  vi.stubEnv('ACCOUNTING_GATEWAY_URL', 'http://gateway.test/accounting');
  vi.stubEnv('NEXTAUTH_SECRET', 'unit-test');
  token.mockResolvedValue({ accessToken: 'private-access', accessTokenExpires: Date.now() + 60_000 });
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

function call(
  route: (request: NextRequest) => Promise<Response>,
  path: string,
  input: unknown,
  { origin = 'http://console.test', cookie = '' } = {},
) {
  return route(
    new NextRequest('http://console.test' + path, {
      method: 'POST',
      headers: { origin, 'content-type': 'application/json', ...(cookie ? { cookie } : {}) },
      body: JSON.stringify(input),
    }),
  );
}

it('forwards an allowed company read with the server-side token and never the URL', async () => {
  const fetcher = vi.fn().mockResolvedValue(Response.json({ items: [] }));
  vi.stubGlobal('fetch', fetcher);

  const response = await call(company, '/api/company', { service: 'identity', method: 'GET', path: '/v1/session/companies?limit=50' });
  expect(response.status).toBe(200);
  expect(response.headers.get('Cache-Control')).toBe('no-store');
  expect(fetcher).toHaveBeenCalledWith(
    'http://identity.test/v1/session/companies?limit=50',
    expect.objectContaining({ redirect: 'error', headers: expect.objectContaining({ Authorization: 'Bearer private-access' }) }),
  );
});

it('keeps the accounting gateway path prefix instead of resolving it away', async () => {
  const fetcher = vi.fn().mockResolvedValue(Response.json({ items: [] }));
  vi.stubGlobal('fetch', fetcher);

  await call(company, '/api/company', { service: 'accounting', method: 'GET', path: `/v1/companies/${id}/fiscal-years` });
  expect(fetcher.mock.calls[0][0]).toBe(`http://gateway.test/accounting/v1/companies/${id}/fiscal-years`);
});

it('carries the idempotency key and the step-up proof for a company command', async () => {
  const fetcher = vi.fn().mockResolvedValue(Response.json({ id: year }));
  vi.stubGlobal('fetch', fetcher);

  await call(
    company,
    '/api/company',
    { service: 'accounting', method: 'POST', path: `/v1/companies/${id}/fiscal-years/generate`, body: { start_year: 2026 }, key: 'generate_1' },
    { cookie: `janso-step-up-${id}=private-proof` },
  );
  expect(fetcher.mock.calls[0][1]).toMatchObject({
    headers: expect.objectContaining({ 'Idempotency-Key': 'generate_1', 'X-Company-Step-Up': 'private-proof' }),
  });
});

it('refuses an unlisted route, a cross-origin call and an unauthenticated one', async () => {
  const fetcher = vi.fn();
  vi.stubGlobal('fetch', fetcher);

  expect((await call(company, '/api/company', { service: 'identity', method: 'DELETE', path: `/v1/companies/${id}` })).status).toBe(422);
  expect((await call(company, '/api/company', { service: 'identity', method: 'GET', path: '/v1/session' }, { origin: 'http://evil.test' })).status).toBe(403);
  token.mockResolvedValue(null);
  expect((await call(company, '/api/company', { service: 'identity', method: 'GET', path: '/v1/session' })).status).toBe(401);
  expect(fetcher).not.toHaveBeenCalled();
});

it('writes the selection only after Identity confirms the company', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(Response.json({ company: { id } })).mockResolvedValueOnce(Response.json({ id: year, company_id: id }));
  vi.stubGlobal('fetch', fetcher);

  const response = await call(context, '/api/company-context', { company: id, fiscalYear: year });
  expect(response.status).toBe(200);
  expect(fetcher.mock.calls[0][0]).toBe(`http://identity.test/v1/session?company_id=${id}`);
  expect(fetcher.mock.calls[1][0]).toBe(`http://gateway.test/accounting/v1/companies/${id}/fiscal-years/${year}`);

  const cookie = response.headers.getSetCookie().join('\n');
  expect(cookie).toContain(`janso-company=${id}`);
  expect(cookie).toContain(`janso-fiscal-year=${id}.${year}`);
  // The same posture auth's step-up route writes this cookie with.
  expect(cookie).toContain('HttpOnly');
  expect(cookie).toContain('SameSite=lax');
  expect(cookie).toContain('Max-Age=28800');
  expect(cookie).not.toContain('Secure');
});
it('does not write context cookies when Identity returns a different or withheld company', async () => {
  for (const body of [{ company: { id: year } }, { company: { id: 123 } }, { company: null }, {}]) {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(body)));
    const response = await call(context, '/api/company-context', { company: id });
    expect(response.status).toBe(502);
    expect(response.headers.getSetCookie()).toHaveLength(0);
  }
});
it('refuses an unavailable explicit company without changing either selection cookie', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({
    company: null, selected_company_id: id, selected_source: 'explicit', step_up_required: false,
  })));
  const response = await call(context, '/api/company-context', { company: id }, {
    cookie: `janso-company=${year}; janso-fiscal-year=${year}.${id}`,
  });
  expect(response.status).toBe(403);
  expect((await response.json()).error.code).toBe('company_unavailable');
  expect(response.headers.getSetCookie()).toHaveLength(0);
});
it('verifies the selected year within the company before writing either cookie', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json({ company: { id } })).mockResolvedValueOnce(Response.json({ error: { message: 'Year not available' } }, { status: 403 })));
  const denied = await call(context, '/api/company-context', { company: id, fiscalYear: year });
  expect(denied.status).toBe(403); expect(denied.headers.getSetCookie()).toHaveLength(0);
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json({ company: { id } })).mockResolvedValueOnce(Response.json({ id: year, company_id: year })));
  const wrongCompany = await call(context, '/api/company-context', { company: id, fiscalYear: year });
  expect(wrongCompany.status).toBe(502); expect(wrongCompany.headers.getSetCookie()).toHaveLength(0);
});

it('marks the cookies secure once the deployment is https, and shares the configured domain', async () => {
  vi.stubEnv('AUTH_URL', 'https://console.test');
  vi.stubEnv('AUTH_COOKIE_DOMAIN', '.janso.test');
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ company: { id } })));

  const response = await call(context, '/api/company-context', { company: id });
  const cookie = response.headers.getSetCookie().join('\n');
  expect(cookie).toContain('Secure');
  expect(cookie).toContain('Domain=.janso.test');
});

it('clears a stale year when the company is switched without naming one', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ company: { id } })));

  const response = await call(context, '/api/company-context', { company: id }, { cookie: `janso-fiscal-year=other.${year}` });
  const cookie = response.headers.getSetCookie().join('\n');
  expect(cookie).toMatch(/janso-fiscal-year=;[^\n]*Max-Age=0/);
});

it('hands back a step-up requirement without writing a cookie', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ error: { code: 'step_up_required' } }, { status: 403 })));

  const response = await call(context, '/api/company-context', { company: id });
  expect(response.status).toBe(403);
  expect((await response.json()).error.code).toBe('step_up_required');
  expect(response.headers.getSetCookie()).toHaveLength(0);
});

it('forwards an existing proof so a completed verification is not demanded twice', async () => {
  const fetcher = vi.fn().mockResolvedValue(Response.json({ company: { id } }));
  vi.stubGlobal('fetch', fetcher);

  await call(context, '/api/company-context', { company: id }, { cookie: `janso-step-up-${id}=private-proof` });
  expect(fetcher.mock.calls[0][1]).toMatchObject({ headers: expect.objectContaining({ 'X-Company-Step-Up': 'private-proof' }) });
});

it.each([
  [{ company: 'not-a-uuid' }],
  [{ company: null }],
  [{ fiscalYear: year }],
  [{ company: '01990000-0000-7000-8000-000000000001', fiscalYear: 'not-a-uuid' }],
  [{ company: '01990000-0000-7000-8000-000000000001', impersonate: true }],
])('refuses a selection it cannot validate: %j', async (input) => {
  const fetcher = vi.fn();
  vi.stubGlobal('fetch', fetcher);

  expect((await call(context, '/api/company-context', input)).status).toBe(422);
  expect(fetcher).not.toHaveBeenCalled();
});

it('refuses a cross-origin selection before authenticating it', async () => {
  const fetcher = vi.fn();
  vi.stubGlobal('fetch', fetcher);

  expect((await call(context, '/api/company-context', { company: id }, { origin: 'http://evil.test' })).status).toBe(403);
  expect(fetcher).not.toHaveBeenCalled();
});

it('reports an unavailable Identity as 503 rather than a broken selection', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
  expect((await call(context, '/api/company-context', { company: id })).status).toBe(503);

  vi.stubEnv('IDENTITY_URL', '');
  expect((await call(context, '/api/company-context', { company: id })).status).toBe(503);
});

it('refuses a path that would resolve outside the service prefix it was approved for', async () => {
  const fetcher = vi.fn();
  vi.stubGlobal('fetch', fetcher);

  /*
   * `%2e%2e` is a dot segment to the URL parser but not to a literal `'..'` check, so the
   * allowlist absorbs it harmlessly against a bare origin while the request would pop the
   * gateway's `/accounting` prefix. The proxy compares the two and refuses.
   */
  const escaped = `/v1/%2e%2e/%2e%2e/v1/companies/${id}/financial-setup/initialize`;
  const response = await call(company, '/api/company', { service: 'accounting', method: 'POST', path: escaped, body: {} });

  expect(response.status).toBe(422);
  expect(fetcher).not.toHaveBeenCalled();
});

it('still allows the same route when the service has no path prefix to pop', async () => {
  const fetcher = vi.fn().mockResolvedValue(Response.json({ items: [] }));
  vi.stubGlobal('fetch', fetcher);

  await call(company, '/api/company', { service: 'identity', method: 'GET', path: '/v1/session/companies?limit=50' });
  expect(fetcher).toHaveBeenCalledWith('http://identity.test/v1/session/companies?limit=50', expect.anything());
});
