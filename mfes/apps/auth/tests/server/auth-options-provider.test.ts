import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { authOptions } from '../../app/lib/auth-options';
import { ISSUER, localEnv } from './local-support';

// The Redis coordinator is exercised by its own suite; here the exchange runs inline.
vi.mock('../../app/lib/refresh-coordinator', async original => ({
  ...await original<typeof import('../../app/lib/refresh-coordinator')>(),
  coordinatedRefresh: async (_identity: unknown, exchange: () => Promise<unknown>) => {
    try { return await exchange(); } catch { return { error: 'unavailable' }; }
  },
}));

const expiredToken = { accessToken: 'stale', accessTokenExpires: 0, refreshToken: 'refresh-token-value' };
beforeEach(() => localEnv());
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });

describe('local provider', () => {
  it('registers the provider as `local` with the same PKCE, state, nonce and scope as before', () => {
    const [provider] = authOptions().providers as unknown as Record<string, unknown>[];
    expect(provider).toMatchObject({ id: 'local', type: 'oauth', clientId: 'auth-app', clientSecret: 'client-secret-for-tests',
      wellKnown: `${ISSUER}/.well-known/openid-configuration`, idToken: true, checks: ['pkce', 'state', 'nonce'],
      authorization: { params: { scope: 'openid profile email offline_access billing.api' } } });
  });
  it('refreshes at the local token endpoint with the client credentials, not an Authentik path', async () => {
    const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ access_token: 'second', expires_in: 300, refresh_token: 'rotated' }) });
    vi.stubGlobal('fetch', fetcher);
    const result = await authOptions().callbacks!.jwt!({ token: expiredToken } as never);
    expect(result).toMatchObject({ accessToken: 'second', refreshToken: 'rotated', refreshError: false });
    expect(String(fetcher.mock.calls[0][0])).toBe(`${ISSUER}/token`);
    expect(fetcher.mock.calls[0][1]).toMatchObject({ method: 'POST', redirect: 'error', cache: 'no-store' });
    const body = fetcher.mock.calls[0][1].body as URLSearchParams;
    expect(Object.fromEntries(body)).toEqual({ grant_type: 'refresh_token', refresh_token: 'refresh-token-value',
      client_id: 'auth-app', client_secret: 'client-secret-for-tests' });
  });
  it.each([[400, 'invalid'], [401, 'invalid'], [500, 'unavailable']])('maps a %s refresh answer to %s', async (status, failure) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status, json: async () => ({ error: 'invalid_grant' }) }));
    const result = await authOptions().callbacks!.jwt!({ token: expiredToken } as never);
    expect(result).toMatchObject({ refreshError: true, refreshFailure: failure, accessToken: undefined });
  });
  it('revokes the Identity session and then the refresh token at the local revoke endpoint on sign-out', async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error('offline'));
    vi.stubGlobal('fetch', fetcher);
    await authOptions().events!.signOut!({ token: { accessToken: 'access', refreshToken: 'refresh' } } as never);
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(String(fetcher.mock.calls[0][0])).toBe('https://identity.test/v1/session/revoke');
    expect(String(fetcher.mock.calls[1][0])).toBe(`${ISSUER}/revoke`);
    expect(Object.fromEntries(fetcher.mock.calls[1][1].body as URLSearchParams)).toEqual({ token: 'refresh',
      token_type_hint: 'refresh_token', client_id: 'auth-app', client_secret: 'client-secret-for-tests' });
  });
  it('allows a loopback HTTP issuer for development and nothing else over HTTP', () => {
    vi.stubEnv('AUTH_LOCAL_ISSUER', 'http://localhost:8001/oidc');
    vi.stubEnv('NEXTAUTH_URL', 'http://localhost:4310');
    expect(() => authOptions()).not.toThrow();
    for (const issuer of ['http://evil.example/oidc', 'http://localhost.evil.example/oidc']) {
      vi.stubEnv('AUTH_LOCAL_ISSUER', issuer);
      expect(() => authOptions()).toThrow();
    }
  });
  it.each(['AUTH_LOCAL_ISSUER', 'AUTH_LOCAL_CLIENT_ID', 'AUTH_LOCAL_CLIENT_SECRET'])('fails closed without %s', name => {
    vi.stubEnv(name, '');
    expect(() => authOptions()).toThrow();
  });
  it('fails closed on an unknown provider value', () => {
    vi.stubEnv('AUTH_PROVIDER', 'saml');
    expect(() => authOptions()).toThrow('Invalid authentication provider configuration');
  });
});

describe('authentik provider', () => {
  beforeEach(() => {
    vi.stubEnv('AUTH_PROVIDER', 'authentik');
    vi.stubEnv('AUTHENTIK_ISSUER', 'https://id.test/application/o/billing/');
    vi.stubEnv('AUTHENTIK_CLIENT_ID', 'test-client');
    vi.stubEnv('AUTHENTIK_CLIENT_SECRET', 'test-only');
  });
  it('is registered as `authentik` and still discovers through the issuer', () => {
    const [provider] = authOptions().providers as unknown as Record<string, unknown>[];
    expect(provider).toMatchObject({ id: 'authentik', name: 'Authentik', clientId: 'test-client',
      wellKnown: 'https://id.test/application/o/billing/.well-known/openid-configuration' });
  });
  it('keeps the application/o refresh and revoke endpoints', async () => {
    const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ access_token: 'second', expires_in: 300 }) });
    vi.stubGlobal('fetch', fetcher);
    await authOptions().callbacks!.jwt!({ token: expiredToken } as never);
    expect(String(fetcher.mock.calls[0][0])).toBe('https://id.test/application/o/token/');
    fetcher.mockClear();
    await authOptions().events!.signOut!({ token: { accessToken: 'access', refreshToken: 'refresh' } } as never);
    expect(String(fetcher.mock.calls[1][0])).toBe('https://id.test/application/o/revoke/');
  });
  it('does not need any local setting', () => {
    for (const name of ['AUTH_LOCAL_ISSUER', 'AUTH_LOCAL_CLIENT_ID', 'AUTH_LOCAL_CLIENT_SECRET', 'AUTH_LOCAL_BFF_SECRET']) vi.stubEnv(name, '');
    expect(() => authOptions()).not.toThrow();
  });
  it('still refuses an HTTP issuer', () => {
    vi.stubEnv('AUTHENTIK_ISSUER', 'http://localhost:9000/application/o/billing/');
    expect(() => authOptions()).toThrow();
  });
});
