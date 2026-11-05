import { beforeEach, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { POST } from '../app/api/platform/route';
import { allowedPlatformRequest } from '../app/lib/platform-request';
const { token } = vi.hoisted(() => ({ token: vi.fn() }));
vi.mock('next-auth/jwt', () => ({ getToken: token }));
/*
 * The envelope now carries `service`, like the other two proxy routes: platform requests go
 * through the one shared boundary (`lib/service-proxy`) rather than this route's own copy of
 * the token preflight, and that boundary routes by service name. `platformCall` sends it.
 */
const request = (body: Record<string, unknown>, origin = 'http://localhost:4320') => new NextRequest('http://localhost:4320/api/platform', { method: 'POST', headers: { origin, 'Content-Type': 'application/json' }, body: JSON.stringify({ service: 'identity', ...body }) });
beforeEach(() => { vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ items: [], page: { has_more: false, next_cursor: null } }))); vi.stubEnv('NEXTAUTH_SECRET', 'unit-test'); vi.stubEnv('AUTH_URL', 'http://localhost:4310'); vi.stubEnv('IDENTITY_URL', 'http://localhost:8001'); token.mockResolvedValue({ accessToken: 'opaque-unit-token', accessTokenExpires: Date.now() + 60000 }); });
it('forwards only permitted platform paths with a server-side token', async () => {
  const response = await POST(request({ path: '/v1/platform/tenants?sort=name', method: 'GET' }));
  expect(response.status).toBe(200); expect(response.headers.get('Cache-Control')).toBe('no-store');
  expect(fetch).toHaveBeenCalledWith('http://localhost:8001/v1/platform/tenants?sort=name', expect.objectContaining({ redirect: 'error', headers: expect.objectContaining({ Authorization: 'Bearer opaque-unit-token' }) }));
});
it.each(['https://evil.invalid/v1/platform/tenants', '//evil.invalid/v1/platform/tenants', '/v1/session', '/v1/platform/tenants?email=private', '/v1/platform/tenants/../tenants'])('denies arbitrary targets %s', async path => {
  expect((await POST(request({ path, method: 'GET' }))).status).toBe(422); expect(fetch).not.toHaveBeenCalled();
});
it('rejects cross-origin writes before authentication', async () => { expect((await POST(request({ path: '/v1/platform/tenants', method: 'POST' }, 'https://evil.invalid'))).status).toBe(403); });
it('provides refresh recovery only for local token expiry', async () => { token.mockResolvedValue({ accessToken: 'expired', accessTokenExpires: 0 }); const response = await POST(request({ path: '/v1/platform/tenants', method: 'GET' })); expect(response.status).toBe(401); expect((await response.json()).error.code).toBe('session_expired'); expect(fetch).not.toHaveBeenCalled(); });
it('preserves real permission denial from Identity', async () => { vi.mocked(fetch).mockResolvedValue(Response.json({ error: { code: 'permission_denied' } }, { status: 403 })); expect((await POST(request({ path: '/v1/platform/tenants', method: 'GET' }))).status).toBe(403); });
it('bounds the JSON body', async () => { expect((await POST(request({ path: '/v1/platform/tenants', method: 'POST', body: 'x'.repeat(17000) }))).status).toBe(413); });
it('does not permit hard deletion', () => { expect(allowedPlatformRequest('DELETE', '/v1/platform/tenants/01900000-0000-7000-8000-000000000001')).toBe(false); });
it('allows account list, bounded sync, detail and review only', () => {
  const path='/v1/platform/accounts/01900000-0000-7000-8000-000000000001';
  expect(allowedPlatformRequest('GET','/v1/platform/accounts?status=pending&sort=name')).toBe(true);
  expect(allowedPlatformRequest('POST','/v1/platform/accounts/sync?page=2')).toBe(true);
  expect(allowedPlatformRequest('GET',path)).toBe(true);
  expect(allowedPlatformRequest('POST',path+'/review')).toBe(true);
  expect(allowedPlatformRequest('PATCH',path)).toBe(false);
  expect(allowedPlatformRequest('POST',path+'/set_password')).toBe(false);
  expect(allowedPlatformRequest('GET','/v1/platform/accounts?provider_url=evil')).toBe(false);
  expect(allowedPlatformRequest('GET','/v1/platform/accounts/pending-registration?email=owner%40example.invalid')).toBe(true);
  expect(allowedPlatformRequest('GET','/v1/platform/tenant-administrators/available?email=owner%40example.invalid')).toBe(true);
  expect(allowedPlatformRequest('GET','/v1/platform/tenant-administrators/available?email=owner%40example.invalid&email=other%40example.invalid')).toBe(false);
  expect(allowedPlatformRequest('POST','/v1/platform/accounts/pending-registration?email=owner%40example.invalid')).toBe(false);
  expect(allowedPlatformRequest('GET','/v1/platform/accounts/pending-registration?email=owner%40example.invalid&email=other%40example.invalid')).toBe(false);
});
it('rejects nested duplicate JSON members before forwarding', async () => {
  const input = new NextRequest('http://localhost:4320/api/platform', { method: 'POST', headers: { origin: 'http://localhost:4320', 'Content-Type': 'application/json' }, body: '{"service":"identity","path":"/v1/platform/references/languages","method":"POST","body":{"code":"zz","code":"yy"}}' });
  expect((await POST(input)).status).toBe(422); expect(fetch).not.toHaveBeenCalled();
});
it('allows only read and update of platform metadata', () => {
  expect(allowedPlatformRequest('GET', '/v1/platform/details')).toBe(true);
  expect(allowedPlatformRequest('PATCH', '/v1/platform/details')).toBe(true);
  expect(allowedPlatformRequest('POST', '/v1/platform/details')).toBe(false);
  expect(allowedPlatformRequest('GET', '/v1/platform/details?user=another')).toBe(false);
});

it('refuses another service, and an envelope field it does not recognise', async () => {
  expect((await POST(request({ service: 'accounting', path: '/v1/platform/tenants', method: 'GET' }))).status).toBe(422);
  expect((await POST(request({ path: '/v1/platform/tenants', method: 'GET', tenant: 'other' }))).status).toBe(422);
  expect(fetch).not.toHaveBeenCalled();
});
