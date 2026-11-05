import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { POST, runtime } from '../../app/api/local/recover/route';
import { BFF_SECRET, IDENTITY, LEAK, TOKEN, consoleSpies, envelope, localEnv, post } from './local-support';

const newPassword = 'A Brand New Passphrase 42!';
const send = (body: unknown, headers: Record<string, string> = {}) => POST(post('/api/local/recover', body, headers));
const inspect = (token: unknown = TOKEN) => send({ action: 'inspect', token });
const redeem = (overrides: Record<string, unknown> = {}) => send({ action: 'redeem', token: TOKEN, new_password: newPassword, ...overrides });
let fetcher: ReturnType<typeof vi.fn>;
let spies: ReturnType<typeof consoleSpies>;
beforeEach(() => {
  localEnv();
  fetcher = vi.fn(async () => Response.json({ valid: true }));
  vi.stubGlobal('fetch', fetcher);
  spies = consoleSpies();
});
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it('runs on the Node runtime', () => expect(runtime).toBe('nodejs'));

describe('inspect', () => {
  it('asks Identity whether the link is still good, with the BFF secret and nothing else', async () => {
    const response = await inspect();
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ valid: true });
    const [url, options] = fetcher.mock.calls[0];
    expect(String(url)).toBe(`${IDENTITY}/internal/v1/local-auth/password/recovery/inspect`);
    expect(options).toMatchObject({ method: 'POST', cache: 'no-store', redirect: 'error' });
    expect(options.headers['X-Auth-Bff-Secret']).toBe(BFF_SECRET);
    expect(JSON.parse(options.body)).toEqual({ token: TOKEN });
    expect(response.headers.get('cache-control')).toBe('no-store');
    expect(response.headers.get('referrer-policy')).toBe('no-referrer');
  });
  it('reports an unknown, expired or spent link as invalid', async () => {
    fetcher.mockResolvedValue(envelope(404, 'not_found'));
    const response = await inspect();
    expect(response.status).toBe(404);
    expect(await response.json()).toMatchObject({ valid: false, error: expect.stringContaining('invalid or has expired') });
  });
  it('passes a rate limit through and treats everything else as unavailable', async () => {
    fetcher.mockResolvedValueOnce(envelope(429, 'rate_limited'));
    const limited = await inspect();
    expect(limited.status).toBe(429);
    expect(limited.headers.get('retry-after')).toBe('60');
    for (const status of [400, 401, 500, 503]) { fetcher.mockResolvedValueOnce(envelope(status, 'x')); expect((await inspect()).status).toBe(503); }
    fetcher.mockRejectedValueOnce(new Error(LEAK));
    const failed = await inspect();
    expect(failed.status).toBe(503);
    expect(await failed.text()).not.toContain(LEAK);
  });
});

describe('redeem', () => {
  beforeEach(() => fetcher.mockResolvedValue(new Response(null, { status: 204 })));
  it('sets the new password through Identity and reports only that it worked', async () => {
    const response = await redeem();
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ redeemed: true });
    const [url, options] = fetcher.mock.calls[0];
    expect(String(url)).toBe(`${IDENTITY}/internal/v1/local-auth/password/recovery/redeem`);
    expect(options.headers['X-Auth-Bff-Secret']).toBe(BFF_SECRET);
    expect(JSON.parse(options.body)).toEqual({ token: TOKEN, new_password: newPassword });
  });
  it('reports a spent or expired link as invalid', async () => {
    fetcher.mockResolvedValue(envelope(404, 'not_found'));
    const response = await redeem();
    expect(response.status).toBe(404);
    expect(await response.json()).toMatchObject({ valid: false });
  });
  it.each([
    ['fields at the top level', Response.json({ error: { code: 'validation_error', message: LEAK }, fields: { new_password: LEAK } }, { status: 422 })],
    ['fields inside the error', Response.json({ error: { code: 'validation_error', message: LEAK, fields: { new_password: LEAK } } }, { status: 422 })],
  ])('maps a 422 on new_password (%s) to a fixed field error', async (_name, upstream) => {
    fetcher.mockResolvedValue(upstream);
    const response = await redeem();
    expect(response.status).toBe(422);
    const text = await response.text();
    expect(JSON.parse(text).fields.new_password).toMatch(/cannot be used/);
    expect(text).not.toContain(LEAK);
  });
  it('treats a 422 about some other field as unavailable', async () => {
    fetcher.mockResolvedValue(Response.json({ error: { code: 'validation_error', message: LEAK }, fields: { token: LEAK } }, { status: 422 }));
    expect((await redeem()).status).toBe(503);
    fetcher.mockResolvedValue(envelope(422, 'validation_error'));
    expect((await redeem()).status).toBe(503);
  });
  it('passes a rate limit through and treats everything else as unavailable', async () => {
    fetcher.mockResolvedValueOnce(envelope(429, 'rate_limited'));
    expect((await redeem()).status).toBe(429);
    for (const status of [400, 401, 403, 500]) { fetcher.mockResolvedValueOnce(envelope(status, 'x')); expect((await redeem()).status).toBe(503); }
    fetcher.mockRejectedValueOnce(new Error(newPassword));
    const failed = await redeem();
    expect(failed.status).toBe(503);
    expect(await failed.text()).not.toContain(newPassword);
  });
  it.each([['five characters', 'abcde'], ['129 characters', 'a'.repeat(129)], ['a control character', 'password\u0007x'], ['empty', '']])(
    'applies the registration password rule before calling Identity: %s', async (_name, value) => {
      const response = await redeem({ new_password: value });
      expect(response.status).toBe(422);
      expect((await response.json()).fields.new_password).toBeTruthy();
      expect(fetcher).not.toHaveBeenCalled();
    });
  it.each([['six characters', 'abcdef'], ['128 characters', 'a'.repeat(128)], ['128 emoji', '😀'.repeat(128)]])('accepts %s', async (_name, value) => {
    expect((await redeem({ new_password: value })).status).toBe(200);
  });
});

describe('request validation', () => {
  it.each(['', 'short', '../../admin', 'a b c d e f g h i j k l m n', 'x'.repeat(300), 'tok\nen_0a1b2c3d4e5f6071'])('does not forward the token %j', async token => {
    expect((await inspect(token)).status).toBe(422);
    expect((await redeem({ token })).status).toBe(422);
    expect(fetcher).not.toHaveBeenCalled();
  });
  it.each<[string, unknown]>([['an unknown action', { action: 'reset', token: TOKEN }], ['no action', { token: TOKEN }],
    ['inspect with a password', { action: 'inspect', token: TOKEN, new_password: newPassword }],
    ['redeem without a password', { action: 'redeem', token: TOKEN }], ['redeem with a non-string password', { action: 'redeem', token: TOKEN, new_password: 12345678 }],
    ['an extra field', { action: 'redeem', token: TOKEN, new_password: newPassword, user_id: 'x' }]])('rejects %s', async (_name, body) => {
    expect((await send(body)).status).toBe(422);
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('is hardened like the registration route', async () => {
    expect((await send({ action: 'inspect', token: TOKEN }, { origin: 'https://evil.test' })).status).toBe(403);
    expect((await send({ action: 'inspect', token: TOKEN }, { 'sec-fetch-site': 'cross-site' })).status).toBe(403);
    expect((await send({ action: 'inspect', token: TOKEN }, { 'content-type': 'text/plain' })).status).toBe(415);
    expect((await send({ action: 'inspect', token: TOKEN }, { 'content-length': '9999' })).status).toBe(413);
    expect((await send({ action: 'redeem', token: TOKEN, new_password: 'x'.repeat(5000) })).status).toBe(400);
    expect((await send('[]')).status).toBe(422);
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('is a 404 under the Authentik provider and fails closed on a missing BFF secret', async () => {
    vi.stubEnv('AUTH_LOCAL_BFF_SECRET', '');
    expect((await inspect()).status).toBe(503);
    vi.stubEnv('AUTH_PROVIDER', 'authentik');
    expect((await inspect()).status).toBe(404);
    expect(fetcher).not.toHaveBeenCalled();
  });
});

describe('secrets stay out of every output', () => {
  it('never logs, echoes or returns the token or the new password', async () => {
    const outputs = [await inspect(), await redeem()];
    for (const status of [404, 422, 429, 500]) {
      fetcher.mockResolvedValueOnce(envelope(status, 'x')); outputs.push(await inspect());
      fetcher.mockResolvedValueOnce(envelope(status, 'x')); outputs.push(await redeem());
    }
    outputs.push(await redeem({ new_password: 'x' }));
    for (const response of outputs) {
      const text = await response.text();
      expect(text).not.toContain(TOKEN);
      expect(text).not.toContain(newPassword);
      expect(response.headers.get('location')).toBeNull();
      expect(JSON.stringify([...response.headers])).not.toContain(TOKEN);
    }
    for (const spy of spies) expect(spy).not.toHaveBeenCalled();
  });
});
