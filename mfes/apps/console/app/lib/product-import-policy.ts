const uuid = '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}';
const identifier = new RegExp('^' + uuid + '$', 'i');
/** Only the existing Catalog master import API; native scope and operation grants still apply. */
export function allowedMasterImportRequest(
  service: string,
  method: string,
  path: string,
  owner: 'catalog' | 'accounting',
  resources: readonly string[],
  actions: readonly string[],
): boolean {
  if (
    service !== owner ||
    !path.startsWith('/v1/') ||
    /[\\#\x00-\x1f\x7f]/.test(path) ||
    /%2f|%5c|%2e|\.\./i.test(path.split('?')[0]!)
  )
    return false;
  let url: URL;
  try {
    url = new URL(path, 'https://imports.invalid');
  } catch {
    return false;
  }
  if (url.origin !== 'https://imports.invalid' || /%/.test(url.pathname))
    return false;
  const parts = url.pathname.split('/').filter(Boolean),
    query = url.searchParams;
  if (
    parts[0] !== 'v1' ||
    parts[1] !== 'companies' ||
    !identifier.test(parts[2] ?? '') ||
    [...query.keys()].some((key) => query.getAll(key).length !== 1)
  )
    return false;
  const paging = () =>
    [...query].every(([key, value]) =>
      key === 'limit'
        ? /^\d+$/.test(value) && +value >= 1 && +value <= 200
        : key === 'cursor' &&
          value.length > 0 &&
          value.length <= 3000 &&
          !/[\x00-\x1f\x7f]/.test(value),
    );
  if (parts[3] === 'import-definitions')
    return parts.length === 4 && method === 'GET' && !url.search;
  if (parts[3] === 'import-templates') {
    if (parts.length === 4) return method === 'POST' && !url.search;
    return (
      parts.length === 5 &&
      identifier.test(parts[4]!) &&
      method === 'GET' &&
      [...query].every(([key, value]) =>
        key === 'format'
          ? ['JSON', 'CSV', 'TSV', 'XLSX'].includes(value)
          : key === 'resource'
            ? resources.includes(value)
            : key === 'action' && actions.includes(value),
      )
    );
  }
  if (parts[3] === 'simple-product-imports')
    return (
      owner === 'catalog' &&
      parts.length === 6 &&
      identifier.test(parts[4] ?? '') &&
      (parts[5] === 'rows'
        ? method === 'GET' && paging()
        : parts[5] === 'progress'
          ? method === 'GET' && !url.search
          : parts[5] === 'advance' && method === 'POST' && !url.search)
    );
  if (parts[3] !== 'import-jobs') return false;
  if (parts.length === 4)
    return method === 'GET' ? paging() : method === 'POST' && !url.search;
  if (!identifier.test(parts[4] ?? '')) return false;
  if (parts.length === 5) return method === 'GET' && !url.search;
  if (
    parts.length === 6 &&
    [
      'validate',
      'commit',
      'retry',
      'revisions',
      'cancel',
      'download-ticket',
      'download',
    ].includes(parts[5]!)
  )
    return method === 'POST' && !url.search;
  if (parts.length === 6 && parts[5] === 'records')
    return method === 'GET' && paging();
  if (
    parts.length === 7 &&
    parts[5] === 'history' &&
    ['attempts', 'revisions', 'artifacts'].includes(parts[6]!)
  )
    return method === 'GET' && paging();
  return (
    parts.length === 8 &&
    parts[5] === 'attempts' &&
    identifier.test(parts[6]!) &&
    parts[7] === 'issues' &&
    method === 'GET' &&
    paging()
  );
}

export function allowedProductImportRequest(
  service: string,
  method: string,
  path: string,
): boolean {
  return allowedMasterImportRequest(
    service,
    method,
    path,
    'catalog',
    ['product_family', 'item', 'simple_product', 'simple_product_create'],
    ['CREATE', 'UPDATE', 'ACTIVATE', 'DISCONTINUE'],
  );
}
