import { afterEach, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { getToken } from 'next-auth/jwt';
import { POST } from '../app/api/purchase-print/route';

vi.mock('next-auth/jwt', () => ({ getToken: vi.fn() }));
const id = '01990000-0000-7000-8000-000000000001';
const path = `/v1/companies/${id}/voucher-print-jobs/${id}/download?token=signed`;
const call = (origin = 'http://localhost:4320') => POST(new NextRequest('http://localhost:4320/api/purchase-print', {
  method: 'POST', headers: { Origin: origin, 'Content-Type': 'application/json' },
  body: JSON.stringify({ service: 'vouchers', method: 'GET', path }),
}));
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.resetAllMocks(); });

function configured() {
  vi.stubEnv('NEXTAUTH_SECRET', 'test-runtime-only'); vi.stubEnv('AUTH_URL', 'http://localhost:4310');
  vi.stubEnv('VOUCHERS_GATEWAY_URL', 'http://gateway.test/vouchers');
  vi.mocked(getToken).mockResolvedValue({ accessToken: 'test-access', accessTokenExpires: Date.now() + 60000 });
}
it('delivers only private PDF bytes without exposing the gateway access token', async () => {
  configured();
  const fetcher = vi.fn().mockResolvedValue(new Response('%PDF-1.7', { headers: { 'Content-Type': 'application/pdf' } }));
  vi.stubGlobal('fetch', fetcher);
  const result = await call();
  expect(result.status).toBe(200);
  expect(result.headers.get('cache-control')).toContain('no-store');
  expect(result.headers.get('content-type')).toBe('application/pdf');
  expect(await result.text()).toBe('%PDF-1.7');
  expect(fetcher).toHaveBeenCalledWith(`http://gateway.test/vouchers${path}`, expect.objectContaining({
    headers: expect.objectContaining({ Authorization: 'Bearer test-access' }),
  }));
});
it('refuses cross-origin calls and a successful HTML response from the print owner', async () => {
  configured();
  const fetcher = vi.fn().mockResolvedValue(new Response('<html>', { headers: { 'Content-Type': 'text/html' } }));
  vi.stubGlobal('fetch', fetcher);
  expect((await call('https://attacker.invalid')).status).toBe(403);
  expect(fetcher).not.toHaveBeenCalled();
  expect((await call()).status).toBe(502);
});
