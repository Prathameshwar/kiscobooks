const uuid = '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}';
const prefix = '/v1/companies/' + uuid;
/** Tax administration has a closed namespace; publication stays behind the shared proxy. */
export function allowedTaxRequest(
  method: string,
  path: string,
): boolean | undefined {
  const [route = '', query = ''] = path.split('?');
  if (!/\/(?:tax-[a-z-]+|entities\/catalog\.tax_[a-z_]+)(?:\/|$)/.test(route))
    return undefined;
  if (
    !path.startsWith('/') ||
    path.startsWith('//') ||
    path.split('?').length > 2 ||
    /[%\\#]/.test(route)
  )
    return false;
  const params = new URLSearchParams(query),
    keys = [...params.keys()];
  if (new Set(keys).size !== keys.length) return false;
  if (
    new RegExp(
      '^' +
        prefix +
        '/entities/catalog[.]tax_(?:category|classification|rule|rate|rate_series|rate_component|rule_applicability)/field-set$',
      'i',
    ).test(route)
  )
    return (
      method === 'GET' &&
      keys.every((key) => key === 'operation') &&
      (!params.has('operation') ||
        ['create', 'update'].includes(params.get('operation')!))
    );
  if (new RegExp('^' + prefix + '/tax-administration$', 'i').test(route))
    return method === 'GET' && keys.length === 0;
  if (new RegExp('^' + prefix + '/tax-defaults/bootstrap$', 'i').test(route))
    return method === 'POST' && keys.length === 0;
  if (
    new RegExp(
      '^' +
        prefix +
        '/(?:tax-rate-previews|tax-withdrawals|tax-release-previews|tax-releases|tax-impact-reviews)$',
      'i',
    ).test(route)
  )
    return method === 'POST' && keys.length === 0;
  if (
    new RegExp('^' + prefix + '/tax-impact-reviews/' + uuid + '$', 'i').test(
      route,
    )
  )
    return method === 'GET' && keys.length === 0;
  if (
    new RegExp(
      '^' + prefix + '/tax-impact-reviews/' + uuid + '/findings$',
      'i',
    ).test(route)
  )
    return (
      method === 'GET' &&
      keys.every((key) =>
        key === 'limit'
          ? /^\d+$/.test(params.get(key)!) &&
            +params.get(key)! >= 1 &&
            +params.get(key)! <= 200
          : key === 'cursor'
            ? params.get(key)!.length > 0 && params.get(key)!.length <= 4096
            : key === 'sort'
              ? ['id', '-id'].includes(params.get(key)!)
              : key === 'blocking' &&
                ['true', 'false'].includes(params.get(key)!),
      )
    );
  const match = new RegExp(
    '^' +
      prefix +
      '/(tax-categories|tax-classifications|tax-rules|tax-rates|tax-rate-series|tax-rate-components|tax-rule-applicabilities|tax-history-actions)(?:/(' +
      uuid +
      '))?$',
    'i',
  ).exec(route);
  if (!match) return false;
  const resource = match[1]!,
    object = match[2];
  if (object)
    return (
      keys.length === 0 &&
      (method === 'GET' ||
        (method === 'PATCH' &&
          ['tax-categories', 'tax-rules'].includes(resource)))
    );
  if (method === 'POST')
    return (
      keys.length === 0 &&
      !['tax-rate-components', 'tax-history-actions'].includes(resource)
    );
  if (method !== 'GET') return false;
  const filters = [
    'limit',
    'cursor',
    'sort',
    ...(['tax-categories', 'tax-rules', 'tax-classifications'].includes(
      resource,
    )
      ? ['q']
      : []),
    ...(['tax-categories', 'tax-rules'].includes(resource)
      ? ['is_active']
      : []),
    ...(resource === 'tax-classifications' ? ['code_system', 'as_of'] : []),
    ...(resource === 'tax-rates' ? ['series_id', 'as_of'] : []),
    ...(['tax-rate-series', 'tax-rule-applicabilities'].includes(resource)
      ? ['rule_id']
      : []),
    ...(resource === 'tax-rate-components' ? ['rate_id'] : []),
    ...(resource === 'tax-history-actions' ? ['target_id'] : []),
  ];
  if (keys.some((key) => !filters.includes(key))) return false;
  return keys.every((key) => {
    const value = params.get(key)!;
    if (key.endsWith('_id'))
      return new RegExp('^' + uuid + '$', 'i').test(value);
    if (key === 'limit')
      return /^\d+$/.test(value) && +value >= 1 && +value <= 200;
    if (key === 'cursor') return value.length > 0 && value.length <= 4096;
    if (key === 'q') return value.trim().length >= 2 && value.length <= 200;
    if (key === 'sort')
      return [
        'id',
        '-id',
        ...(['tax-categories', 'tax-rules', 'tax-classifications'].includes(
          resource,
        )
          ? ['code', '-code']
          : []),
      ].includes(value);
    if (key === 'is_active') return ['true', 'false'].includes(value);
    if (key === 'code_system') return ['HSN', 'SAC'].includes(value);
    if (key === 'as_of') return /^\d{4}-\d\d-\d\d$/.test(value);
    return false;
  });
}
