import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import { identityFetch } from '../app/identity-session';
const { getToken, cookieGet, go } = vi.hoisted(() => ({ getToken: vi.fn(), cookieGet: vi.fn(), go: vi.fn() }));
vi.mock('next-auth/jwt', () => ({ getToken }));
vi.mock('next/headers', () => ({ headers: async () => new Headers(), cookies: async () => ({ get: cookieGet }) }));
vi.mock('next/navigation', () => ({ redirect: go }));
beforeEach(() => {
  vi.clearAllMocks();
  vi.stubEnv('AUTH_URL', 'https://auth.test'); vi.stubEnv('IDENTITY_URL', 'https://identity.test'); vi.stubEnv('NEXTAUTH_SECRET', 'test-only');
  getToken.mockResolvedValue({ accessToken: 'private-access', accessTokenExpires: Date.now() + 300_000 });
  go.mockImplementation((url) => { throw new Error('redirect:' + url); });
});
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });
it('sends access and company proof only to the configured Identity origin', async () => {
  cookieGet.mockReturnValue({ value: 'private-proof' });
  const fetcher = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
  vi.stubGlobal('fetch', fetcher);
  const company = '0198ffff-0000-7000-8000-000000000001';
  await identityFetch(`/v1/companies/${company}/display-config`);
  expect(String(fetcher.mock.calls[0][0])).toBe(`https://identity.test/v1/companies/${company}/display-config`);
  expect(fetcher.mock.calls[0][1]).toMatchObject({ redirect: 'error', cache: 'no-store', headers: { Authorization: 'Bearer private-access', 'X-Company-Step-Up': 'private-proof' } });
  await expect(identityFetch('https://evil.test/')).rejects.toThrow('Invalid Identity path');
});
it('redirects missing and expired sessions before requesting data', async () => {
  getToken.mockResolvedValue(null);
  await expect(identityFetch('/v1/session')).rejects.toThrow('redirect:https://auth.test/login');
  getToken.mockResolvedValue({ accessToken: 'stale', accessTokenExpires: 0 });
  await expect(identityFetch('/v1/session')).rejects.toThrow('redirect:https://auth.test/refresh');
});
it('starts company verification only for the step-up error contract', async () => {
  const company = '0198ffff-0000-7000-8000-000000000001';
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: 'step_up_required' } }), { status: 403 })));
  await expect(identityFetch(`/v1/companies/${company}`)).rejects.toThrow(`redirect:https://auth.test/step-up?company=${company}`);
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 403 })));
  expect((await identityFetch('/v1/session')).status).toBe(403);
});
it('sends revoked authentication back to login', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 401 })));
  await expect(identityFetch('/v1/session')).rejects.toThrow('redirect:https://auth.test/login?error=SessionExpired');
});
it('forwards only the selected company proof during session bootstrap', async () => {
  const company = '0198ffff-0000-7000-8000-000000000001';
  cookieGet.mockReturnValue({ value: 'company-proof' });
  const fetcher = vi.fn(async () => Response.json({ company: { id: company } })); vi.stubGlobal('fetch', fetcher);
  await identityFetch('/v1/session?company_id=' + company);
  expect(cookieGet).toHaveBeenCalledWith('janso-step-up-' + company);
  expect(fetcher).toHaveBeenCalledWith(expect.any(URL), expect.objectContaining({ headers: expect.objectContaining({ 'X-Company-Step-Up': 'company-proof' }) }));
});
it('sanitizes missing configuration and dependency outages into 503 without swallowing redirects', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('private connection details')));
  const response = await identityFetch('/v1/session'); expect(response.status).toBe(503);
  expect(await response.text()).not.toContain('private');
  vi.stubEnv('IDENTITY_URL', ''); expect((await identityFetch('/v1/session')).status).toBe(503);
});
