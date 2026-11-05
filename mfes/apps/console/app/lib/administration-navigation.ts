const UUID = '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}';
export const administrationPages = {
  users: { href: '/users', label: 'Users', singular: 'user', sorts: ['updated_at', 'display_name', 'email'], filters: ['status', 'user_type'], maxSearch: 100 },
  roles: { href: '/roles', label: 'Roles', singular: 'role', sorts: ['name', 'key', 'updated_at'], filters: ['scope_hint'], maxSearch: 100 },
  departments: { href: '/departments', label: 'Departments', singular: 'department', sorts: ['path', 'code'], filters: ['is_active'], maxSearch: 20 },
  'user-groups': { href: '/user-groups', label: 'User groups', singular: 'user group', sorts: ['id', 'code'], filters: ['is_active'], maxSearch: 40 },
  assignments: { href: '/assignments', label: 'Assignments', singular: 'assignment', sorts: ['created_at'], filters: ['subject_type', 'subject_id', 'role_id', 'scope_type', 'active'], maxSearch: 0 },
  permissions: { href: '/permissions', label: 'Permissions', singular: 'permission', sorts: [], filters: [], maxSearch: 100 },
  companies: { href: '/companies/manage', label: 'Companies', singular: 'company', sorts: [], filters: ['status'], maxSearch: 100 },
  tenants: { href: '/platform/tenants', label: 'Tenants', singular: 'tenant', sorts: ['name', 'created_at'], filters: ['status'], maxSearch: 100 },
  'my-access': { href: '/my-access', label: 'My access', singular: 'access', sorts: [], filters: [], maxSearch: 0 },
} as const;
export type AdministrationResource = keyof typeof administrationPages;
const enums: Record<string, readonly string[]> = { status: ['invited', 'active', 'suspended', 'deactivated', 'closed'], user_type: ['tenant_user', 'customer_portal_user', 'service_account', 'platform_admin'], scope_hint: ['platform', 'tenant', 'company', 'department'], subject_type: ['user', 'user_group'], scope_type: ['tenant', 'company', 'department'], active: ['true', 'false'], is_active: ['true', 'false'] };
const statuses: Partial<Record<AdministrationResource, readonly string[]>> = { users: ['invited', 'active', 'suspended', 'deactivated'], companies: ['active', 'suspended', 'closed'], tenants: ['active', 'suspended', 'closed'] };
export function administrationResource(path: string): AdministrationResource | undefined {
  return (Object.keys(administrationPages) as AdministrationResource[]).find(key => path === administrationPages[key].href
    || ['users', 'roles', 'departments', 'user-groups', 'tenants'].includes(key) && new RegExp('^' + administrationPages[key].href + '/' + UUID + '$', 'i').test(path)
    || key === 'companies' && new RegExp('^/companies/' + UUID + '(?:/configuration|/gst-settings|/years(?:/next|/' + UUID + '(?:/continuity)?)?)?$', 'i').test(path));
}
/** Only implemented read/directory destinations; bounded nesting preserves related-page context. */
function checkedReturn(value: string | undefined, depth = 0): string | null {
  if (!value || value.length > 4096 || depth > 4 || !value.startsWith('/') || /[\\#\x00-\x1f\x7f]/.test(value)) return null;
  const url = new URL(value, 'https://console.invalid');
  if (url.origin !== 'https://console.invalid') return null;
  const path = url.pathname.toLowerCase(), resource = administrationResource(path);
  if (!resource) return ['/', '/organisation', '/organisation/access', '/platform', '/companies', '/settings', '/settings/company'].includes(path) && !url.search ? path : null;
  const page = administrationPages[resource], directory = path === page.href, params = new URLSearchParams();
  for (const [key, item] of url.searchParams) {
    if (url.searchParams.getAll(key).length !== 1 || /[\x00-\x1f\x7f]/.test(item)) continue;
    if (key === 'returnTo') { const parent = checkedReturn(item, depth + 1); if (parent && new URL(parent, url).pathname !== path) params.set(key, parent); continue; }
    if (resource === 'companies' && path.endsWith('/years/next') && key === 'sourceYear' && new RegExp('^' + UUID + '$', 'i').test(item)) { params.set(key, item.toLowerCase()); continue; }
    if (!directory) continue;
    if (key === 'q' && item.trim().length >= 2 && item.length <= page.maxSearch) params.set(key, item);
    else if (key === 'limit' && /^\d+$/.test(item) && +item >= 1 && +item <= 200) params.set(key, item);
    else if (key === 'sort' && item.split(',').every(part => (page.sorts as readonly string[]).includes(part.replace(/^-/, '')))) params.set(key, item);
    else if ((page.filters as readonly string[]).includes(key) && item.length <= 100 && (key.endsWith('_id') ? new RegExp('^' + UUID + '$', 'i').test(item) : (key === 'status' ? statuses[resource] : enums[key])?.includes(item))) params.set(key, item);
  }
  return path + (params.size ? '?' + params : '');
}
export function administrationReturn(resource: AdministrationResource, value?: string): string {
  try { return checkedReturn(value) ?? administrationPages[resource].href; } catch { return administrationPages[resource].href; }
}
export function administrationLink(path: string, back: string): string {
  const url = new URL(path, 'https://console.invalid');
  const target = checkedReturn(back);
  if (target) {
    if (new URL(target, url).pathname === url.pathname) {
      const resource = administrationResource(url.pathname);
      if (resource && url.pathname !== administrationPages[resource].href) return target;
      const parent = new URL(target, url).searchParams.get('returnTo');
      return parent ? administrationLink(path, parent) : url.pathname + url.search;
    }
    url.searchParams.set('returnTo', target);
  }
  return url.pathname + url.search;
}
export function administrationDirectoryReturn(resource: AdministrationResource, back: string) {
  let next: string | null = administrationReturn(resource, back);
  for (let depth = 0; next && depth <= 4; depth++) {
    const url: URL = new URL(next, 'https://console.invalid');
    if (url.pathname === administrationPages[resource].href) return next;
    next = url.searchParams.get('returnTo');
  }
  return administrationPages[resource].href;
}
export function administrationBackLabel(back: string) {
  const path = new URL(back, 'https://console.invalid').pathname, resource = administrationResource(path);
  if (path === '/organisation/access') return 'roles and access';
  if (resource === 'companies' && path.endsWith('/configuration')) return 'company configuration';
  if (resource === 'companies' && path.endsWith('/gst-settings')) return 'GST settings';
  if (resource === 'companies' && /\/years(?:\/[0-9a-f-]+)?$/.test(path)) return path.endsWith('/years') ? 'financial years' : 'financial year details';
  if (resource) return path === administrationPages[resource].href ? administrationPages[resource].label.toLowerCase() : administrationPages[resource].singular + ' details';
  return path.startsWith('/settings') ? 'company settings' : path === '/organisation' ? 'administration' : path === '/platform' ? 'platform administration' : path === '/companies' ? 'open a company' : 'business overview';
}
