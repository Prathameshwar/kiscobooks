import { revisionedDefinitionResources } from './product-profile-resources';
const uuid = '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',
  prefix = '^/v1/companies/' + uuid;
export function allowedProductProfileRequest(
  method: string,
  path: string,
): boolean | undefined {
  const [route = '', query = ''] = path.split('?');
  if (
    !/\/(inventory-templates|warranty-policies|return-policies|handling-profiles|manufacturing-operations|manufacturing-routes)(?:\/|$)|\/entities\/catalog[.](inventory_profile_template|warranty_policy|return_policy|handling_profile|manufacturing_operation|manufacturing_route)(?:_revision|_condition|_step)?\/field-set$/i.test(
      route,
    )
  )
    return undefined;
  if (path.split('?').length > 2 || /[%\\#]/.test(route)) return false;
  const params = new URLSearchParams(query),
    keys = [...params.keys()];
  if (keys.length !== new Set(keys).size) return false;
  if (
    new RegExp(prefix + '/manufacturing-operations/service-options$', 'i').test(
      route,
    )
  )
    return (
      method === 'GET' &&
      keys.every((key) =>
        key === 'q'
          ? params.get(key)!.trim().length >= 2 &&
            params.get(key)!.length <= 200
          : key === 'limit'
            ? /^\d+$/.test(params.get(key)!) &&
              +params.get(key)! >= 1 &&
              +params.get(key)! <= 200
            : key === 'cursor'
              ? !!params.get(key) && params.get(key)!.length <= 4096
              : key === 'value'
                ? new RegExp('^' + uuid + '$', 'i').test(params.get(key)!)
                : false,
      )
    );

  if (
    new RegExp(
      prefix + '/manufacturing-routes/operation-references/' + uuid + '$',
      'i',
    ).test(route)
  )
    return method === 'GET' && keys.length === 0;
  if (
    new RegExp(prefix + '/manufacturing-routes/operation-options$', 'i').test(
      route,
    )
  )
    return (
      method === 'GET' &&
      keys.every((key) =>
        key === 'q'
          ? params.get(key)!.trim().length >= 2 &&
            params.get(key)!.length <= 200
          : key === 'limit'
            ? /^\d+$/.test(params.get(key)!) &&
              +params.get(key)! >= 1 &&
              +params.get(key)! <= 200
            : key === 'cursor'
              ? !!params.get(key) && params.get(key)!.length <= 4096
              : key === 'value'
                ? new RegExp('^' + uuid + '$', 'i').test(params.get(key)!)
                : key === 'sort'
                  ? ['id', '-id', 'code', '-code', 'name', '-name'].includes(
                      params.get(key)!,
                    )
                  : false,
      )
    );
  const metadata = new RegExp(
    prefix +
      '/entities/catalog[.](inventory_profile_template|warranty_policy|return_policy|handling_profile|manufacturing_operation|manufacturing_route)(_revision|_step)?/field-set$',
    'i',
  ).exec(route);
  if (
    metadata ||
    new RegExp(
      prefix + '/entities/catalog[.]return_policy_condition/field-set$',
      'i',
    ).test(route)
  )
    return (
      method === 'GET' &&
      keys.every(
        (key) =>
          key === 'operation' &&
          [
            'create',
            'update',
            ...(metadata && !metadata[2] ? [] : ['publish']),
          ].includes(params.get(key)!),
      )
    );
  const match = new RegExp(
    prefix +
      '/(' +
      revisionedDefinitionResources.join('|') +
      ')(?:/(' +
      uuid +
      ')(?:/(activate|deactivate|revisions)(?:/(' +
      uuid +
      ')(?:/(publish|retire|conditions|steps))?)?)?)?$',
    'i',
  ).exec(route);
  if (!match) return false;
  const [, resource, object, action, revision, child] = match;
  if (['activate', 'deactivate'].includes(action ?? ''))
    return method === 'POST' && !keys.length && !revision;
  if (
    child === 'retire' &&
    !['manufacturing-operations', 'manufacturing-routes'].includes(resource!)
  )
    return false;
  if (child === 'publish' || child === 'retire')
    return method === 'POST' && !keys.length;
  if (child === 'conditions' && resource !== 'return-policies') return false;
  if (
    child === 'steps' &&
    (resource !== 'manufacturing-routes' || method !== 'GET')
  )
    return false;
  if ((revision && !child) || (object && !action))
    return ['GET', 'PATCH'].includes(method) && !keys.length;
  if (method === 'POST') return !child && !keys.length;
  if (method !== 'GET') return false;
  return keys.every((key) => {
    const value = params.get(key)!;
    if (key === 'limit')
      return /^\d+$/.test(value) && +value >= 1 && +value <= 200;
    if (key === 'cursor') return value.length > 0 && value.length <= 4096;
    if (key === 'sort')
      return (
        child
          ? child === 'steps'
            ? ['id', '-id', 'sequence', '-sequence']
            : ['id', '-id', 'condition_code', '-condition_code']
          : action
            ? ['revision', '-revision', 'id', '-id']
            : ['code', '-code', 'name', '-name', 'id', '-id']
      ).includes(value);
    if (child)
      return (
        key === 'condition_code' &&
        [
          'ORIGINAL_PACKAGING',
          'PROOF_OF_PURCHASE',
          'COMPLETE_ACCESSORIES',
          'UNUSED',
          'UNDAMAGED',
        ].includes(value)
      );
    if (action)
      return (
        (key === 'published' && ['true', 'false'].includes(value)) ||
        (['manufacturing-operations', 'manufacturing-routes'].includes(
          resource!,
        ) &&
          key === 'status' &&
          ['DRAFT', 'PUBLISHED', 'RETIRED'].includes(value))
      );
    return key === 'q'
      ? value.trim().length >= 2 && value.length <= 200
      : key === 'code'
        ? /^[A-Z0-9][A-Z0-9_.-]{0,29}$/.test(value)
        : key === 'is_active' && ['true', 'false'].includes(value);
  });
}
