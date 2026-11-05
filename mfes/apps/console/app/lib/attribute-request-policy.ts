const uuid = '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',
  prefix = '^/v1/companies/' + uuid;
export function allowedAttributeRequest(
  method: string,
  path: string,
): boolean | undefined {
  const [route = '', query = ''] = path.split('?');
  if (
    !/\/attribute-(?:definitions|options|sets)(?:\/|$)|\/entities\/catalog[.]attribute_(?:definition|option|set(?:_revision|_member)?)\/field-set$/i.test(
      route,
    )
  )
    return undefined;
  if (
    path.split('?').length > 2 ||
    /[%\\#]/.test(route) ||
    path.startsWith('//')
  )
    return false;
  const params = new URLSearchParams(query),
    keys = [...params.keys()];
  if (new Set(keys).size !== keys.length) return false;
  const metadata = new RegExp(
    prefix +
      '/entities/catalog[.](attribute_(?:definition|option|set(?:_revision|_member)?))/field-set$',
    'i',
  ).exec(route);
  if (metadata)
    return (
      method === 'GET' &&
      keys.every(
        (key) =>
          key === 'operation' &&
          (['create', 'update'].includes(params.get(key)!) ||
            (params.get(key) === 'publish' &&
              ['attribute_set_revision', 'attribute_set_member'].includes(
                metadata[1]!,
              ))),
      )
    );
  const match = new RegExp(
    prefix +
      '/attribute-(definitions|options|sets)(?:/(' +
      uuid +
      ')(?:/(activate|deactivate|revisions)(?:/(' +
      uuid +
      ')(?:/(members|publish))?)?)?)?$',
    'i',
  ).exec(route);
  if (!match) return false;
  const [, resource, object, action, revision, child] = match;
  if (
    (revision && action !== 'revisions') ||
    (action === 'revisions' && resource !== 'sets')
  )
    return false;
  if (action === 'activate' || action === 'deactivate' || child === 'publish')
    return method === 'POST' && !keys.length;
  if (child === 'members' && method === 'PUT') return !keys.length;
  if (revision && !child) return method === 'GET' && !keys.length;
  if (object && !action)
    return ['GET', 'PATCH'].includes(method) && !keys.length;
  if (method === 'POST' && !revision) return !keys.length;
  if (method !== 'GET') return false;
  return keys.every((key) => {
    const value = params.get(key)!;
    if (key === 'limit')
      return /^\d+$/.test(value) && +value >= 1 && +value <= 200;
    if (key === 'cursor') return value.length > 0 && value.length <= 4096;
    if (key === 'sort')
      return (
        child
          ? ['id', '-id', 'position', '-position']
          : action
            ? ['id', '-id', 'revision', '-revision']
            : ['id', '-id', 'code', '-code', 'name', '-name']
      ).includes(value);
    if (child)
      return (
        (key === 'definition_id' &&
          new RegExp('^' + uuid + '$', 'i').test(value)) ||
        (['is_required', 'allow_variant_axis'].includes(key) &&
          ['true', 'false'].includes(value))
      );
    if (action) return key === 'published' && ['true', 'false'].includes(value);
    if (key === 'q') return value.trim().length >= 2 && value.length <= 200;
    if (key === 'code') return value.length >= 1 && value.length <= 30;
    if (key === 'is_active') return ['true', 'false'].includes(value);
    if (key === 'value_type')
      return (
        resource !== 'sets' &&
        ['TEXT', 'INTEGER', 'DECIMAL', 'BOOLEAN', 'DATE'].includes(value)
      );
    if (key === 'definition_id')
      return (
        resource === 'options' && new RegExp('^' + uuid + '$', 'i').test(value)
      );
    if (key === 'measurement_dimension')
      return (
        resource === 'definitions' &&
        ['COUNT', 'MASS', 'VOLUME', 'LENGTH', 'AREA', 'TIME', 'JOB'].includes(
          value,
        )
      );
    return (
      resource === 'definitions' &&
      key === 'is_variant_capable' &&
      ['true', 'false'].includes(value)
    );
  });
}
