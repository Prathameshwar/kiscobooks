/** Closed transport paths for the single-product facade and live company control. */
export function allowedSimpleProductRequest(
  method: string,
  path: string,
): boolean | undefined {
  const rawRoute = path.split('?')[0]!;
  if (
    !/\/simple-product-creations(?:\/|\?|$)|\/products(?:\/|\?|$)|\/product-configuration\/authoring(?:\/|\?|$)|\/entities\/catalog\.company_product_authoring_configuration\/field-set/.test(
      rawRoute,
    )
  )
    return undefined;
  if (
    /[\\#\x00-\x1f\x7f]/.test(path) ||
    /%2f|%5c|\.\./i.test(rawRoute) ||
    /%2e/i.test(rawRoute)
  )
    return false;
  let url: URL;
  try {
    url = new URL(path, 'https://console.invalid');
  } catch {
    return false;
  }
  if (url.origin !== 'https://console.invalid') return false;
  const uuid = '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}';
  const base = '^/v1/companies/' + uuid;
  let queries: string[] = [];
  const route = url.pathname;
  if (new RegExp(base + '/simple-product-creations/options$', 'i').test(route)) {
    if (method !== 'GET') return false;
    queries = ['kind', 'group_id'];
    if (url.searchParams.has('kind') && !['GOODS', 'SERVICE'].includes(url.searchParams.get('kind')!)) return false;
    if (url.searchParams.has('group_id') && !new RegExp('^' + uuid + '$', 'i').test(url.searchParams.get('group_id')!)) return false;
  } else if (new RegExp(base + '/simple-product-creations$', 'i').test(route)) {
    if (method !== 'POST') return false;
  } else if (new RegExp(base + '/simple-product-creations/' + uuid + '$', 'i').test(route)) {
    if (!['GET', 'PATCH'].includes(method)) return false;
  } else if (new RegExp(base + '/simple-product-creations/by-key/' + uuid + '$', 'i').test(route)) {
    if (method !== 'GET') return false;
  } else if (new RegExp(base + '/simple-product-creations/' + uuid + '/advance$', 'i').test(route)) {
    if (method !== 'POST') return false;
  } else if (new RegExp(base + '/product-configuration/authoring$', 'i').test(route)) {
    if (!['GET', 'PATCH'].includes(method)) return false;
  } else if (
    new RegExp(base + '/product-configuration/authoring/preview$', 'i').test(
      route,
    )
  ) {
    if (method !== 'POST') return false;
  } else if (
    new RegExp(
      base +
        '/entities/catalog[.]company_product_authoring_configuration/field-set$',
      'i',
    ).test(route)
  ) {
    if (method !== 'GET') return false;
    queries = ['operation'];
  } else if (new RegExp(base + '/products/field-set$', 'i').test(route)) {
    if (method !== 'GET') return false;
    queries = ['operation', 'object_id'];
  } else if (new RegExp(base + '/products$', 'i').test(route)) {
    if (!['GET', 'POST'].includes(method)) return false;
    if (method === 'GET')
      queries = [
        'q',
        'cursor',
        'limit',
        'sort',
        'code',
        'status',
        'base_unit_id',
        'sellable',
        'purchasable',
        'custom_filters',
      ];
  } else if (new RegExp(base + '/products/' + uuid + '$', 'i').test(route)) {
    if (!['GET', 'PATCH'].includes(method)) return false;
  } else if (
    new RegExp(base + '/products/' + uuid + '/attribute-form$', 'i').test(route)
  ) {
    if (method !== 'GET') return false;
  } else if (
    new RegExp(
      base + '/products/' + uuid + '/(?:attributes|categories)$',
      'i',
    ).test(route)
  ) {
    if (method !== 'PUT') return false;
  } else if (
    new RegExp(
      base +
        '/products/' +
        uuid +
        '/(?:groups|manufacturers|category-preview)$',
      'i',
    ).test(route)
  ) {
    if (method !== 'POST') return false;
  } else return false;
  for (const [key, value] of url.searchParams)
    if (
      !queries.includes(key) ||
      url.searchParams.getAll(key).length !== 1 ||
      /[\x00-\x1f\x7f]/.test(value)
    )
      return false;
  if (
    url.searchParams.has('operation') &&
    !['create', 'update'].includes(url.searchParams.get('operation')!)
  )
    return false;
  if (
    url.searchParams.has('object_id') &&
    !new RegExp('^' + uuid + '$', 'i').test(url.searchParams.get('object_id')!)
  )
    return false;
  if (
    url.searchParams.has('object_id') &&
    url.searchParams.get('operation') !== 'update'
  )
    return false;
  if (
    url.searchParams.has('base_unit_id') &&
    !new RegExp('^' + uuid + '$', 'i').test(
      url.searchParams.get('base_unit_id')!,
    )
  )
    return false;
  if (
    url.searchParams.has('limit') &&
    (!/^[1-9][0-9]{0,2}$/.test(url.searchParams.get('limit')!) ||
      Number(url.searchParams.get('limit')) > 200)
  )
    return false;
  if (
    url.searchParams.has('sort') &&
    !/^-?(?:id|code|name)$/.test(url.searchParams.get('sort')!)
  )
    return false;
  if (
    url.searchParams.has('status') &&
    !['DRAFT', 'ACTIVE', 'DISCONTINUED'].includes(
      url.searchParams.get('status')!,
    )
  )
    return false;
  for (const key of ['sellable', 'purchasable'])
    if (
      url.searchParams.has(key) &&
      !['true', 'false'].includes(url.searchParams.get(key)!)
    )
      return false;
  return true;
}
