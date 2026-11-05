import { randomBytes } from 'node:crypto';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { encode } from 'next-auth/jwt';
import { GET, POST } from '../../app/api/setup/route';
import { allowSetupAttempt, setupCookieValue } from '../../app/lib/setup-server';
import { AUTH_URL, BFF_SECRET, IDENTITY, ISSUER, LEAK, consoleSpies, envelope, localEnv } from './local-support';

let key: string, secret: string;
const administrator = { name: 'Platform Admin', email: 'Admin@Example.Test', password: 'An Administrator Passphrase 7!', password_repeat: 'An Administrator Passphrase 7!' };
const localStatus = (administratorExists: boolean) => Response.json({ provider: 'local', registration_enabled: true,
  recovery: { link: true, email: false }, setup: { administrator_exists: administratorExists } });
const unlocked = async () => `janso-platform-setup=${await setupCookieValue()}`;
const post = (body: object, cookie = '', origin = AUTH_URL) => POST(new NextRequest(`${AUTH_URL}/api/setup`, {
  method: 'POST', headers: { origin, cookie }, body: JSON.stringify(body) }));
const get = (query = '', cookie = '') => GET(new NextRequest(`${AUTH_URL}/api/setup${query}`, { headers: { cookie } }));
let fetcher: ReturnType<typeof vi.fn>;
// The setup limiter keeps per-minute counters in module state; each test starts a fresh minute.
let clock = Date.now();
const urls = () => fetcher.mock.calls.map(([url]) => String(url));
beforeEach(() => {
  clock += 120_000;
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(clock);
  key = randomBytes(32).toString('hex'); secret = randomBytes(32).toString('hex');
  localEnv({ IDENTITY_SETUP_KEY: key, NEXTAUTH_SECRET: secret });
  fetcher = vi.fn(async (url: URL | string) => String(url).endsWith('/v1/setup/status') ? Response.json({ available: true, completed: false })
    : String(url).endsWith('/internal/v1/local-auth/status') ? localStatus(false) : new Response(null, { status: 500 }));
  vi.stubGlobal('fetch', fetcher);
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllEnvs(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe('status', () => {
  it('names the provider but tells a locked caller nothing about administrators', async () => {
    const body = await (await get()).json();
    expect(body).toEqual({ available: true, completed: false, unlocked: false, provider: 'local' });
    expect(urls().some(url => url.includes('local-auth'))).toBe(false);
  });
  it.each([false, true])('tells an unlocked caller whether an administrator exists (%s)', async exists => {
    fetcher.mockImplementation(async (url: URL | string) => String(url).endsWith('/v1/setup/status')
      ? Response.json({ available: true, completed: false }) : localStatus(exists));
    const body = await (await get('', await unlocked())).json();
    expect(body).toMatchObject({ unlocked: true, provider: 'local', administratorExists: exists });
    const call = fetcher.mock.calls.find(([url]) => String(url).endsWith('/internal/v1/local-auth/status'))!;
    expect(call[1].headers['X-Auth-Bff-Secret']).toBe(BFF_SECRET);
  });
  it('does not ask once setup is closed', async () => {
    fetcher.mockImplementation(async () => Response.json({ available: false, completed: true }));
    expect(await (await get('', await unlocked())).json()).toEqual({ available: false, completed: true, unlocked: true, provider: 'local' });
    expect(urls().some(url => url.includes('local-auth'))).toBe(false);
  });
  it.each([['an HTTP error', () => new Response(null, { status: 401 })], ['an unexpected body', () => Response.json({ provider: 'authentik' })],
    ['a body without the setup flag', () => Response.json({ provider: 'local', setup: {} })]])('fails closed on %s from the local status', async (_name, answer) => {
    fetcher.mockImplementation(async (url: URL | string) => String(url).endsWith('/v1/setup/status')
      ? Response.json({ available: true, completed: false }) : answer());
    expect((await get('', await unlocked())).status).toBe(503);
  });
});

describe('create-administrator', () => {
  const create = async (overrides: Record<string, unknown> = {}, cookie?: string, origin?: string) =>
    post({ action: 'create-administrator', ...administrator, ...overrides }, cookie ?? await unlocked(), origin);
  beforeEach(() => fetcher.mockImplementation(async () => Response.json({ created: true }, { status: 201 })));

  it('creates the account with the server-held setup key and the BFF secret, and returns no secret', async () => {
    const response = await create();
    expect(response.status).toBe(201);
    const text = await response.text();
    expect(JSON.parse(text)).toEqual({ created: true });
    expect(text).not.toContain(administrator.password);
    const [url, options] = fetcher.mock.calls[0];
    expect(String(url)).toBe(`${IDENTITY}/internal/v1/local-auth/setup/administrator`);
    expect(options).toMatchObject({ method: 'POST', cache: 'no-store', redirect: 'error' });
    expect(options.headers['X-Setup-Key']).toBe(key);
    expect(options.headers['X-Auth-Bff-Secret']).toBe(BFF_SECRET);
    expect(JSON.parse(options.body)).toEqual({ name: 'Platform Admin', email: 'admin@example.test', password: administrator.password });
  });
  it('never accepts a setup key from the request body and never sends one that was supplied', async () => {
    expect((await create({ key: 'attacker-supplied-key-attacker-supplied' })).status).toBe(422);
    expect((await create({ setup_key: 'attacker-supplied-key-attacker-supplied' })).status).toBe(422);
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('requires the unlocked setup capability, from the setup origin', async () => {
    expect((await create({}, '')).status).toBe(403);
    expect((await create({}, 'janso-platform-setup=forged')).status).toBe(403);
    expect((await create({}, undefined, 'https://evil.test')).status).toBe(403);
    // A capability issued for another key stops working after key rotation.
    const stale = `janso-platform-setup=${await setupCookieValue()}`;
    vi.stubEnv('IDENTITY_SETUP_KEY', randomBytes(32).toString('hex'));
    expect((await create({}, stale)).status).toBe(403);
    expect(fetcher).not.toHaveBeenCalled();
  });
  it.each<[string, Record<string, unknown>]>([['no name', { name: '' }], ['a long name', { name: 'n'.repeat(101) }],
    ['a control character in the name', { name: 'Ad\u0007min' }], ['an invalid email', { email: 'admin' }], ['an email with a space', { email: 'a b@c.test' }],
    ['a short password', { password: 'short', password_repeat: 'short' }], ['a long password', { password: 'p'.repeat(129), password_repeat: 'p'.repeat(129) }],
    ['a mismatched confirmation', { password_repeat: 'different-passphrase-1' }], ['an extra field', { role: 'owner' }],
    ['a non-string password', { password: 12345678 }]])('rejects %s without calling Identity', async (_name, overrides) => {
    const response = await create(overrides);
    expect(response.status).toBe(422);
    expect(await response.text()).not.toContain(administrator.password);
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('is rate limited', async () => {
    for (let count = 0; count < 10; count++) expect(allowSetupAttempt('create-administrator', 10)).toBe(true);
    expect((await create()).status).toBe(429);
    expect(fetcher).not.toHaveBeenCalled();
  });
  it.each([[403, 403, /Unlock setup again/], [409, 409, /already exists/], [429, 429, /Too many/], [500, 503, /could not be created/], [502, 503, /could not be created/]])(
    'maps Identity %i to %i with a fixed message', async (upstream, status, message) => {
      fetcher.mockImplementation(async () => envelope(upstream, 'x'));
      const response = await create();
      expect(response.status).toBe(status);
      const text = await response.text();
      expect(JSON.parse(text).error).toMatch(message);
      expect(text).not.toContain(LEAK);
    });
  it.each([['password', /password cannot be used/], ['email', /email address cannot be used/], ['name', /Check the administrator details/]])(
    'maps a 422 on %s to a fixed message', async (field, message) => {
      fetcher.mockImplementation(async () => Response.json({ error: { code: 'validation_error', message: LEAK }, fields: { [field]: LEAK } }, { status: 422 }));
      const response = await create();
      expect(response.status).toBe(422);
      const text = await response.text();
      expect(JSON.parse(text).error).toMatch(message);
      expect(text).not.toContain(LEAK);
    });
  it('hides network failures and never logs the password', async () => {
    const spies = consoleSpies();
    fetcher.mockRejectedValue(new Error(`socket ${administrator.password}`));
    const response = await create();
    expect(response.status).toBe(503);
    expect(await response.text()).not.toContain(administrator.password);
    for (const spy of spies) expect(spy).not.toHaveBeenCalled();
  });
  it('is not a setup action under the Authentik provider', async () => {
    vi.stubEnv('AUTH_PROVIDER', 'authentik');
    const response = await create();
    expect(response.status).toBe(422);
    expect(fetcher).not.toHaveBeenCalled();
  });
});

describe('connection checks and administrator sign-in', () => {
  const discovery = (issuer: string) => async (url: URL | string) => {
    const text = String(url);
    if (text.endsWith('/v1/setup/checks')) return Response.json({ ready: true, checks: [], countries: [], currencies: [] });
    if (text === `${ISSUER}/.well-known/openid-configuration`) return Response.json({ issuer });
    if (text.endsWith('/internal/v1/local-auth/status')) return localStatus(false);
    return new Response(null, { status: 500 });
  };
  const checks = async () => (await (await get('?action=checks', await unlocked())).json()).checks as { name: string; status: string; message: string }[];
  it('verifies the local discovery document and the BFF credentials instead of Authentik', async () => {
    fetcher.mockImplementation(discovery(ISSUER));
    const found = await checks();
    expect(found).toContainEqual({ name: 'Auth provider configuration', status: 'ready', message: 'Discovery and issuer match' });
    expect(found).toContainEqual({ name: 'Local sign-in service', status: 'ready', message: 'Identity accepted the Auth application' });
    expect(urls().some(url => /authentik|application\/o/.test(url))).toBe(false);
  });
  it('flags an issuer mismatch and a rejected BFF secret with local wording', async () => {
    fetcher.mockImplementation(async (url: URL | string) => String(url).endsWith('/internal/v1/local-auth/status') ? new Response(null, { status: 401 }) : discovery('https://other.test/oidc')(url));
    const found = await checks();
    expect(found.find(check => check.name === 'Auth provider configuration')).toMatchObject({ status: 'failed', message: expect.stringContaining('AUTH_LOCAL_') });
    expect(found.find(check => check.name === 'Local sign-in service')).toMatchObject({ status: 'failed', message: expect.stringContaining('AUTH_LOCAL_BFF_SECRET') });
    expect(JSON.stringify(found)).not.toMatch(/Authentik/);
  });
  it('describes administrator sign-in without naming Authentik', async () => {
    const response = await get('?action=administrator', await unlocked());
    expect(response.status).toBe(401);
    expect((await response.json()).error).toBe('Sign in as the administrator to continue.');
    const token = await encode({ secret, token: { accessToken: randomBytes(24).toString('hex'), accessTokenExpires: Date.now() + 300_000 } });
    const cookie = `${await unlocked()}; __Secure-next-auth.session-token=${token}`;
    fetcher.mockImplementation(async () => new Response(null, { status: 403 }));
    const forbidden = await get('?action=administrator', cookie);
    expect(forbidden.status).toBe(403);
    expect((await forbidden.json()).error).not.toMatch(/Authentik/);
    const incomplete = await post({ action: 'complete', draft: { platform_name: 'JANSO', public_url: 'https://console.test', workspace_name: 'Ops',
      workspace_slug: 'ops', administrator_name: 'Admin', country_code: 'IN', currency_code: 'INR', timezone: 'UTC' } }, await unlocked());
    expect(incomplete.status).toBe(401);
    expect((await incomplete.json()).error).toMatch(/Sign in as the administrator/);
  });
});
