import { expect, it } from 'vitest';
import { allowedAccessRequest } from '../app/lib/access-request-policy';

const id = '01990000-0000-7000-8000-000000000001';
it.each([
  ['GET', '/v1/roles?limit=50&cursor=opaque'], ['POST', '/v1/roles'],
  ['GET', '/v1/roles/' + id], ['PATCH', '/v1/roles/' + id],
  ['POST', '/v1/roles/' + id + '/clone'], ['GET', '/v1/permissions'],
  ['GET', '/v1/role-assignments?role_id=' + id], ['POST', '/v1/role-assignments'],
  ['POST', '/v1/role-assignments/' + id + '/revoke'],
])('allows %s %s', (method, path) => expect(allowedAccessRequest('identity', method, path)).toBe(true));
it.each([
  ['catalog', 'GET', '/v1/roles'], ['identity', 'DELETE', '/v1/roles/' + id],
  ['identity', 'GET', '/v1/roles?tenant_id=' + id], ['identity', 'GET', '/internal/v1/gateway/authorize'],
  ['identity', 'GET', 'https://evil.invalid/v1/roles'], ['identity', 'GET', '//evil.invalid/v1/roles'],
  ['identity', 'GET', '/v1/roles/../users'], ['identity', 'GET', '/v1/roles/%2fusers'],
  ['identity', 'GET', '/v1/roles#fragment'], ['identity', 'POST', '/v1/roles/' + id + '/clone?x=1'],
])('rejects %s %s %s', (service, method, path) => expect(allowedAccessRequest(service, method, path)).toBe(false));
