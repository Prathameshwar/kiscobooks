import { allowedOrganisationRequest } from './organisation-request-policy';
/** Fixed access-management API surface; authorization remains with Identity. */
export function allowedAccessRequest(service: string, method: string, path: string): boolean {
  if (service !== 'identity' || path.length > 3000 || !path.startsWith('/v1/') || /[\\#\x00-\x20\x7f]/.test(path) || path.includes('..') || /%2f|%5c|%2e/i.test(path.split('?')[0]!)) return false;
  let url: URL;
  try { url = new URL(path, 'https://access.invalid'); } catch { return false; }
  if (url.origin !== 'https://access.invalid') return false;
  if (url.pathname !== path.split('?')[0]) return false;
  const queryKeys = [...url.searchParams.keys()];
  if (new Set(queryKeys).size !== queryKeys.length) return false;
  const organisation = allowedOrganisationRequest(method, url);
  if (organisation !== undefined) return organisation;
  const id = '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}';
  const keys = (...allowed: string[]) => [...url.searchParams.keys()].every(key => allowed.includes(key));
  if (url.pathname === '/v1/roles') return method === 'GET' ? keys('limit', 'cursor', 'q', 'sort', 'scope_hint') : method === 'POST' && !url.search;
  if (url.pathname === '/v1/role-assignments') return method === 'GET' ? keys('limit', 'cursor', 'subject_id', 'subject_type', 'role_id', 'scope_type', 'active', 'sort') : method === 'POST' && !url.search;
  if (url.pathname === '/v1/role-assignments/check') return method === 'POST' && !url.search;
  if (url.pathname === '/v1/permissions') return method === 'GET' && !url.search;
  if (url.pathname === '/v1/users') return method === 'GET' ? keys('limit', 'cursor', 'q', 'sort', 'status', 'user_type') : method === 'POST' && !url.search;
  if (url.pathname === '/v1/session/companies') return method === 'GET' && keys('limit', 'cursor', 'q', 'id');
  if (new RegExp('^/v1/companies/' + id + '/users$', 'i').test(url.pathname)) return method === 'GET' ? keys('limit', 'cursor', 'sort', 'q', 'status') : method === 'POST' && !url.search;
  if (new RegExp('^/v1/companies/' + id + '/users/' + id + '$', 'i').test(url.pathname)) return method === 'GET' && !url.search;
  if (new RegExp('^/v1/users/' + id + '/invitations$', 'i').test(url.pathname)) return method === 'GET' ? keys('limit', 'cursor') : method === 'POST' && !url.search;
  if (url.search) return false;
  if (new RegExp('^/v1/roles/' + id + '$', 'i').test(url.pathname)) return ['GET', 'PATCH'].includes(method);
  if (new RegExp('^/v1/roles/' + id + '/clone$', 'i').test(url.pathname)) return method === 'POST';
  if (new RegExp('^/v1/roles/' + id + '/lifecycle$', 'i').test(url.pathname)) return method === 'POST';
  if (new RegExp('^/v1/users/' + id + '$', 'i').test(url.pathname)) return ['GET', 'PATCH'].includes(method);
  if (new RegExp('^/v1/users/' + id + '/(lifecycle|deactivate|password-recovery)$', 'i').test(url.pathname)) return method === 'POST';
  if (new RegExp('^/v1/invitations/' + id + '/cancel$', 'i').test(url.pathname)) return method === 'POST';
  return method === 'POST' && new RegExp('^/v1/role-assignments/' + id + '/(revoke|regrant)$', 'i').test(url.pathname);
}
