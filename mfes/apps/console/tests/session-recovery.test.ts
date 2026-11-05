import { afterEach, expect, it, vi } from 'vitest';
import { sessionFetch } from '../app/lib/session-fetch';
import { productFieldRequest } from '../app/lib/product-fields';
const expired = () => Response.json({ error: { code: 'session_expired', message: 'Session expired' } }, { status: 401 });
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });
it('refreshes parallel API reads once and keeps browser credentials confined to Auth', async () => {
  const refreshed = new Set<string>();
  const fetcher = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes('/api/session/refresh')) {
      await new Promise((resolve) => setTimeout(resolve, 20)); return Response.json({ authenticated: true });
    }
    if (!refreshed.has(url)) { refreshed.add(url); return expired(); }
    return Response.json({ ok: true });
  });
  vi.stubGlobal('fetch', fetcher);
  const responses = await Promise.all([sessionFetch('/api/audit/a'), sessionFetch('/api/audit/b')]);
  expect(responses.every((response) => response.ok)).toBe(true);
  const calls = fetcher.mock.calls.filter(([input]) => String(input).includes('/api/session/refresh'));
  expect(calls).toHaveLength(1);
  expect(fetcher).toHaveBeenCalledWith('http://localhost:4310/api/session/refresh', expect.objectContaining({ credentials: 'include', redirect: 'error' }));
});
it('retains a money action and its idempotency key when retrying after expiry', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(expired()).mockResolvedValueOnce(Response.json({ authenticated: true }))
    .mockResolvedValueOnce(Response.json({ id: 'result' }));
  vi.stubGlobal('fetch', fetcher);
  expect(await productFieldRequest('vouchers', 'POST', '/v1/companies/company/vouchers', { amount: '100.0000' }, 'same-key'))
    .toEqual({ id: 'result' });
  expect(fetcher.mock.calls[2]).toEqual(fetcher.mock.calls[0]);
  expect(JSON.parse(fetcher.mock.calls[2][1].body)).toMatchObject({ key: 'same-key', body: { amount: '100.0000' } });
});
it('refreshes but does not automatically repeat a mutation without an idempotency key', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(expired()).mockResolvedValueOnce(Response.json({ authenticated: true }));
  vi.stubGlobal('fetch', fetcher);
  await expect(productFieldRequest('identity', 'PATCH', '/v1/user', {})).rejects.toThrow('Session expired');
  expect(fetcher).toHaveBeenCalledTimes(2);
});
it('does not replay a mutation whose idempotency key would be rejected by the proxy', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(expired()).mockResolvedValueOnce(Response.json({ authenticated: true }));
  vi.stubGlobal('fetch', fetcher);
  await expect(productFieldRequest('vouchers', 'POST', '/v1/vouchers', {}, 'invalid key')).rejects.toThrow('Session expired');
  expect(fetcher).toHaveBeenCalledTimes(2);
});
it.each([401, 403, 422, 500, 503])('does not refresh upstream authorization or ordinary API errors: %s', async (status) => {
  const fetcher = vi.fn(async () => Response.json({ error: { code: 'access_denied' } }, { status }));
  vi.stubGlobal('fetch', fetcher); expect((await sessionFetch('/api/product-fields')).status).toBe(status);
  expect(fetcher).toHaveBeenCalledTimes(1);
});
it.each([401, 503])('keeps the original expiry response when refresh cannot recover: %s', async (status) => {
  const fetcher = vi.fn().mockResolvedValueOnce(expired()).mockResolvedValueOnce(Response.json({ authenticated: false }, { status }));
  vi.stubGlobal('fetch', fetcher); expect((await sessionFetch('/api/product-fields')).status).toBe(401);
  expect(fetcher).toHaveBeenCalledTimes(2);
});
it('retries once and propagates expiry without an endless refresh loop', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(expired()).mockResolvedValueOnce(Response.json({ authenticated: true })).mockResolvedValueOnce(expired());
  vi.stubGlobal('fetch', fetcher); expect((await sessionFetch('/api/product-fields')).status).toBe(401);
  expect(fetcher).toHaveBeenCalledTimes(3);
});
