import { randomBytes } from 'node:crypto';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { encode } from 'next-auth/jwt';
import { GET, POST } from '../../app/api/setup/route';
import { allowSetupAttempt, setupCookieValue, validDraft } from '../../app/lib/setup-server';

let key: string, secret: string;
const draft = { platform_name: 'JANSO', public_url: 'https://console.test', workspace_name: 'Operators',
  workspace_slug: 'operators', administrator_name: 'Admin', country_code: 'IN', currency_code: 'INR', timezone: 'UTC' };
beforeEach(() => {
  key = randomBytes(32).toString('hex'); secret = randomBytes(32).toString('hex');
  for (const [name, value] of Object.entries({ AUTH_PROVIDER: 'authentik', IDENTITY_SETUP_KEY: key, NEXTAUTH_SECRET: secret,
    NEXTAUTH_URL: 'https://auth.test', IDENTITY_URL: 'https://identity.test', CONSOLE_URL: 'https://console.test' })) vi.stubEnv(name, value);
  vi.stubGlobal('fetch', vi.fn(async () => Response.json({ available: true, completed: false })));
});
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });
const post = (body: object, cookie = '', origin = 'https://auth.test') => POST(new NextRequest('https://auth.test/api/setup', {
  method: 'POST', headers: { origin, cookie }, body: JSON.stringify(body) }));
it('requires the setup key and same-origin requests and stores only an encrypted capability', async () => {
  expect((await post({ action: 'unlock', key }, '', 'https://evil.test')).status).toBe(403);
  expect((await post({ action: 'unlock', key: 'wrong' })).status).toBe(403);
  const response = await post({ action: 'unlock', key });
  expect(response.status).toBe(200);
  const cookie = response.headers.get('set-cookie')!;
  expect(cookie).toContain('HttpOnly'); expect(cookie).toContain('Secure');
  expect(cookie).toContain('Path=/api/setup'); expect(cookie).not.toContain(key);
  expect(await response.text()).not.toContain(key);
});
it('rejects tampered setup cookies and drafts with extra or oversized fields', async () => {
  expect((await post({ action: 'save', draft }, 'janso-platform-setup=invalid')).status).toBe(403);
  const cookie = `janso-platform-setup=${await setupCookieValue()}`;
  expect((await post({ action: 'save', draft: { ...draft, password: 'forbidden' } }, cookie)).status).toBe(422);
  expect(validDraft({ ...draft, public_url: 'x'.repeat(2400) })).toBe(false);
  expect(validDraft({ ...draft, locale: 'hi' })).toBe(true);
  expect(validDraft({ ...draft, locale: 'unsupported' })).toBe(false);
  const saved = await post({ action: 'save', draft }, cookie);
  expect(saved.status).toBe(200); expect(saved.headers.get('set-cookie')).not.toContain('Admin');
});
it('requires an authenticated provider token to complete setup and never accepts one from the body', async () => {
  const cookie = `janso-platform-setup=${await setupCookieValue()}`;
  expect((await post({ action: 'complete', draft, accessToken: 'browser-token' }, cookie)).status).toBe(401);
});
it('completes using the encrypted session token and verifies live platform access', async () => {
  const accessToken = randomBytes(24).toString('hex');
  const session = await encode({ secret, token: { accessToken, accessTokenExpires: Date.now() + 300_000 } });
  const cookie = `janso-platform-setup=${await setupCookieValue(draft)}; __Secure-next-auth.session-token=${session}`;
  const fetcher = vi.fn(async (url: URL) => String(url).endsWith('/v1/session')
    ? Response.json({ permissions: ['platform.tenant.read'] }) : Response.json({ completed: true }));
  vi.stubGlobal('fetch', fetcher);
  const response = await post({ action: 'complete', draft }, cookie);
  expect(response.status).toBe(200); expect(await response.json()).toMatchObject({ verified: true, destination: 'https://console.test/platform' });
  expect(fetcher.mock.calls).toHaveLength(2);
  expect(JSON.stringify(fetcher.mock.calls)).not.toContain(secret);
});
it('sanitizes upstream failures, closes existing setup and hides configuration from public status', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('database-password'); }));
  const response = await GET(new NextRequest('https://auth.test/api/setup'));
  expect(response.status).toBe(503); expect(await response.text()).not.toContain('database-password');
  vi.stubGlobal('fetch', vi.fn(async () => Response.json({ available: false, completed: true })));
  expect((await post({ action: 'unlock', key })).status).toBe(409);
});

it('bounds setup attempts and invalidates old capabilities after key rotation', async () => {
  const identity = randomBytes(16).toString('hex');
  expect(allowSetupAttempt(identity, 1)).toBe(true);
  expect(allowSetupAttempt(identity, 1)).toBe(false);
  const cookie = `janso-platform-setup=${await setupCookieValue()}`;
  vi.stubEnv('IDENTITY_SETUP_KEY', randomBytes(32).toString('hex'));
  expect((await post({ action: 'save', draft }, cookie)).status).toBe(403);
});

it('reports saved setup when the post-commit session verification is unavailable', async () => {
  const accessToken = randomBytes(24).toString('hex');
  const session = await encode({ secret, token: { accessToken, accessTokenExpires: Date.now() + 300_000 } });
  const cookie = `janso-platform-setup=${await setupCookieValue(draft)}; __Secure-next-auth.session-token=${session}`;
  vi.stubGlobal('fetch', vi.fn(async (url: URL) => {
    if (String(url).endsWith('/v1/session')) throw new Error('connection unavailable');
    return Response.json({ completed: true });
  }));
  const response = await post({ action: 'complete', draft }, cookie);
  expect(response.status).toBe(200);
  expect(await response.json()).toMatchObject({ completed: true, verified: false });
});

it('rejects a misconfigured destination before sending any provisioning request', async () => {
  const cookie = `janso-platform-setup=${await setupCookieValue(draft)}`;
  vi.stubEnv('CONSOLE_URL', 'javascript:alert(1)');
  expect((await post({ action: 'complete', draft }, cookie)).status).toBe(503);
  expect(fetch).not.toHaveBeenCalled();
});

it('bounds Unicode draft bytes so encrypted cookies remain within browser limits', async () => {
  const unicode = { ...draft, platform_name: '界'.repeat(200), workspace_name: '界'.repeat(200), administrator_name: '界'.repeat(100) };
  expect(validDraft(unicode)).toBe(true);
  const encoded = await setupCookieValue(unicode);
  expect(encoded.length).toBeLessThan(3800);
  expect(validDraft({ ...unicode, public_url: 'https://example.test/' + 'x'.repeat(900) })).toBe(false);
});

it('rejects oversized streams without trusting Content-Length', async () => {
  const response = await POST(new NextRequest('https://auth.test/api/setup', { method: 'POST',
    headers: { origin: 'https://auth.test' }, body: JSON.stringify({ action: 'unlock', key: '界'.repeat(3000) }) }));
  expect(response.status).toBe(413);
  expect(fetch).not.toHaveBeenCalled();
});

it('does not reveal drafts or unexpected upstream fields once setup is closed', async () => {
  const cookie = `janso-platform-setup=${await setupCookieValue(draft)}`;
  vi.stubGlobal('fetch', vi.fn(async () => Response.json({ completed: true, available: false, password: 'private' })));
  const response = await GET(new NextRequest('https://auth.test/api/setup', { headers: { cookie } }));
  expect(await response.json()).toEqual({ completed: true, available: false, unlocked: true });
});

it('requires service readiness payloads rather than an unrelated HTTP success', async () => {
  const cookie = `janso-platform-setup=${await setupCookieValue()}`;
  vi.stubEnv('SETUP_SERVICE_URLS', JSON.stringify(Object.fromEntries(
    ['Audit', 'Catalog', 'Accounting', 'Vouchers', 'Reports', 'Notification'].map(name => [name, 'http://127.0.0.1:8000']))));
  vi.stubGlobal('fetch', vi.fn(async (url: URL) => String(url).endsWith('/v1/setup/checks')
    ? Response.json({ ready: true, checks: [], countries: [], currencies: [] }) : Response.json({ status: 'wrong' })));
  const response = await GET(new NextRequest('https://auth.test/api/setup?action=checks', { headers: { cookie } }));
  const checks = await response.json();
  expect(checks.ready).toBe(false);
  expect(checks.checks.filter((check: { name: string; status: string }) => check.name.endsWith(' API')))
    .toHaveLength(6);
  expect(checks.checks.every((check: { status: string }) => check.status === 'failed')).toBe(true);
});
