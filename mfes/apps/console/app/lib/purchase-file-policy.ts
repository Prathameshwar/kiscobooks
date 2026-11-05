/** The larger byte envelope serves these exact Purchase file routes only. */
export function allowedPurchaseFileRequest(service: string, method: string, path: string): boolean {
  if (service !== 'vouchers' || /[\\#\x00-\x1f\x7f]/.test(path) || /%2f|%5c|%2e|\.\./i.test(path.split('?')[0]!)) return false;
  const uuid = '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}';
  const root = new RegExp('^/v1/companies/' + uuid + '/vouchers/' + uuid + '/supporting-files$', 'i');
  let url: URL; try { url = new URL(path, 'https://files.invalid'); } catch { return false; }
  if (url.origin !== 'https://files.invalid' || !path.startsWith('/v1/') || /%/.test(url.pathname) || [...url.searchParams.keys()].some(key => url.searchParams.getAll(key).length !== 1)) return false;
  if (root.test(url.pathname)) return method === 'POST' ? !url.search : method === 'GET' && [...url.searchParams].every(([key, value]) => key === 'revision_id' && new RegExp('^' + uuid + '$', 'i').test(value));
  return method === 'GET' && new RegExp('^/v1/companies/' + uuid + '/vouchers/' + uuid + '/supporting-files/' + uuid + '/download$', 'i').test(url.pathname)
    && !!url.searchParams.get('token') && [...url.searchParams].every(([key, value]) => key === 'revision_id' ? new RegExp('^' + uuid + '$', 'i').test(value) : key === 'token' && value.length <= 2000 && /^[a-zA-Z0-9_.=-]+$/.test(value));
}
