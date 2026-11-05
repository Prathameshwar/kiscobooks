const uuid = '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',
  prefix = '^/v1/companies/' + uuid;
export function allowedPricingRequest(
  method: string,
  path: string,
): boolean | undefined {
  const [route = '', query = ''] = path.split('?');
  if (
    !/\/(sales-channels|price-levels|price-plans|pricing\/bootstrap)(?:\/|$)|\/entities\/catalog[.](sales_channel|price_level|price_plan)\/field-set$/i.test(
      route,
    )
  )
    return undefined;
  if (path.split('?').length > 2 || /[%\\#]/.test(route)) return false;
  const params = new URLSearchParams(query),
    keys = [...params.keys()];
  if (new Set(keys).size !== keys.length) return false;
  if (
    new RegExp(
      prefix +
        '/entities/catalog[.](sales_channel|price_level|price_plan)/field-set$',
      'i',
    ).test(route)
  )
    return (
      method === 'GET' &&
      keys.every(
        (key) =>
          key === 'operation' &&
          ['create', 'update'].includes(params.get(key)!),
      )
    );
  if (new RegExp(prefix + '/pricing/bootstrap$', 'i').test(route))
    return method === 'POST' && !keys.length;
  const match = new RegExp(
    prefix +
      '/(sales-channels|price-levels|price-plans)(?:/(' +
      uuid +
      ')(?:/(activate|deactivate))?)?$',
    'i',
  ).exec(route);
  if (!match) return false;
  const [, resource, object, action] = match;
  if (action)
    return resource === 'sales-channels' && method === 'POST' && !keys.length;
  if (object) return ['GET', 'PATCH'].includes(method) && !keys.length;
  if (method === 'POST') return !keys.length;
  if (method !== 'GET') return false;
  return keys.every((key) => {
    const value = params.get(key)!;
    if (key === 'limit')
      return /^\d+$/.test(value) && +value >= 1 && +value <= 200;
    if (key === 'cursor') return value.length > 0 && value.length <= 4096;
    if (key === 'q') return value.trim().length >= 2 && value.length <= 200;
    if (key === 'sort')
      return (
        resource === 'sales-channels'
          ? ['id', '-id', 'code', '-code', 'name', '-name']
          : ['id', '-id', 'code', '-code', 'code,id', '-code,-id']
      ).includes(value);
    if (resource === 'sales-channels')
      return key === 'is_active' && ['true', 'false'].includes(value);
    if (resource !== 'price-plans') return false;
    return key === 'currency'
      ? /^[A-Z]{3}$/.test(value)
      : key === 'purpose'
        ? ['SALE', 'PURCHASE', 'REFERENCE_RETAIL'].includes(value)
        : key === 'price_level_id' &&
          new RegExp('^' + uuid + '$', 'i').test(value);
  });
}
