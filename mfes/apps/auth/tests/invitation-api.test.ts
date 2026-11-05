import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { POST } from '../app/api/invitations/accept/route';
const { getToken } = vi.hoisted(() => ({ getToken: vi.fn() }));
vi.mock('next-auth/jwt', () => ({ getToken }));
const id = '0198ffff-0000-7000-8000-000000000001';
beforeEach(() => {
  vi.stubEnv('NEXTAUTH_URL', 'https://auth.test'); vi.stubEnv('IDENTITY_URL', 'https://identity.test');
  vi.stubEnv('NEXTAUTH_SECRET', 'test-only'); getToken.mockResolvedValue({ accessToken: 'private-access' });
});
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.clearAllMocks(); });
const request = (body: unknown = { tenant: id, invitation: id }, origin = 'https://auth.test') =>
  new NextRequest('https://auth.test/api/invitations/accept', { method: 'POST',
    headers: { origin, 'content-type': 'application/json' }, body: JSON.stringify(body) });
it('bounds outages and sanitizes details into a retryable response', async () => {
  const fetcher = vi.fn().mockRejectedValue(new Error('private connection details'));
  vi.stubGlobal('fetch', fetcher);
  const response = await POST(request());
  expect(response.status).toBe(503); expect(await response.json()).toEqual({ error: 'Service unavailable' });
  expect(response.headers.get('Cache-Control')).toBe('no-store');
  expect(fetcher.mock.calls[0][1]).toMatchObject({ cache: 'no-store', redirect: 'error', signal: expect.any(AbortSignal) });
});
it.each([200, 204, 401, 403, 422, 503])('preserves accepted or denied Identity results: %s', async (status) => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status })));
  const response = await POST(request()); expect(response.status).toBe(status === 204 ? 200 : status);
  expect(await response.json()).toEqual({ accepted: status < 300 });
});
it('rejects origin, malformed body and unauthenticated requests before sending commands', async () => {
  const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
  expect((await POST(request(undefined, 'https://evil.test'))).status).toBe(403);
  expect((await POST(request({ tenant: [], invitation: id }))).status).toBe(422);
  getToken.mockResolvedValue(null); expect((await POST(request())).status).toBe(401);
  expect(fetcher).not.toHaveBeenCalled();
});
