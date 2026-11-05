/** Closed transport paths for Advanced draft and option reads. */
export function allowedProductCreationRequest(
  method: string,
  path: string,
): boolean | undefined {
  const [route = '', query = ''] = path.split('?');
  if (/\/advanced-product-creations(?:\/|$)/.test(route)) {
    if (path.split('?').length > 2 || /[%\\#\x00-\x1f\x7f]/.test(route) || /\.\./.test(route)) return false;
    const uuid = '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}';
    const base = '^/v1/companies/' + uuid + '/advanced-product-creations';
    if (new RegExp(base + '/options$', 'i').test(route)) {
      if (method !== 'GET') return false;
      const params = new URLSearchParams(query);
      return [...params.keys()].every(key => ['kind', 'group_id', 'product_type_revision_id'].includes(key))
        && [...params.keys()].length === new Set(params.keys()).size
        && (!params.has('kind') || ['GOODS', 'SERVICE'].includes(params.get('kind')!))
        && ['group_id', 'product_type_revision_id'].every(key => !params.has(key) || new RegExp('^' + uuid + '$', 'i').test(params.get(key)!));
    }
    if (new RegExp(base + '/drafts$', 'i').test(route)) return !query && ['GET', 'POST'].includes(method);
    if (new RegExp(base + '/drafts/' + uuid + '$', 'i').test(route)) return !query && ['GET', 'PUT'].includes(method);
    if (new RegExp(base + '/definitions$', 'i').test(route)) return !query && method === 'POST';
    if (new RegExp(base + '/definitions/' + uuid + '$', 'i').test(route)) return !query && method === 'GET';
    if (new RegExp(base + '/definitions/' + uuid + '/skus/' + uuid + '/(setup|publish-prices|readiness|activate|opening-preflight|opening(?:/advance)?)$', 'i').test(route)) return !query && method === 'POST';
    return false;
  }
  if (/\/price-drafts(?:\/|$)/.test(route)) {
    return (
      method === 'GET' &&
      path.split('?').length === 1 &&
      /^\/v1\/companies\/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\/price-drafts\/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(
        route,
      )
    );
  }

  if (
    !/\/entities\/catalog\.(item_price_draft|catalog_tax_binding|item_attribute_value)\/field-set$/.test(
      route,
    )
  )
    return undefined;
  if (path.split('?').length > 2 || /[%\\#]/.test(route)) return false;
  const match =
    /^\/v1\/companies\/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\/entities\/catalog\.(item_price_draft|catalog_tax_binding|item_attribute_value)\/field-set$/.exec(
      route,
    );
  if (!match || method !== 'GET') return false;
  const params = new URLSearchParams(query);
  return (
    [...params.keys()].every((key) => key === 'operation') &&
    params.getAll('operation').length <= 1 &&
    (!params.has('operation') || params.get('operation') === 'create')
  );
}
