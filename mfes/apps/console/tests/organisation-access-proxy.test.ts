import { beforeEach, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { proxyServiceRequest } from '../app/lib/service-proxy';
import { allowedAccessRequest } from '../app/lib/access-request-policy';
import { companyId, userId, roleId } from './access-fixtures';
const { token } = vi.hoisted(() => ({ token: vi.fn() }));
vi.mock('next-auth/jwt', () => ({ getToken: token }));
beforeEach(() => {
  vi.stubEnv('NEXTAUTH_SECRET', 'unit-test'); vi.stubEnv('AUTH_URL', 'http://localhost:4310');
  token.mockResolvedValue({ accessToken: 'opaque-test-token', accessTokenExpires: Date.now() + 60000 });
});
it('normalizes a successful no-content membership removal for JSON clients', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
  const request = new NextRequest('http://localhost:4320/api/access', { method: 'POST', headers: { origin: 'http://localhost:4320', 'Content-Type': 'application/json' }, body: JSON.stringify({ service: 'identity', method: 'DELETE', path: '/v1/user-groups/' + roleId + '/members/' + userId }) });
  const response = await proxyServiceRequest(request, { allow: () => true, base: () => 'http://localhost:8001', subject: 'access' });
  expect(response.status).toBe(200); expect(await response.json()).toEqual({ ok: true });
});
it('allows only the declared organization paths and methods', () => {
  const dept = '/v1/companies/' + companyId + '/departments', group = '/v1/user-groups/' + roleId;
  for (const [method, path] of [['POST', dept], ['GET', dept + '?is_active=false&sort=code'], ['GET', dept + '/field-set?operation=update&id=' + userId], ['GET', dept + '/' + userId], ['PATCH', dept + '/' + userId], ['POST', dept + '/' + userId + '/reparent'], ['POST', dept + '/' + userId + '/lifecycle'], ['POST', '/v1/user-groups'], ['GET', '/v1/user-groups?is_active=true&sort=code&id=' + roleId], ['GET', '/v1/user-groups/field-set?operation=create'], ['GET', group], ['PATCH', group], ['POST', group + '/lifecycle'], ['GET', group + '/members?limit=50'], ['POST', group + '/members'], ['DELETE', group + '/members/' + userId]]) expect(allowedAccessRequest('identity', method!, path!), method + ' ' + path).toBe(true);
  for (const [method, path] of [['DELETE', group], ['DELETE', dept + '/' + userId], ['POST', group + '?tenant_id=x'], ['GET', dept + '/field-set?operation=create&operation=update'], ['GET', group + '/members?arbitrary=true'], ['POST', group + '/members/' + userId], ['GET', '/v1/user-groups/field-set?operation=invalid'], ['GET', dept + '?is_active=invalid']]) expect(allowedAccessRequest('identity', method!, path!)).toBe(false);
});
