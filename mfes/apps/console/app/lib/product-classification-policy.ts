import {
  classificationResources,
  classificationDefinitions,
  type ClassificationResource,
} from './product-classification-resources';
const uuid = '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',
  prefix = '^/v1/companies/' + uuid;
export function allowedClassificationRequest(
  method: string,
  path: string,
): boolean | undefined {
  const [route = '', query = ''] = path.split('?');
  // Configuration owns its reference lookup, even when the source is "items".
  if (route.includes('/configuration-adoption') || /\/product-configuration\/options\//.test(route)) return undefined;
  const entities = [
    ...classificationResources.map((resource) =>
      classificationDefinitions[resource].entity.slice(8),
    ),
    'product_type_revision',
    'family_category',
    'family_group_assignment',
    'family_manufacturer',
    'item_unit_binding',
    'item_unit_revision',
    'item_barcode',
  ];
  const metadata = new RegExp(
    prefix + '/entities/catalog[.](' + entities.join('|') + ')/field-set$',
    'i',
  ).exec(route);
  const match = new RegExp(
    prefix +
      '/(' +
      classificationResources.join('|') +
      ')(?:/(' +
      uuid +
      ')(?:/([a-z-]+)(?:/(' +
      uuid +
      ')(?:/(publish))?)?)?)?$',
    'i',
  ).exec(route);
  if (
    !metadata &&
    !new RegExp(
      '/(' + classificationResources.join('|') + ')(?:/|$)',
      'i',
    ).test(route)
  )
    return undefined;
  if (path.split('?').length > 2 || /[%\\#\x00-\x1f\x7f]/.test(route))
    return false;
  const params = new URLSearchParams(query),
    keys = [...params.keys()];
  if (
    keys.length !== new Set(keys).size ||
    [...params.values()].some((value) => /[\x00-\x1f\x7f]/.test(value))
  )
    return false;
  if (metadata)
    return (
      method === 'GET' &&
      keys.every((key) =>
        key === 'operation'
          ? [
              'create',
              'update',
              ...(metadata[1] === 'product_type_revision' ? ['publish'] : []),
            ].includes(params.get(key)!)
          : key === 'object_id' &&
            ['item', 'product_family'].includes(metadata[1]!) &&
            params.get('operation') === 'update' &&
            new RegExp('^' + uuid + '$', 'i').test(params.get(key)!),
      )
    );
  if (!match) return false;
  const [, resource, object, action, child, command] = match;
  if (
    resource !== resource?.toLowerCase() ||
    action !== action?.toLowerCase() ||
    command !== command?.toLowerCase()
  )
    return false;
  if (
    action === 'attributes' ||
    action === 'attribute-form' ||
    action === 'variants' ||
    action?.startsWith('configuration-adoption')
  )
    return undefined;
  if (command)
    return (
      resource === 'product-types' &&
      action === 'revisions' &&
      method === 'POST' &&
      !keys.length
    );
  const products = resource === 'items' || resource === 'product-families';
  const nested =
    (resource === 'product-types' && action === 'revisions') ||
    (resource === 'product-families' &&
      ['groups', 'categories', 'manufacturers'].includes(action ?? '')) ||
    (resource === 'items' &&
      ['unit-bindings', 'barcodes'].includes(action ?? ''));
  if (child)
    return (
      nested &&
      ['GET', ...(resource === 'product-types' ? ['PATCH'] : [])].includes(
        method,
      ) &&
      !keys.length
    );
  if (action && !nested) {
    const actions =
      resource === 'items'
        ? ['activation-preview', 'activate']
        : resource === 'product-families'
          ? ['category-preview']
          : resource === 'category-schemes'
            ? ['transition-preview', 'transition', 'activate', 'deactivate']
            : [
                'activate',
                'deactivate',
                ...(['brands', 'item-categories'].includes(resource!)
                  ? ['reparent']
                  : []),
              ];
    if (
      resource === 'items' &&
      ['requirements', 'configuration'].includes(action)
    )
      return (
        method === 'GET' &&
        keys.every(
          (key) =>
            key === 'as_of' && /^\d{4}-\d\d-\d\d$/.test(params.get(key)!),
        )
      );
    return actions.includes(action) && method === 'POST' && !keys.length;
  }
  if (object && !action)
    return ['GET', 'PATCH'].includes(method) && !keys.length;
  if (method !== 'GET')
    return (
      !keys.length &&
      (nested && action === 'categories'
        ? method === 'PUT'
        : method === 'POST' &&
          (!products || resource === 'product-families' || !!action))
    );
  const filters: readonly string[] = nested
    ? resource === 'product-types'
      ? ['published']
      : ['as_of']
    : classificationDefinitions[resource as ClassificationResource].filters;
  return keys.every((key) => {
    const value = params.get(key)!;
    if (key === 'limit')
      return /^\d+$/.test(value) && +value >= 1 && +value <= 200;
    if (key === 'cursor') return value.length > 0 && value.length <= 4096;
    if (key === 'q')
      return !nested && value.trim().length >= 2 && value.length <= 200;
    if (key === 'sort')
      return (
        nested
          ? resource === 'product-types'
            ? ['id', '-id', 'revision', '-revision']
            : ['id', '-id']
          : [
              'id',
              '-id',
              'name',
              '-name',
              resource === 'items' ? 'sku' : 'code',
              resource === 'items' ? '-sku' : '-code',
            ]
      ).includes(value);
    if (!filters.includes(key)) return false;
    if (key.endsWith('_id'))
      return new RegExp('^' + uuid + '$', 'i').test(value);
    if (['is_active', 'sellable', 'purchasable', 'published'].includes(key))
      return ['true', 'false'].includes(value);
    if (key === 'kind')
      return [
        'GOODS',
        'SERVICE',
        ...(resource === 'product-types' ? ['BOTH'] : []),
      ].includes(value);
    if (key === 'membership_mode')
      return ['SINGLE', 'MULTIPLE'].includes(value);
    if (key === 'status')
      return ['DRAFT', 'ACTIVE', 'DISCONTINUED'].includes(value);
    if (key === 'as_of') return /^\d{4}-\d\d-\d\d$/.test(value);
    if (key === 'country_code') return /^[A-Z]{2}$/.test(value);
    if (key === 'state_code') return /^[A-Z0-9-]{1,6}$/.test(value);
    return /^[A-Z0-9][A-Z0-9_.-]{0,29}$/.test(value);
  });
}
