import { beforeEach, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { POST } from '../app/api/access/route';
const { token } = vi.hoisted(() => ({ token: vi.fn() }));
vi.mock('next-auth/jwt', () => ({ getToken: token }));
const request = (body: Record<string, unknown>, origin = 'http://localhost:4320') => new NextRequest('http://localhost:4320/api/access', { method: 'POST', headers: { origin, 'Content-Type': 'application/json' }, body: JSON.stringify({ service: 'identity', ...body }) });
beforeEach(() => {
  token.mockReset();
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ items: [], page: { has_more: false, next_cursor: null } })));
  vi.stubEnv('NEXTAUTH_SECRET', 'unit-test'); vi.stubEnv('AUTH_URL', 'http://localhost:4310'); vi.stubEnv('IDENTITY_URL', 'http://localhost:8001');
  token.mockResolvedValue({ accessToken: 'opaque-test-token', accessTokenExpires: Date.now() + 60000 });
});
it('forwards declared access reads with server credentials and no caching', async () => {
  const response = await POST(request({ path: '/v1/roles?limit=50', method: 'GET' }));
  expect(response.status).toBe(200); expect(response.headers.get('Cache-Control')).toBe('no-store');
  expect(fetch).toHaveBeenCalledWith('http://localhost:8001/v1/roles?limit=50', expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer opaque-test-token' }) }));
});
it('rejects arbitrary targets before forwarding', async () => {
  expect((await POST(request({ path: '/v1/session/api-tokens', method: 'GET' }))).status).toBe(422);
  expect(fetch).not.toHaveBeenCalled();
});
it('rejects cross-origin access changes before authentication', async () => {
  expect((await POST(request({ path: '/v1/roles', method: 'POST' }, 'https://evil.invalid'))).status).toBe(403);
  expect(token).not.toHaveBeenCalled();
});
it('returns upstream permission failures without granting UI authority', async () => {
  vi.mocked(fetch).mockResolvedValue(Response.json({ error: { code: 'permission_denied' } }, { status: 403 }));
  expect((await POST(request({ path: '/v1/roles', method: 'POST', body: {} }))).status).toBe(403);
});
it('denies expired sessions', async () => {
  token.mockResolvedValue({ accessToken: 'expired', accessTokenExpires: 0 });
  expect((await POST(request({ path: '/v1/roles', method: 'GET' }))).status).toBe(401);
  expect(fetch).not.toHaveBeenCalled();
});
it('rejects unrecognized envelope fields', async () => {
  expect((await POST(request({ path: '/v1/roles', method: 'GET', tenant_id: 'another-tenant' }))).status).toBe(422);
  expect(fetch).not.toHaveBeenCalled();
});
