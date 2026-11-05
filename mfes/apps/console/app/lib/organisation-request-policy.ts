/** Fixed organization operations; no entity hard-delete surface. */
export function allowedOrganisationRequest(method: string, url: URL): boolean | undefined {
  const id = '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}';
  const keys = (...allowed: string[]) => [...url.searchParams.keys()].every(key => allowed.includes(key));
  const query = (allowed: string[], sorts: string[]) => keys(...allowed) && [...url.searchParams].every(([key, value]) => {
    if (/[\x00-\x1f\x7f]/.test(value)) return false;
    if (key === 'limit') return /^\d+$/.test(value) && Number(value) >= 1 && Number(value) <= 200;
    if (key === 'cursor') return value.length > 0 && value.length <= 2048;
    if (key === 'id') return new RegExp('^' + id + '$', 'i').test(value);
    if (key === 'user_id' || key === 'department_id') return new RegExp('^' + id + '$', 'i').test(value);
    if (key === 'sort') return sorts.includes(value.replace(/^-/, ''));
    if (key === 'is_active') return ['true', 'false'].includes(value);
    if (key === 'operation') return ['create', 'update'].includes(value);
    return key === 'q' && value.length >= 2 && value.length <= (url.pathname.includes('departments') ? 20 : 40);
  });
  const department = new RegExp('^/v1/companies/' + id + '/departments', 'i');
  if (url.pathname === '/v1/user-groups' || new RegExp(department.source + '$', 'i').test(url.pathname)) return method === 'GET' ? query(['limit', 'cursor', 'q', 'sort', 'id', 'is_active'], url.pathname.includes('departments') ? ['path', 'code'] : ['id', 'code']) : method === 'POST' && !url.search;
  if (url.pathname === '/v1/user-groups/field-set' || new RegExp(department.source + '/field-set$', 'i').test(url.pathname)) return method === 'GET' && query(url.pathname.includes('departments') ? ['operation', 'id'] : ['operation'], []);
  if (new RegExp(department.source + '/' + id + '$', 'i').test(url.pathname) || new RegExp('^/v1/user-groups/' + id + '$', 'i').test(url.pathname)) return !url.search && ['GET', 'PATCH'].includes(method);
  if (new RegExp(department.source + '/' + id + '/(reparent|lifecycle)$', 'i').test(url.pathname) || new RegExp('^/v1/user-groups/' + id + '/lifecycle$', 'i').test(url.pathname)) return method === 'POST' && !url.search;
  if (new RegExp('^/v1/user-groups/' + id + '/members$', 'i').test(url.pathname)) return method === 'GET' ? query(['limit', 'cursor'], []) : method === 'POST' && !url.search;
  if (new RegExp('^/v1/user-groups/' + id + '/members/' + id + '$', 'i').test(url.pathname)) return method === 'DELETE' && !url.search;
  if (new RegExp('^/v1/companies/' + id + '/memberships$', 'i').test(url.pathname)) return method === 'GET' ? query(['limit', 'cursor', 'user_id', 'department_id', 'is_active'], []) : method === 'POST' && !url.search;
  if (new RegExp('^/v1/memberships/' + id + '/(end|make-primary)$', 'i').test(url.pathname)) return method === 'POST' && !url.search;
  return undefined;
}
