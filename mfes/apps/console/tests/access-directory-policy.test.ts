import { expect, it } from 'vitest';
import { allowedAccessRequest } from '../app/lib/access-request-policy';
const id = '01990000-0000-7000-8000-000000000001';
it.each([
  ['GET', '/v1/users?limit=25&q=Ann&status=active'], ['POST', '/v1/users'],
  ['GET', `/v1/users/${id}`], ['PATCH', `/v1/users/${id}`],
  ['POST', `/v1/users/${id}/lifecycle`], ['POST', `/v1/users/${id}/deactivate`],
  ['GET', `/v1/users/${id}/invitations?limit=25`], ['POST', `/v1/users/${id}/invitations`],
  ['POST', `/v1/invitations/${id}/cancel`], ['POST', `/v1/roles/${id}/lifecycle`],
  ['GET', '/v1/session/companies?limit=50'], ['GET', `/v1/companies/${id}/departments?limit=50`],
  ['GET', '/v1/user-groups?limit=50'],
])('supports the explicit directory workflow: %s %s', (method, path) => expect(allowedAccessRequest('identity', method, path)).toBe(true));
it.each([
  '/v1/roles?limit=25&limit=200', '/v1/roles?%71=Ann&q=Bob', '/v1/%2e/roles',
  `/v1/users/${id}/identities`, '/v1/session/api-tokens', `/v1/users/${id}?tenant_id=${id}`,
])('refuses ambiguous or unrelated access routes: %s', path => expect(allowedAccessRequest('identity', 'GET', path)).toBe(false));
