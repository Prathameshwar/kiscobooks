import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { POST } from '../../app/api/change-password/route';
import { AUTH_URL, IDENTITY, LEAK, consoleSpies, envelope, localEnv } from './local-support';

const { getToken } = vi.hoisted(() => ({ getToken: vi.fn() }));
vi.mock('next-auth/jwt', () => ({ getToken }));
const access = 'access-token-for-the-signed-in-user';
const current = 'My Current Passphrase 1!';
const next = 'My Brand New Passphrase 2!';
const change = (body: unknown = { current_password: current, new_password: next }, headers: Record<string, string> = {}) =>
  new NextRequest(`${AUTH_URL}/api/change-password`, { method: 'POST',
    headers: { origin: AUTH_URL, 'content-type': 'application/json', ...headers }, body: typeof body === 'string' ? body : JSON.stringify(body) });
let fetcher: ReturnType<typeof vi.fn>;
let spies: ReturnType<typeof consoleSpies>;
beforeEach(() => {
  localEnv();
  getToken.mockReset().mockResolvedValue({ accessToken: access, accessTokenExpires: Date.now() + 300_000 });
  fetcher = vi.fn(async () => new Response(null, { status: 204 }));
  vi.stubGlobal('fetch', fetcher);
  spies = consoleSpies();
});
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe('local change password', () => {
  it('changes the password through Identity with the session access token and nothing else', async () => {
    const response = await POST(change());
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ changed: true });
    expect(response.headers.get('cache-control')).toBe('no-store');
    const [url, options] = fetcher.mock.calls[0];
    expect(String(url)).toBe(`${IDENTITY}/v1/session/password`);
    expect(options).toMatchObject({ method: 'POST', cache: 'no-store', redirect: 'error' });
    expect(options.headers.Authorization).toBe(`Bearer ${access}`);
    expect(options.headers).not.toHaveProperty('X-Auth-Bff-Secret');
    expect(JSON.parse(options.body)).toEqual({ current_password: current, new_password: next });
  });
  it('401 from Identity means the session is no longer valid', async () => {
    fetcher.mockResolvedValue(envelope(401, 'unauthorized'));
    const response = await POST(change());
    expect(response.status).toBe(401);
    expect((await response.json()).error).toMatch(/Sign in again/);
  });
  it('422 on the current password becomes a fixed field error', async () => {
    fetcher.mockResolvedValue(Response.json({ error: { code: 'validation_error', message: LEAK }, fields: { current_password: LEAK } }, { status: 422 }));
    const response = await POST(change());
    expect(response.status).toBe(422);
    const text = await response.text();
    expect(JSON.parse(text).fields).toEqual({ current_password: 'Your current password is incorrect.' });
    expect(text).not.toContain(LEAK);
  });
  it('422 on the new password becomes a fixed field error, in either envelope position', async () => {
    fetcher.mockResolvedValueOnce(Response.json({ error: { code: 'validation_error', message: LEAK, fields: { new_password: LEAK } } }, { status: 422 }));
    expect((await (await POST(change())).json()).fields).toEqual({ new_password: expect.stringContaining('different password') });
    fetcher.mockResolvedValueOnce(Response.json({ error: { code: 'validation_error', message: LEAK }, fields: { new_password: LEAK, current_password: LEAK } }, { status: 422 }));
    expect(Object.keys((await (await POST(change())).json()).fields).sort()).toEqual(['current_password', 'new_password']);
  });
  it('429 asks the caller to wait; other failures are temporary and say nothing about Identity', async () => {
    fetcher.mockResolvedValueOnce(envelope(429, 'rate_limited'));
    const limited = await POST(change());
    expect(limited.status).toBe(429);
    expect(limited.headers.get('retry-after')).toBe('60');
    for (const status of [400, 403, 404, 500, 503]) {
      fetcher.mockResolvedValueOnce(envelope(status, 'x'));
      const response = await POST(change());
      expect(response.status).toBe(503);
      expect(await response.text()).not.toContain(LEAK);
    }
    fetcher.mockResolvedValueOnce(envelope(422, 'x'));
    expect((await POST(change())).status).toBe(503);
    fetcher.mockRejectedValueOnce(new Error(`${current} ${LEAK}`));
    const failed = await POST(change());
    expect(failed.status).toBe(503);
    const text = await failed.text();
    expect(text).not.toContain(current);
    expect(text).not.toContain(LEAK);
  });

  describe('is authenticated and validated before Identity is called', () => {
    it.each<[string, unknown]>([['no session', null], ['an expired access token', { accessToken: access, accessTokenExpires: Date.now() + 1000 }],
      ['no access token', { accessTokenExpires: Date.now() + 300_000 }], ['a non-numeric expiry', { accessToken: access, accessTokenExpires: 'soon' }]])(
      'answers 401 with %s', async (_name, token) => {
        getToken.mockResolvedValue(token);
        expect((await POST(change())).status).toBe(401);
        expect(fetcher).not.toHaveBeenCalled();
      });
    it('refuses a foreign or cross-site origin', async () => {
      expect((await POST(change(undefined, { origin: 'https://evil.test' }))).status).toBe(403);
      expect((await POST(change(undefined, { 'sec-fetch-site': 'cross-site' }))).status).toBe(403);
      expect(fetcher).not.toHaveBeenCalled();
    });
    it('accepts only a small JSON body', async () => {
      expect((await POST(change(undefined, { 'content-type': 'text/plain' }))).status).toBe(415);
      expect((await POST(change(undefined, { 'content-length': '9000' }))).status).toBe(413);
      expect((await POST(change({ current_password: current, new_password: 'x'.repeat(6000) }))).status).toBe(400);
      expect((await POST(change('{"current_password"'))).status).toBe(400);
      expect((await POST(change('[]'))).status).toBe(422);
      expect(fetcher).not.toHaveBeenCalled();
    });
    it.each<[string, unknown]>([['an extra field', { current_password: current, new_password: next, user_id: 'x' }],
      ['a missing field', { new_password: next }], ['a non-string field', { current_password: 1, new_password: next }]])('rejects %s', async (_name, body) => {
      expect((await POST(change(body))).status).toBe(422);
      expect(fetcher).not.toHaveBeenCalled();
    });
    it('applies the password rule to the new password and requires a current one', async () => {
      for (const new_password of ['short', 'a'.repeat(129), 'ctrl\u0007chars1']) {
        const response = await POST(change({ current_password: current, new_password }));
        expect(response.status).toBe(422);
        expect((await response.json()).fields).toHaveProperty('new_password');
      }
      for (const current_password of ['', 'c'.repeat(513)]) {
        const response = await POST(change({ current_password, new_password: next }));
        expect(response.status).toBe(422);
        expect((await response.json()).fields).toHaveProperty('current_password');
      }
      expect(fetcher).not.toHaveBeenCalled();
    });
    it('fails closed on missing configuration', async () => {
      vi.stubEnv('NEXTAUTH_SECRET', '');
      expect((await POST(change())).status).toBe(503);
      vi.stubEnv('NEXTAUTH_SECRET', 'nextauth-secret-for-tests-0123456789');
      vi.stubEnv('IDENTITY_URL', 'http://identity.internal');
      expect((await POST(change())).status).toBe(503);
      expect(fetcher).not.toHaveBeenCalled();
    });
  });

  it('never logs, echoes or returns either password', async () => {
    const outputs = [await POST(change()), await POST(change({ current_password: current, new_password: 'x' }))];
    for (const status of [401, 422, 429, 500]) { fetcher.mockResolvedValueOnce(envelope(status, 'x')); outputs.push(await POST(change())); }
    for (const response of outputs) {
      const text = await response.text();
      expect(text).not.toContain(current);
      expect(text).not.toContain(next);
    }
    for (const spy of spies) expect(spy).not.toHaveBeenCalled();
  });
});

describe('under the Authentik provider the route is unchanged', () => {
  it('still only returns the provider destination and never calls Identity', async () => {
    vi.stubEnv('AUTH_PROVIDER', 'authentik');
    vi.stubEnv('AUTHENTIK_ISSUER', 'https://id.test/application/o/bill/');
    const response = await POST(new NextRequest(`${AUTH_URL}/api/change-password`, { method: 'POST', headers: { origin: AUTH_URL } }));
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ destination: 'https://id.test/if/flow/bill-password-change/' });
    expect(fetcher).not.toHaveBeenCalled();
  });
});
