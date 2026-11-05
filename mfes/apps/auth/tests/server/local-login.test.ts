import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { GET, POST, runtime } from '../../app/api/local/login/route';
import { AUTH_URL, BFF_SECRET, IDENTITY, LEAK, REQUEST_ID, consoleSpies, envelope, localEnv, post } from './local-support';

const callback = `${AUTH_URL}/api/auth/callback/local?code=abc&state=xyz`;
const password = 'Correct Horse 9! battery';
const login = (overrides: Record<string, unknown> = {}, headers: Record<string, string> = {}) =>
  post('/api/local/login', { request_id: REQUEST_ID, email: 'Person@Example.Test ', password, ...overrides }, headers);
let fetcher: ReturnType<typeof vi.fn>;
let spies: ReturnType<typeof consoleSpies>;
beforeEach(() => {
  localEnv();
  fetcher = vi.fn(async () => Response.json({ redirect_to: callback }));
  vi.stubGlobal('fetch', fetcher);
  spies = consoleSpies();
});
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe('POST /api/local/login', () => {
  it.each(['tenant1', ' TENANT1 ', 'tenant1@gmail.com'])('accepts username or email: %s', async identifier => {
    const response = await POST(post('/api/local/login', { request_id: REQUEST_ID, identifier, password }));
    expect(response.status).toBe(200);
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({ request_id: REQUEST_ID, identifier: identifier.trim().toLowerCase(), password });
  });
  it('rejects simultaneous identifier and legacy email fields', async () => {
    const response = await POST(login({ identifier: 'tenant1' }));
    expect(response.status).toBe(422);
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('accepts generated administrator usernames', async () => {
    expect((await POST(login({ email: 'bill-admin-' + 'a'.repeat(32) }))).status).toBe(200);
  });
  it('runs on the Node runtime', () => expect(runtime).toBe('nodejs'));
  it('signs in through Identity with the BFF secret and returns the callback to follow', async () => {
    const response = await POST(login());
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ redirect_to: callback });
    expect(response.headers.get('cache-control')).toBe('no-store');
    expect(response.headers.get('referrer-policy')).toBe('no-referrer');
    const [url, options] = fetcher.mock.calls[0];
    expect(String(url)).toBe(`${IDENTITY}/internal/v1/local-auth/login`);
    expect(options).toMatchObject({ method: 'POST', cache: 'no-store', redirect: 'error' });
    expect(options.signal).toBeInstanceOf(AbortSignal);
    expect(options.headers['X-Auth-Bff-Secret']).toBe(BFF_SECRET);
    // The email is normalised; the password is passed through untouched.
    expect(JSON.parse(options.body)).toEqual({ request_id: REQUEST_ID, identifier: 'person@example.test', password });
  });
  it('never forwards the caller cookies or authorization', async () => {
    await POST(login({}, { cookie: 'session=private', authorization: 'Bearer private' }));
    expect(JSON.stringify(fetcher.mock.calls[0][1].headers)).not.toMatch(/private/i);
  });

  describe('maps every upstream outcome to a fixed, safe message', () => {
    it('401 is one message whether the email or the password was wrong', async () => {
      fetcher.mockResolvedValue(envelope(401, 'invalid_credentials'));
      const response = await POST(login());
      expect(response.status).toBe(401);
      expect(await response.json()).toEqual({ error: 'Username, email or password is incorrect.', code: 'invalid_credentials' });
    });
    it('403 account_pending says the account awaits approval', async () => {
      fetcher.mockResolvedValue(envelope(403, 'account_pending'));
      const response = await POST(login());
      expect(response.status).toBe(403);
      expect((await response.json()).error).toMatch(/waiting for administrator approval/);
    });
    it('403 with any other code is treated as unavailable rather than guessed', async () => {
      fetcher.mockResolvedValue(envelope(403, 'something_else'));
      expect((await POST(login())).status).toBe(503);
    });
    it('404 says the sign-in request expired and to start again', async () => {
      fetcher.mockResolvedValue(envelope(404, 'not_found'));
      const response = await POST(login());
      expect(response.status).toBe(404);
      expect(await response.json()).toMatchObject({ code: 'request_expired', error: expect.stringContaining('expired') });
    });
    it.each([[900, 15], [901, 16], [60, 1], [1, 1], [90_000, 1440]])('423 with retry_after %is reports %i minutes', async (seconds, minutes) => {
      fetcher.mockResolvedValue(envelope(423, 'account_locked', { retry_after: seconds }));
      const response = await POST(login());
      expect(response.status).toBe(423);
      const body = await response.json();
      expect(body).toMatchObject({ code: 'account_locked', retry_after_minutes: minutes });
      expect(body.error).toContain(`${minutes} minute`);
    });
    it('423 also reads retry_after from the error object or the header, and degrades without one', async () => {
      fetcher.mockResolvedValueOnce(Response.json({ error: { code: 'account_locked', message: LEAK, retry_after: 120 } }, { status: 423 }));
      expect((await (await POST(login())).json()).retry_after_minutes).toBe(2);
      fetcher.mockResolvedValueOnce(envelope(423, 'account_locked', {}, { 'Retry-After': '300' }));
      expect((await (await POST(login())).json()).retry_after_minutes).toBe(5);
      fetcher.mockResolvedValueOnce(envelope(423, 'account_locked', { retry_after: 'soon' }));
      const body = await (await POST(login())).json();
      expect(body).not.toHaveProperty('retry_after_minutes');
      expect(body.error).toContain('try again later');
    });
    it('429 says too many attempts and asks the browser to wait', async () => {
      fetcher.mockResolvedValue(envelope(429, 'rate_limited'));
      const response = await POST(login());
      expect(response.status).toBe(429);
      expect(response.headers.get('retry-after')).toBe('60');
      expect((await response.json()).error).toMatch(/Too many attempts/);
    });
    it.each([400, 422, 500, 502, 503])('%i is a temporary failure', async status => {
      fetcher.mockResolvedValue(envelope(status, 'internal'));
      const response = await POST(login());
      expect(response.status).toBe(503);
      expect((await response.json()).error).toBe('Sign in is temporarily unavailable. Please try again.');
    });
    it('a network failure or timeout is a temporary failure', async () => {
      fetcher.mockRejectedValue(new Error(`connect ECONNREFUSED ${LEAK}`));
      const response = await POST(login());
      expect(response.status).toBe(503);
      expect(await response.text()).not.toContain('ECONNREFUSED');
    });
    it('an unreadable success body is a temporary failure', async () => {
      fetcher.mockResolvedValue(new Response('<html>not json</html>', { status: 200 }));
      expect((await POST(login())).status).toBe(503);
    });
    it.each([401, 403, 404, 423, 429, 500])('never echoes upstream text or the password (%i)', async status => {
      fetcher.mockResolvedValue(envelope(status, status === 403 ? 'account_pending' : 'x', { retry_after: 60, detail: LEAK }));
      const response = await POST(login());
      const text = await response.text();
      expect(text).not.toContain(LEAK);
      expect(text).not.toContain(password);
      expect(text).not.toContain(BFF_SECRET);
    });
  });

  describe('only this app\'s own NextAuth callback is ever returned', () => {
    it.each([
      ['another origin', 'https://evil.test/api/auth/callback/local?code=1&state=2'],
      ['a look-alike host', 'https://auth.test.evil.test/api/auth/callback/local'],
      ['a userinfo trick', 'https://auth.test@evil.test/api/auth/callback/local'],
      ['credentials on our origin', 'https://user:pw@auth.test/api/auth/callback/local'],
      ['a different scheme', 'http://auth.test/api/auth/callback/local'],
      ['a different port', 'https://auth.test:8443/api/auth/callback/local'],
      ['another path on our origin', 'https://auth.test/setup'],
      ['a parent path escape', 'https://auth.test/api/auth/callback/../signin'],
      ['an encoded parent escape', 'https://auth.test/api/auth/callback/%2e%2e/signin'],
      ['a relative URL', '/api/auth/callback/local?code=1'],
      ['a scripted URL', 'javascript:alert(1)'],
      ['a data URL', 'data:text/html,<script>alert(1)</script>'],
      ['a fragment', 'https://auth.test/api/auth/callback/local#x'],
      ['an empty value', ''],
      ['a non-string', 42],
    ])('rejects %s', async (_name, redirect_to) => {
      fetcher.mockResolvedValue(Response.json({ redirect_to }));
      const response = await POST(login());
      expect(response.status).toBe(503);
      const text = await response.text();
      expect(text).not.toContain('evil');
      expect(text).not.toContain('redirect_to');
    });
    it('accepts the callback of any NextAuth provider id on this origin', async () => {
      fetcher.mockResolvedValue(Response.json({ redirect_to: `${AUTH_URL}/api/auth/callback/other?code=a` }));
      expect((await POST(login())).status).toBe(200);
    });
  });

  describe('browser hardening matches /api/registration', () => {
    it.each<[string, Record<string, string>]>([['a foreign origin', { origin: 'https://evil.test' }], ['an empty origin', { origin: '' }],
      ['a similar origin', { origin: 'https://auth.test.evil.test' }], ['a cross-site fetch', { 'sec-fetch-site': 'cross-site' }]])('refuses %s', async (_name, headers) => {
      const response = await POST(login({}, headers));
      expect(response.status).toBe(403);
      expect(fetcher).not.toHaveBeenCalled();
    });
    it('refuses a request with no Origin header at all', async () => {
      const request = new NextRequest(`${AUTH_URL}/api/local/login`, { method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ request_id: REQUEST_ID, email: 'a@b.test', password }) });
      expect((await POST(request)).status).toBe(403);
      expect(fetcher).not.toHaveBeenCalled();
    });
    it('accepts only JSON', async () => {
      for (const type of ['text/plain', 'application/x-www-form-urlencoded', 'multipart/form-data', '']) {
        expect((await POST(login({}, { 'content-type': type }))).status).toBe(415);
      }
      expect(fetcher).not.toHaveBeenCalled();
    });
    it('bounds the body by declared length and by the stream itself', async () => {
      expect((await POST(login({}, { 'content-length': '5000' }))).status).toBe(413);
      expect((await POST(login({ password: 'x'.repeat(6000) }))).status).toBe(400);
      expect((await POST(post('/api/local/login', '{"request_id":'))).status).toBe(400);
      expect(fetcher).not.toHaveBeenCalled();
    });
    it.each([['an array', '[]'], ['null', 'null'], ['a string', '"x"']])('refuses %s as the body', async (_name, body) => {
      expect((await POST(post('/api/local/login', body))).status).toBe(422);
      expect(fetcher).not.toHaveBeenCalled();
    });
    it('rejects extra fields (no mass assignment) and missing or mistyped ones', async () => {
      for (const body of [{ request_id: REQUEST_ID, email: 'a@b.test', password, admin: true },
        { request_id: REQUEST_ID, email: 'a@b.test' }, { email: 'a@b.test', password },
        { request_id: REQUEST_ID, email: 'a@b.test', password: 123 }, { request_id: [REQUEST_ID], email: 'a@b.test', password }]) {
        expect((await POST(post('/api/local/login', body))).status).toBe(422);
      }
      expect(fetcher).not.toHaveBeenCalled();
    });
    it.each(['', 'short', '../../admin', 'a/b/c/d/e/f/g/h/i/j/k', 'has space in the id value', 'x'.repeat(300), 'id with\nnewline12345'])(
      'does not send an invalid request id upstream: %j', async request_id => {
        expect((await POST(login({ request_id }))).status).toBe(422);
        expect(fetcher).not.toHaveBeenCalled();
      });
    it.each(['', 'ab', 'a@b', 'bad/name', 'has space', 'a b@c.test', `${'a'.repeat(250)}@b.test`])('does not send an invalid email upstream: %j', async email => {
      expect((await POST(login({ email }))).status).toBe(422);
      expect(fetcher).not.toHaveBeenCalled();
    });
    it('does not send an empty or oversized password upstream', async () => {
      expect((await POST(login({ password: '' }))).status).toBe(422);
      expect((await POST(login({ password: 'p'.repeat(513) }))).status).toBe(422);
      expect(fetcher).not.toHaveBeenCalled();
    });
  });

  describe('credentials stay out of every output', () => {
    it('logs nothing, on success or on any failure', async () => {
      await POST(login());
      for (const status of [401, 403, 404, 423, 429, 500]) { fetcher.mockResolvedValueOnce(envelope(status, 'account_pending')); await POST(login()); }
      fetcher.mockRejectedValueOnce(new Error(`boom ${password}`));
      const failed = await POST(login());
      expect(await failed.text()).not.toContain(password);
      for (const spy of spies) expect(spy).not.toHaveBeenCalled();
    });
    it('does not echo the password in validation errors', async () => {
      const response = await POST(login({ email: 'bad' }));
      expect(await response.text()).not.toContain(password);
    });
  });

  describe('configuration', () => {
    it('is a 404 when the Authentik provider is configured, and never calls Identity', async () => {
      vi.stubEnv('AUTH_PROVIDER', 'authentik');
      expect((await POST(login())).status).toBe(404);
      expect((await GET(new NextRequest(`${AUTH_URL}/api/local/login?request=${REQUEST_ID}`))).status).toBe(404);
      expect(fetcher).not.toHaveBeenCalled();
    });
    it.each([['AUTH_LOCAL_BFF_SECRET', ''], ['AUTH_LOCAL_BFF_SECRET', 'too-short'], ['IDENTITY_URL', 'http://identity.internal'], ['NEXTAUTH_URL', '']])(
      'fails closed with %s=%j', async (name, value) => {
        vi.stubEnv(name, value);
        const response = await POST(login());
        expect(response.status).toBe(503);
        expect(fetcher).not.toHaveBeenCalled();
      });
  });
});

describe('GET /api/local/login (is the sign-in request still open?)', () => {
  const get = (query = `?request=${REQUEST_ID}`, headers: Record<string, string> = {}) =>
    GET(new NextRequest(`${AUTH_URL}/api/local/login${query}`, { headers }));
  it('reports an open request', async () => {
    fetcher.mockResolvedValue(Response.json({ expires_at: '2026-10-31T10:00:00Z' }));
    const response = await get();
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ valid: true });
    const [url, options] = fetcher.mock.calls[0];
    expect(String(url)).toBe(`${IDENTITY}/internal/v1/local-auth/requests/${REQUEST_ID}`);
    expect(options.headers['X-Auth-Bff-Secret']).toBe(BFF_SECRET);
    expect(options).toMatchObject({ cache: 'no-store', redirect: 'error' });
  });
  it('reports an unknown, expired or used request as expired', async () => {
    fetcher.mockResolvedValue(envelope(404, 'not_found'));
    const response = await get();
    expect(response.status).toBe(404);
    expect(await response.json()).toMatchObject({ valid: false });
  });
  it.each([500, 401, 503])('treats %i as unavailable, not as expired', async status => {
    fetcher.mockResolvedValue(envelope(status, 'x'));
    expect((await get()).status).toBe(503);
  });
  it('treats a network failure as unavailable', async () => {
    fetcher.mockRejectedValue(new Error(LEAK));
    const response = await get();
    expect(response.status).toBe(503);
    expect(await response.text()).not.toContain(LEAK);
  });
  it.each(['', '?request=', '?request=short', '?request=../../etc/passwd', '?request=a%2Fb%2Fc%2Fd%2Fe%2Ff%2Fg%2Fh%2Fi'])('never sends an invalid id (%j) anywhere', async query => {
    expect((await get(query)).status).toBe(404);
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('refuses a cross-site fetch', async () => {
    expect((await get(undefined, { 'sec-fetch-site': 'cross-site' })).status).toBe(403);
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('is not cacheable', async () => {
    fetcher.mockResolvedValue(Response.json({ expires_at: 'x' }));
    expect((await get()).headers.get('cache-control')).toBe('no-store');
  });
});
