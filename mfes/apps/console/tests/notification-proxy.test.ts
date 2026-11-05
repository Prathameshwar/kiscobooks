import { beforeEach, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { POST } from '../app/api/notifications/route';
const { token } = vi.hoisted(() => ({ token: vi.fn() }));
vi.mock('next-auth/jwt', () => ({ getToken: token }));
const request = (body: Record<string, unknown>, origin = 'http://localhost:4320') => new NextRequest('http://localhost:4320/api/notifications', { method: 'POST', headers: { origin, 'Content-Type': 'application/json' }, body: JSON.stringify({ service: 'notification', ...body }) });
beforeEach(() => {
  token.mockReset();
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ items: [], page: { has_more: false, next_cursor: null } })));
  vi.stubEnv('NEXTAUTH_SECRET', 'unit-test'); vi.stubEnv('AUTH_URL', 'http://localhost:4310'); vi.stubEnv('NOTIFICATION_GATEWAY_URL', 'http://localhost:8000/notification');
  token.mockResolvedValue({ accessToken: 'opaque-test-token', accessTokenExpires: Date.now() + 60000 });
});
it('forwards scoped management reads with server credentials and no caching', async () => {
  const response = await POST(request({ path: '/v1/platform/templates?limit=50', method: 'GET' }));
  expect(response.status).toBe(200); expect(response.headers.get('Cache-Control')).toBe('no-store');
  expect(fetch).toHaveBeenCalledWith('http://localhost:8000/notification/v1/platform/templates?limit=50', expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer opaque-test-token' }) }));
});
it.each([200, 403, 500])('reports a non-JSON upstream response with status %s as a safe failure', async status => {
  vi.mocked(fetch).mockResolvedValue(new Response('<html>upstream error</html>', { status }));
  const response = await POST(request({ path: '/v1/channels', method: 'GET' }));
  expect(response.status).toBe(status === 200 ? 502 : status);
  expect(await response.json()).toEqual({ error: { message: 'Unexpected service response' } });
});
it('rejects callbacks and forged ownership before forwarding', async () => {
  expect((await POST(request({ path: '/v1/callbacks/email/key', method: 'POST' }))).status).toBe(422);
  expect((await POST(request({ path: '/v1/templates', method: 'GET', tenant_id: 'another' }))).status).toBe(422);
  expect(fetch).not.toHaveBeenCalled();
});
it('rejects cross-origin writes before authentication', async () => {
  expect((await POST(request({ path: '/v1/templates', method: 'POST' }, 'https://evil.invalid'))).status).toBe(403);
  expect(token).not.toHaveBeenCalled();
});
it.each([401, 403, 422, 500])('preserves upstream error status %s', async status => {
  vi.mocked(fetch).mockResolvedValue(Response.json({ error: { code: 'request_failed' } }, { status }));
  expect((await POST(request({ path: '/v1/templates', method: 'GET' }))).status).toBe(status);
});
it('denies expired sessions and unavailable service configuration', async () => {
  token.mockResolvedValue({ accessToken: 'expired', accessTokenExpires: 0 });
  expect((await POST(request({ path: '/v1/templates', method: 'GET' }))).status).toBe(401);
  expect(fetch).not.toHaveBeenCalled();
});
it.each(['consent-events', 'suppressions', 'routing-rules'])('forwards %s commands with an unchanged body and replay key', async path => {
  const body = { reason: 'Recorded evidence', source_event_key: 'evidence-123' };
  expect((await POST(request({ path: '/v1/platform/' + path, method: 'POST', body, key: 'command-123' }))).status).toBe(200);
  expect(fetch).toHaveBeenCalledWith('http://localhost:8000/notification/v1/platform/' + path, expect.objectContaining({
    method: 'POST', body: JSON.stringify(body), headers: expect.objectContaining({ 'Idempotency-Key': 'command-123' }),
  }));
});
