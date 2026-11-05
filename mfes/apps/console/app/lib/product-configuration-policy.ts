const uuid = '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}';
const sources = '(?:items|product-type-revisions|attribute-set-revisions|inventory-template-revisions|warranty-revisions|return-policy-revisions|handling-revisions|identifier-profiles|currencies)';
/** Closed routes for native configuration, with no writable publication/history endpoint. */
export function allowedConfigurationRequest(method: string, path: string): boolean | undefined {
  const rawRoute = path.split('?')[0]!;
  // Product authoring is validated by the dedicated simple-product policy.
  // Inspect only the route so search text cannot change namespace ownership.
  if (/\/product-configuration\/authoring(?:\/|$)/.test(rawRoute)) return undefined;
  if (!rawRoute.includes('/product-configur') && !rawRoute.includes('/configuration-adoption') && !/\/entities\/catalog\.(product_configuration_|product_entry_option_policy|product_numeric_default|catalog_default_profile|product_pricing_policy)/.test(rawRoute)) return undefined;
  if (/[\\#\x00-\x1f\x7f]/.test(path) || /%2f|%5c|%2e|\.\./i.test(rawRoute)) return false;
  const url = new URL(path, 'https://console.invalid'); if (url.origin !== 'https://console.invalid') return false;
  const prefix = '^/v1/companies/' + uuid, route = url.pathname;
  let allowed: string[] = [];
  if (new RegExp(prefix + '/entities/catalog[.](?:product_configuration_(?:scope|draft|revision)|product_entry_option_policy|product_numeric_default|catalog_default_profile|product_pricing_policy)/field-set$', 'i').test(route)) { if (method !== 'GET') return false; allowed = ['operation']; }
  else if (new RegExp(prefix + '/product-configuration/options/' + sources + '$', 'i').test(route)) { if (method !== 'GET') return false; allowed = ['q', 'cursor', 'limit', 'sort', 'kind', 'value']; }
  else if (new RegExp(prefix + '/product-configuration-scopes$', 'i').test(route)) { if (!['GET', 'POST'].includes(method)) return false; allowed = method === 'GET' ? ['cursor', 'limit', 'sort', 'scope_kind'] : []; if (url.searchParams.has('scope_kind') && url.searchParams.get('scope_kind') !== 'COMPANY') return false; }
  else if (new RegExp(prefix + '/product-configuration-scopes/' + uuid + '(?:/(drafts|revisions))?$', 'i').test(route)) { if (method !== 'GET') return false; allowed = route.endsWith('/drafts') ? ['cursor', 'limit', 'sort', 'status'] : route.endsWith('/revisions') ? ['cursor', 'limit', 'sort', 'effective_on'] : []; }
  else if (new RegExp(prefix + '/product-configurations$', 'i').test(route)) { if (method !== 'POST') return false; }
  else if (new RegExp(prefix + '/product-configurations/company$', 'i').test(route)) { if (method !== 'POST') return false; }
  else if (new RegExp(prefix + '/product-configurations/' + uuid + '$', 'i').test(route)) { if (!['GET', 'PATCH'].includes(method)) return false; }
  else if (new RegExp(prefix + '/product-configurations/' + uuid + '/(preview|publish)$', 'i').test(route)) { if (method !== (route.endsWith('/preview') ? 'GET' : 'POST')) return false; }
  else if (new RegExp(prefix + '/product-configuration-revisions/' + uuid + '$', 'i').test(route)) { if (method !== 'GET') return false; }
  else if (new RegExp(prefix + '/product-configuration/(?:effective|authoring-defaults)$', 'i').test(route)) { if (method !== 'GET') return false; allowed = ['as_of', 'kind', 'product_type_revision_id', 'product_type_id', 'group_id', 'family_id', 'item_id', ...(route.endsWith('authoring-defaults') ? ['include_price', 'unit_id', 'unit_revision_id', 'currency'] : [])]; }
  else if (new RegExp(prefix + '/items/' + uuid + '/configuration-adoption(?:/preview)?$', 'i').test(route)) { if (method !== (route.endsWith('/preview') ? 'GET' : 'POST')) return false; allowed = route.endsWith('/preview') ? ['as_of'] : []; }
  else return false;
  for (const [key, value] of url.searchParams) if (!allowed.includes(key) || url.searchParams.getAll(key).length !== 1 || /[\x00-\x1f\x7f]/.test(value)) return false;
  return true;
}
