const uuid = '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',
  prefix = '^/v1/companies/' + uuid;
const resources =
  '(?:unit-conversions|pack-types|identifier-types|identifier-namespaces|identifier-profiles)';
/** Close all selected namespaces before the older generic product route rules. */
export function allowedUnitsIdentifiersRequest(
  method: string,
  path: string,
): boolean | undefined {
  const [route = '', query = ''] = path.split('?');
  if (
    !new RegExp(
      '/' +
        resources +
        '(?:/|$)|/units/convert$|/entities/catalog[.](?:unit_conversion|pack_type|identifier_type|identifier_namespace|identifier_profile(?:_requirement)?)/field-set$',
    ).test(route)
  )
    return undefined;
  if (
    path.split('?').length > 2 ||
    /[%\\#]/.test(route) ||
    !path.startsWith('/') ||
    path.startsWith('//')
  )
    return false;
  const params = new URLSearchParams(query),
    keys = [...params.keys()];
  if (new Set(keys).size !== keys.length) return false;
  if (new RegExp(prefix + '/units/convert$', 'i').test(route))
    return method === 'POST' && !keys.length;
  if (
    new RegExp(
      prefix +
        '/entities/catalog[.](?:unit_conversion|pack_type|identifier_type|identifier_namespace|identifier_profile(?:_requirement)?)/field-set$',
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
  const match = new RegExp(
    prefix +
      '/(' +
      resources +
      ')(?:/(' +
      uuid +
      ')(?:/(activate|deactivate|requirements))?)?$',
    'i',
  ).exec(route);
  if (!match) return false;
  const [, resource, object, action] = match;
  if (
    (action === 'requirements' && resource !== 'identifier-profiles') ||
    (action && resource === 'unit-conversions')
  )
    return false;
  if (action && action !== 'requirements')
    return method === 'POST' && !keys.length;
  if (object && !action)
    return (
      !keys.length &&
      (method === 'GET' ||
        (method === 'PATCH' && resource !== 'unit-conversions'))
    );
  if (!object && method === 'POST') return !keys.length;
  if (method !== 'GET') return false;
  return keys.every((key) => {
    const value = params.get(key)!;
    if (key === 'limit')
      return /^\d+$/.test(value) && +value >= 1 && +value <= 200;
    if (key === 'cursor') return value.length > 0 && value.length <= 4096;
    if (key === 'sort')
      return (
        action
          ? ['id', '-id', 'identifier_type', '-identifier_type']
          : resource === 'unit-conversions'
            ? ['id', '-id']
            : resource === 'identifier-types' ||
                resource === 'identifier-namespaces'
              ? ['id', '-id', 'code', '-code']
              : ['id', '-id', 'code', '-code', 'name', '-name']
      ).includes(value);
    if (action)
      return (
        (key === 'identifier_type' && ['SERIAL', 'IMEI'].includes(value)) ||
        (key === 'namespace_rule' &&
          ['COMPANY', 'MANUFACTURER_SKU'].includes(value))
      );
    if (resource === 'unit-conversions')
      return (
        ['from_unit_id', 'canonical_unit_id'].includes(key) &&
        new RegExp('^' + uuid + '$', 'i').test(value)
      );
    if (key === 'q') return value.trim().length >= 2 && value.length <= 200;
    if (key === 'code')
      return (
        value.length >= 1 &&
        value.length <= (resource === 'identifier-namespaces' ? 40 : 30)
      );
    if (key === 'is_active') return ['true', 'false'].includes(value);
    return (
      resource === 'identifier-types' &&
      key === 'is_barcode' &&
      ['true', 'false'].includes(value)
    );
  });
}
