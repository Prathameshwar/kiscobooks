/** Fixed platform boundary. Browser input cannot select another service or URL. */
export function allowedPlatformRequest(method: string, path: string): boolean {
  if (!path.startsWith('/v1/platform/') || path.length > 3000 || path.includes('\\') || path.includes('..') || path.includes('#') || /%2f|%5c/i.test(path)) return false;
  let url: URL;
  try { url = new URL(path, 'https://platform.invalid'); } catch { return false; }
  if (url.origin !== 'https://platform.invalid') return false;
  if (url.pathname === '/v1/platform/system-roles') return method === 'GET' && !url.search;
  if (url.pathname === '/v1/platform/system-roles/reconcile') return method === 'POST' && !url.search;
  if (url.pathname.startsWith('/v1/platform/access/')) {
    const id = '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}';
    const tenant = '^/v1/platform/access/tenants/' + id;
    const keys = [...url.searchParams.keys()];
    if (new Set(keys).size !== keys.length) return false;
    if (url.pathname === '/v1/platform/access/role') return method === 'GET' && !url.search;
    if (url.pathname === '/v1/platform/access/tenants') return method === 'GET' && keys.every(key => ['q', 'limit', 'cursor'].includes(key));
    if (new RegExp(tenant + '$', 'i').test(url.pathname)) return method === 'GET' && !url.search;
    if (new RegExp(tenant + '/administrators$', 'i').test(url.pathname)) return method === 'POST' ? !url.search : method === 'GET' && keys.every(key => ['q', 'status', 'sort', 'limit', 'cursor'].includes(key));
    if (new RegExp(tenant + '/administrators/' + id + '$', 'i').test(url.pathname)) return method === 'GET' && !url.search;
    return method === 'POST' && !url.search && new RegExp(tenant + '/administrators/' + id + '/(commands|password-recovery)$', 'i').test(url.pathname);
  }
  if (url.pathname === '/v1/platform/pricing') {
    if (method === 'POST') return !url.search;
    return method === 'GET' && [...url.searchParams.keys()].every(key => ['q', 'category', 'status', 'limit', 'cursor'].includes(key));
  }
  const price = '^/v1/platform/pricing/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}';
  if (new RegExp(price + '$', 'i').test(url.pathname)) return ['GET', 'PATCH'].includes(method) && !url.search;
  if (new RegExp(price + '/revisions$', 'i').test(url.pathname)) return method === 'GET' && [...url.searchParams.keys()].every(key => ['limit', 'cursor'].includes(key));
  if (new RegExp(price + '/(delete|restore)$', 'i').test(url.pathname)) return method === 'POST' && !url.search;
  if (url.pathname === '/v1/platform/details') return ['GET', 'PATCH'].includes(method) && !url.search;
  if (url.pathname === '/v1/platform/tenant-options') return method === 'GET' && !url.search;
  if (url.pathname === '/v1/platform/accounts') return method === 'GET' && [...url.searchParams.keys()].every(key => ['q', 'status', 'sort', 'limit', 'cursor'].includes(key));
  if (url.pathname === '/v1/platform/accounts/sync') return method === 'POST' && [...url.searchParams.keys()].every(key => key === 'page');
  if (url.pathname === '/v1/platform/accounts/options') return method === 'GET' && !url.search;
  if (url.pathname === '/v1/platform/accounts/pending-registration') {
    const keys = [...url.searchParams.keys()], email = url.searchParams.get('email') ?? '';
    return method === 'GET' && keys.length === 1 && keys[0] === 'email'
      && email.length >= 3 && email.length <= 320 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  }
  if (url.pathname === '/v1/platform/references/options') return method === 'GET' && !url.search;
  if (url.pathname === '/v1/platform/references/timezones') {
    const params = url.searchParams, keys = [...params.keys()];
    return method === 'GET' && path.split('?').length <= 2 && new Set(keys).size === keys.length
      && keys.every(key => ['q', 'status', 'sort', 'limit', 'cursor'].includes(key))
      && (!params.has('q') || params.get('q')!.trim().length >= 2 && params.get('q')!.length <= 100)
      && (!params.has('status') || ['active', 'archived'].includes(params.get('status')!))
      && (!params.has('sort') || ['name', '-name', 'code', '-code'].includes(params.get('sort')!))
      && (!params.has('limit') || /^\d+$/.test(params.get('limit')!) && Number(params.get('limit')) >= 1 && Number(params.get('limit')) <= 200)
      && (!params.has('cursor') || params.get('cursor')!.length > 0 && params.get('cursor')!.length <= 3000);
  }
  const reference = '^/v1/platform/references/(countries|states|languages|currencies)';
  if (new RegExp(reference + '$').test(url.pathname)) {
    if (method === 'POST') return !url.search;
    return method === 'GET' && [...url.searchParams.keys()].every(key => ['q', 'status', 'country_code', 'sort', 'limit', 'cursor'].includes(key));
  }
  if (new RegExp(reference + '/[A-Za-z0-9-]{2,6}$').test(url.pathname)) return ['GET', 'PATCH'].includes(method) && !url.search;
  if (new RegExp(reference + '/[A-Za-z0-9-]{2,6}/(archive|restore)$').test(url.pathname)) return method === 'POST' && !url.search;
  if (url.pathname === '/v1/platform/tenants') {
    if (method === 'POST') return !url.search;
    return method === 'GET' && [...url.searchParams.keys()].every(key => ['q', 'status', 'sort', 'limit', 'cursor'].includes(key));
  }
  if (url.pathname === '/v1/platform/tenant-administrators/available') {
    const keys = [...url.searchParams.keys()], email = url.searchParams.get('email') ?? '';
    return method === 'GET' && keys.length === 1 && keys[0] === 'email'
      && email.length >= 3 && email.length <= 320 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  }
  if (url.search) return false;
  const id = '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}';
  if (new RegExp('^/v1/platform/accounts/' + id + '$', 'i').test(url.pathname)) return method === 'GET';
  if (new RegExp('^/v1/platform/accounts/' + id + '/(review|reconcile)$', 'i').test(url.pathname)) return method === 'POST';
  if (new RegExp('^/v1/platform/tenants/' + id + '$', 'i').test(url.pathname)) return ['GET', 'PATCH'].includes(method);
  if (new RegExp('^/v1/platform/tenants/' + id + '/lifecycle$', 'i').test(url.pathname)) return method === 'POST';
  return method === 'GET' && new RegExp('^/v1/platform/tenants/' + id + '/administrator-invitation$', 'i').test(url.pathname);
}
