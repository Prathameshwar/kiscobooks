import { createRequire } from 'node:module';
import { randomBytes } from 'node:crypto';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { encode, decode } from 'next-auth/jwt';
import { createClient } from 'redis';
import { GET as authGet, POST as authPost } from '../../app/api/auth/[...nextauth]/route';
import { GET as refreshGet } from '../../app/refresh/route';
import { POST as refreshPost, OPTIONS } from '../../app/api/session/refresh/route';
import { identityFetch } from '../../../console/app/identity-session';

const require = createRequire(import.meta.url);
const { workAsyncStorage } = require('next/dist/server/app-render/work-async-storage.external');
const { workUnitAsyncStorage } = require('next/dist/server/app-render/work-unit-async-storage.external');
const { createRequestStoreForAPI } = require('next/dist/server/async-storage/request-store');
function run(request: NextRequest, handler: (request: NextRequest) => Promise<Response>): Promise<Response> {
  const store = createRequestStoreForAPI(request, request.nextUrl, { tags: [], expirationsByCacheKind: new Map() }, undefined, {});
  return workAsyncStorage.run({ route: '/api/auth', isStaticGeneration: false },
    () => workUnitAsyncStorage.run(store, () => handler(request)));
}
let secret: string;
beforeEach(() => {
  secret = randomBytes(32).toString('hex');
  for (const [key, value] of Object.entries({ AUTH_PROVIDER: 'authentik', NEXTAUTH_URL: 'https://auth.test', NEXTAUTH_SECRET: secret,
    CONSOLE_URL: 'https://console.test', IDENTITY_URL: 'https://identity.test',
    AUTHENTIK_ISSUER: 'https://id.test/application/o/billing/', AUTHENTIK_CLIENT_ID: 'test-client',
    AUTHENTIK_CLIENT_SECRET: randomBytes(32).toString('hex'), AUTH_COOKIE_DOMAIN: '.test' })) vi.stubEnv(key, value);
});
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });
const context = (action: string) => ({ params: Promise.resolve({ nextauth: [action] }) });
async function cookie(expired = false) {
  const value = await encode({ secret, token: { sub: 'person', accessToken: randomBytes(24).toString('hex'),
    refreshToken: randomBytes(24).toString('hex'), accessTokenExpires: expired ? 0 : Date.now() + 300_000 } });
  return `__Secure-next-auth.session-token=${value}`;
}
function cookieHeader(response: Response) { return response.headers.getSetCookie().map((value) => value.split(';')[0]).join('; '); }

it('the actual CSRF-protected logout clears the shared session and company cookies and invokes revocation', async () => {
  const session = await cookie(), company = '0198ffff-0000-7000-8000-000000000001';
  const initialCookies = `${session}; janso-company=${company}; janso-step-up-${company}=proof`;
  const csrfRequest = new NextRequest('https://auth.test/api/auth/csrf', { headers: { cookie: initialCookies } });
  const csrf = await run(csrfRequest, (request) => authGet(request, context('csrf')));
  const { csrfToken } = await csrf.json();
  const fetcher = vi.fn(async (_input: RequestInfo | URL) => new Response(null, { status: 204 })); vi.stubGlobal('fetch', fetcher);
  const request = new NextRequest('https://auth.test/api/auth/signout', { method: 'POST',
    headers: { cookie: `${initialCookies}; ${cookieHeader(csrf)}`, 'content-type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ csrfToken, callbackUrl: 'https://auth.test/login?reauth=1', json: 'true' }) });
  const response = await run(request, (value) => authPost(value, context('signout')));
  expect(response.status).toBe(200);
  expect(await response.json()).toEqual({ url: 'https://auth.test/login?reauth=1' });
  const cleared = response.headers.getSetCookie();
  for (const name of ['__Secure-next-auth.session-token', 'janso-company', `janso-step-up-${company}`])
    expect(cleared.some((value) => value.startsWith(name + '=;') && (value.includes('Max-Age=0') || value.includes('1970')))).toBe(true);
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect(String(fetcher.mock.calls[0][0])).toBe('https://identity.test/v1/session/revoke');
  const anonymous = new NextRequest('https://auth.test/api/auth/session');
  expect(await (await run(anonymous, (value) => authGet(value, context('session')))).json()).toEqual({});
});
it('a logout without matching CSRF cannot clear cookies or revoke sessions', async () => {
  const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
  const request = new NextRequest('https://auth.test/api/auth/signout', { method: 'POST',
    headers: { cookie: await cookie(), 'content-type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ csrfToken: 'wrong', json: 'true' }) });
  const response = await run(request, (value) => authPost(value, context('signout')));
  expect(fetcher).not.toHaveBeenCalled();
  expect(response.headers.getSetCookie().some((value) => value.includes('session-token=;'))).toBe(false);
});
it('the actual handler sanitizes error redirects and invalid configuration', async () => {
  const request = new NextRequest('https://auth.test/api/auth/error?error=OAuthCallback');
  const response = await run(request, (value) => authGet(value, context('error')));
  expect(response.headers.get('location')).toBe('https://auth.test/api/auth/signin?error=OAuthCallback');
  const signin = new NextRequest(response.headers.get('location')!);
  const destination = new URL((await run(signin, (value) => authGet(value, context('signin')))).headers.get('location')!, signin.url);
  expect(destination.pathname).toBe('/login');
  expect(destination.searchParams.get('error')).toBe('OAuthCallback');
  vi.stubEnv('AUTHENTIK_CLIENT_SECRET', '');
  const unavailable = await run(request, (value) => authGet(value, context('error')));
  expect(unavailable.status).toBe(503);
  expect(await unavailable.text()).toBe('{"error":"Authentication unavailable"}');
  vi.stubEnv('CONSOLE_URL', '');
  expect((await run(new NextRequest('https://auth.test/refresh?returnTo=/vouchers'), refreshGet)).status).toBe(503);
});
it('only trusted origins can refresh and the response exposes no tokens', async () => {
  const request = new NextRequest('https://auth.test/api/session/refresh', { method: 'POST',
    headers: { origin: 'https://console.test', cookie: await cookie() } });
  const response = await run(request, refreshPost);
  expect(response.status).toBe(200);
  expect(await response.json()).toEqual({ authenticated: true });
  expect(response.headers.get('Access-Control-Allow-Origin')).toBe('https://console.test');
  expect(response.headers.get('Set-Cookie')).toContain('HttpOnly');
  expect((await OPTIONS(new NextRequest(request.url, { headers: { origin: 'https://console.test' } }))).status).toBe(204);
  expect((await refreshPost(new NextRequest(request.url, { method: 'POST', headers: { origin: 'https://evil.test' } }))).status).toBe(403);
});
it.each([false, true])('Console reads the actual encrypted cookie and forwards only selected-company proof: chunks=%s', async (chunked) => {
  vi.stubEnv('AUTH_URL', 'https://auth.test');
  const company = '0198ffff-0000-7000-8000-000000000001';
  const access = randomBytes(24).toString('hex');
  const encoded = await encode({ secret, token: { sub: 'person', accessToken: access,
    refreshToken: randomBytes(24).toString('hex'), accessTokenExpires: Date.now() + 300_000 } });
  const session = chunked ? `__Secure-next-auth.session-token.0=${encoded.slice(0, 150)}; __Secure-next-auth.session-token.1=${encoded.slice(150)}` :
    `__Secure-next-auth.session-token=${encoded}`;
  const fetcher = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => Response.json({ company: { id: company } }));
  vi.stubGlobal('fetch', fetcher);
  const request = new NextRequest('https://console.test/vouchers', { headers: {
    cookie: `${session}; janso-company=${company}; janso-step-up-${company}=selected-proof; janso-step-up-00000000-0000-0000-0000-000000000002=other-proof`,
  } });
  const response = await run(request, () => identityFetch('/v1/session?company_id=' + company));
  expect(response.status).toBe(200);
  expect(fetcher).toHaveBeenCalledWith(new URL('https://identity.test/v1/session?company_id=' + company),
    expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer ' + access, 'X-Company-Step-Up': 'selected-proof' }) }));
  const forwarded = new Headers(fetcher.mock.calls[0][1]?.headers);
  expect(forwarded.get('X-Request-Id')).toMatch(/^[0-9a-f-]{36}$/i);
  expect(forwarded.get('X-Trace-Id')).toMatch(/^[0-9a-f]{32}$/i);
  expect([...forwarded.values()].join(' ')).not.toContain('other-proof');
  expect(forwarded.has('cookie')).toBe(false);
});
it('a real refresh failure is retryable and preserves the Console return URL', async () => {
  vi.stubEnv('AUTH_REDIS_URL', '');
  const request = new NextRequest('https://auth.test/refresh?returnTo=https%3A%2F%2Fconsole.test%2Fvouchers',
    { headers: { cookie: await cookie(true) } });
  const response = await run(request, refreshGet);
  expect(response.headers.get('location')).toBe('https://auth.test/login?error=SessionUnavailable&returnTo=https%3A%2F%2Fconsole.test%2Fvouchers');
  expect(response.headers.getSetCookie()).not.toHaveLength(0);
});
it('an expired session redirects to the configured public Auth host behind a proxy', async () => {
  vi.stubEnv('AUTH_REDIS_URL', '');
  const request = new NextRequest('https://localhost:4310/refresh?returnTo=https%3A%2F%2Fconsole.test%2Fvouchers',
    { headers: { cookie: await cookie(true) } });
  const response = await run(request, refreshGet);
  expect(response.headers.get('location')).toBe('https://auth.test/login?error=SessionUnavailable&returnTo=https%3A%2F%2Fconsole.test%2Fvouchers');
});

// Opt-in native Redis evidence: no production keys/DB flushing; keys expire automatically.
it.skipIf(!process.env.TEST_AUTH_REDIS_URL)('rotates one grant across actual Redis-backed concurrent handler requests', async () => {
  vi.stubEnv('AUTH_REDIS_URL', process.env.TEST_AUTH_REDIS_URL!);
  const original = await cookie(true);
  const access = randomBytes(24).toString('hex'), rotated = randomBytes(24).toString('hex');
  const fetcher = vi.fn(async () => {
    await new Promise((resolve) => setTimeout(resolve, 50));
    return Response.json({ access_token: access, refresh_token: rotated, expires_in: 300 });
  });
  vi.stubGlobal('fetch', fetcher);
  const responses = await Promise.all(Array.from({ length: 8 }, () => run(
    new NextRequest('https://auth.test/api/session/refresh', { method: 'POST',
      headers: { cookie: original, origin: 'https://console.test' } }), refreshPost)));
  expect(fetcher).toHaveBeenCalledTimes(1);
  for (const response of responses) {
    expect(response.status).toBe(200);
    const sessionCookie = response.headers.getSetCookie().find((value) => value.startsWith('__Secure-next-auth.session-token='))!;
    const decoded = await decode({ secret, token: sessionCookie.split(';')[0].split('=')[1] });
    expect(decoded).toMatchObject({ accessToken: access, refreshToken: rotated, refreshError: false });
  }
  const observer = createClient({ url: process.env.TEST_AUTH_REDIS_URL, RESP: 2 });
  observer.on('error', () => {}); await observer.connect();
  try {
    for await (const keys of observer.scanIterator({ MATCH: 'janso:refresh:*:result' })) {
      for (const key of keys) {
        const value = await observer.get(key);
        expect(value).not.toContain(access); expect(value).not.toContain(rotated);
        expect(await observer.pTTL(key)).toBeLessThanOrEqual(15_000);
      }
    }
  } finally { await observer.quit(); }
});
