import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { getToken } from 'next-auth/jwt';
import { POST } from '../app/api/company/route';

vi.mock('next-auth/jwt', () => ({ getToken: vi.fn() }));
const company = '00000000-0000-0000-0000-000000000001';

beforeEach(() => {
  vi.stubEnv('AUTH_URL', 'http://auth.test');
  vi.stubEnv('IDENTITY_URL', 'http://gateway.test');
  vi.stubEnv('ACCOUNTING_GATEWAY_URL', 'http://gateway.test/accounting');
  vi.stubEnv('CATALOG_GATEWAY_URL', 'http://gateway.test/catalog');
  vi.stubEnv('VOUCHERS_GATEWAY_URL', 'http://gateway.test/vouchers');
  vi.stubEnv('NEXTAUTH_SECRET', 'test');
  vi.mocked(getToken).mockResolvedValue({ accessToken: 'test-access', accessTokenExpires: Date.now() + 60000 });
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

it.each([
  ['accounting', 'POST', '/accounting-setup/initialize', 45000],
  ['accounting', 'POST', '/financial-setup/initialize', 45000],
  ['accounting', 'GET', '/financial-setup', 15000],
  ['accounting', 'POST', '/fiscal-years/generate', 15000],
  ['catalog', 'POST', '/pricing/bootstrap', 15000],
  ['vouchers', 'POST', '/voucher-type-defaults/bootstrap', 15000],
])('allows chart and books provisioning to finish without extending other setup budgets: %s %s %s', async (service, method, suffix, budget) => {
  const timeout = vi.spyOn(AbortSignal, 'timeout').mockReturnValue(new AbortController().signal);
  const fetch = vi.fn().mockResolvedValue(Response.json({ status: 'READY' }));
  vi.stubGlobal('fetch', fetch);
  const body = { country_code: 'IN' };
  const response = await POST(new NextRequest('http://console.test/api/company', {
    method: 'POST', headers: { origin: 'http://console.test', 'content-type': 'application/json' },
    body: JSON.stringify({ service, method, path: `/v1/companies/${company}${suffix}`, key: 'same-setup', body }),
  }));
  expect(response.status).toBe(200);
  expect(timeout).toHaveBeenCalledWith(budget);
  expect(fetch).toHaveBeenCalledOnce();
  expect(fetch).toHaveBeenCalledWith(`http://gateway.test/${service}/v1/companies/${company}${suffix}`,
    expect.objectContaining({ method, headers: expect.objectContaining({ 'Idempotency-Key': 'same-setup' }),
      ...(method === 'POST' ? { body: JSON.stringify(body) } : {}) }));
});
