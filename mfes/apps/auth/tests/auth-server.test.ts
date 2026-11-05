import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { authOptions, safeReturnUrl } from '../app/lib/auth-options';
import { POST } from '../app/api/step-up/route';
const { getToken } = vi.hoisted(() => ({ getToken: vi.fn() }));
vi.mock('next-auth/jwt', () => ({ getToken }));
vi.mock('../app/lib/refresh-coordinator', async (original) => ({
  ...await original<typeof import('../app/lib/refresh-coordinator')>(),
  coordinatedRefresh: async (_identity: unknown, exchange: () => Promise<unknown>) => {
    try { return await exchange(); } catch { return { error: 'unavailable' }; }
  },
}));
const company = '0198ffff-0000-7000-8000-000000000001';
beforeEach(() => {
  vi.clearAllMocks();
  for (const [key, value] of Object.entries({ AUTH_PROVIDER: 'authentik', AUTHENTIK_ISSUER: 'https://id.test/application/o/billing/', AUTHENTIK_CLIENT_ID: 'test-client', AUTHENTIK_CLIENT_SECRET: 'test-only', NEXTAUTH_SECRET: 'test-only', NEXTAUTH_URL: 'https://auth.test', CONSOLE_URL: 'https://console.test', IDENTITY_URL: 'https://identity.test' })) vi.stubEnv(key, value);
});
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });

it('restricts return URLs and keeps credentials out of session JSON', async () => {
  expect(safeReturnUrl('//evil.test')).toBe('https://console.test/');
  expect(safeReturnUrl('https://user:pass@console.test/path')).toBe('https://console.test/');
  expect(safeReturnUrl('/safe')).toBe('https://console.test/safe');
  expect(safeReturnUrl(null)).toBe('https://console.test/');
  vi.stubEnv('AUTH_COOKIE_DOMAIN', '.example.test');
  const options = authOptions();
  expect(options.cookies?.sessionToken?.options).toMatchObject({ secure: true, httpOnly: true, sameSite: 'lax' });
  const session = await options.callbacks!.session!({ session: { expires: 'future' }, token: { accessToken: 'private', refreshToken: 'private', refreshError: true } } as never);
  expect(session.expires).toBe(new Date(0).toISOString());
  expect(JSON.stringify(session)).not.toContain('private');
});

it('reuses live access tokens and rotates expired provider tokens', async () => {
  const jwt = authOptions().callbacks!.jwt!;
  const token = await jwt({ token: {}, account: { access_token: 'first', refresh_token: 'refresh', expires_at: Math.floor(Date.now() / 1000) + 300 } } as never);
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ access_token: 'second', expires_in: 300, refresh_token: 'rotated' }) });
  vi.stubGlobal('fetch', fetcher);
  expect(await jwt({ token } as never)).toEqual(token);
  expect(fetcher).not.toHaveBeenCalled();
  const refreshed = await jwt({ token: { ...token, accessTokenExpires: 0 } } as never);
  expect(refreshed).toMatchObject({ accessToken: 'second', refreshToken: 'rotated', refreshError: false });
  expect(fetcher.mock.calls[0][1]).toMatchObject({ redirect: 'error', cache: 'no-store' });
});
it('keeps checked profile region metadata private and rejects session update overrides', async () => {
  const jwt = authOptions().callbacks!.jwt!;
  const token = await jwt({ token: {}, account: { access_token: 'access', expires_at: Date.now() / 1000 + 300 },
    profile: { billing_registration_region: { country_code: 'IN', state_code: 'IN-MH', is_active: true } } } as never);
  expect(token.registrationRegion).toEqual({ country_code: 'IN', state_code: 'IN-MH' });
  expect(await jwt({ token, trigger: 'update', session: { registrationRegion: { country_code: 'US', state_code: 'US-CA' } } } as never)).toEqual(token);
  const session = await authOptions().callbacks!.session!({ session: { expires: 'future' }, token } as never);
  expect(session).not.toHaveProperty('registrationRegion');
  const next = await jwt({ token, account: { access_token: 'access', expires_at: Date.now() / 1000 + 300 }, profile: {} } as never);
  expect(next.registrationRegion).toBeNull();
});

it.each(['missing', 'network', 'invalid'])('fails expired authentication closed: %s', async (mode) => {
  const fetcher = mode === 'network' ? vi.fn().mockRejectedValue(new Error('offline')) : vi.fn().mockResolvedValue({ ok: true, json: async () => ({ expires_in: -1 }) });
  vi.stubGlobal('fetch', fetcher);
  const result = await authOptions().callbacks!.jwt!({ token: { accessToken: 'stale', accessTokenExpires: 0, ...(mode !== 'missing' ? { refreshToken: 'refresh' } : {}) } } as never);
  expect(result).toMatchObject({ refreshError: true, accessToken: undefined });
});

it('revokes both Identity sessions and provider refresh credentials on logout', async () => {
  const fetcher = vi.fn().mockRejectedValue(new Error('offline'));
  vi.stubGlobal('fetch', fetcher);
  await authOptions().events!.signOut!({ token: { accessToken: 'access', refreshToken: 'refresh' } } as never);
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect(String(fetcher.mock.calls[0][0])).toBe('https://identity.test/v1/session/revoke');
  expect(String(fetcher.mock.calls[1][0])).toBe('https://id.test/application/o/revoke/');
});

function request(body: unknown, origin = 'https://auth.test') {
  return new NextRequest('https://auth.test/api/step-up', { method: 'POST', headers: { origin, 'content-type': 'application/json' }, body: JSON.stringify(body) });
}
it('rejects cross-origin and malformed step-up commands before calling Identity', async () => {
  expect((await POST(request({ company, action: 'challenge' }, 'https://evil.test'))).status).toBe(403);
  expect((await POST(request({ company: '../other', action: 'challenge' }))).status).toBe(422);
  getToken.mockResolvedValue(null);
  expect((await POST(request({ company, action: 'challenge' }))).status).toBe(401);
});
it('keeps a completed proof in an HttpOnly company cookie', async () => {
  getToken.mockResolvedValue({ accessToken: 'private-access' });
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ proof: 'private-proof-value-12345' }) }));
  const response = await POST(request({ company, action: 'complete', challenge: company }));
  expect(response.status).toBe(200);
  expect(await response.json()).toEqual({ completed: true });
  expect(response.headers.get('set-cookie')).toContain('HttpOnly');
  expect(response.headers.get('set-cookie')).toContain('Secure');
  expect(response.headers.get('cache-control')).toBe('no-store');
  expect(response.headers.get('set-cookie')).toContain('janso-company=' + company);
});

it.each([
  { access_token: '', expires_in: 300 },
  { access_token: 'access', expires_in: Infinity },
  { access_token: 'access', expires_in: 901 },
  { access_token: 'access', expires_in: 300, refresh_token: '' },
])('rejects malformed refresh success metadata: %j', async (value) => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => value }));
  const token = await authOptions().callbacks!.jwt!({ token: { refreshToken: 'refresh', accessTokenExpires: 0 } } as never);
  expect(token).toMatchObject({ refreshError: true, refreshFailure: 'invalid', accessToken: undefined, refreshToken: undefined });
});
it.each(['', 'a'.repeat(16_385)])('rejects invalid initial access credentials', async (access_token) => {
  const token = await authOptions().callbacks!.jwt!({ token: {}, account: { access_token,
    refresh_token: 'refresh', expires_at: Date.now() / 1000 + 300 } } as never);
  expect(token).toMatchObject({ refreshError: true, accessToken: undefined, refreshToken: undefined });
});
it.each([undefined, Infinity, '300'])('rejects malformed initial expiry metadata: %s', async (expires_at) => {
  const token = await authOptions().callbacks!.jwt!({ token: {}, account: {
    access_token: 'access', refresh_token: 'refresh', expires_at } } as never);
  expect(token).toMatchObject({ refreshError: true, accessToken: undefined, refreshToken: undefined });
});
it.each([403, 503])('preserves a rejected Identity challenge: %s', async (status) => {
  getToken.mockResolvedValue({ accessToken: 'private-access' });
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status }));
  expect((await POST(request({ company, action: 'challenge' }))).status).toBe(status);
});
it('maps provider failures and invalid proofs without leaking them', async () => {
  getToken.mockResolvedValue({ accessToken: 'private-access' });
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('private')));
  expect((await POST(request({ company, action: 'complete' }))).status).toBe(503);
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ proof: 'x'.repeat(129) }) }));
  expect((await POST(request({ company, action: 'complete' }))).status).toBe(502);
});
