/** The larger byte envelope serves one route only: uploading a brand asset's bytes. */
export function allowedDesignAssetUpload(service: string, method: string, path: string): boolean {
  if (service !== 'design' || /[\\#\x00-\x1f\x7f]/.test(path) || /%2f|%5c|%2e|\.\./i.test(path.split('?')[0]!)) return false;
  const uuid = '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}';
  let url: URL;
  try {
    url = new URL(path, 'https://assets.invalid');
  } catch {
    return false;
  }
  if (url.origin !== 'https://assets.invalid' || !path.startsWith('/v1/') || /%/.test(url.pathname) || url.search) {
    return false;
  }
  return method === 'POST' && new RegExp('^/v1/companies/' + uuid + '/assets$', 'i').test(url.pathname);
}
