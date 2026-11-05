const uuid = '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}';
const prefix = '/v1/companies/' + uuid;

/** Undefined delegates unrelated product routes; false closes this entire master namespace. */
export function allowedCatalogMasterRequest(method: string, path: string): boolean | undefined {
  const [route = '', query = ''] = path.split('?');
  if (!/\/\b(?:units|manufacturers|item-groups|warehouses)(?:\/|$)|\/entities\/catalog\.(?:unit_of_measure|manufacturer|warehouse|item_group(?:_parent)?)\/field-set$/.test(route)) return undefined;
  if (!path.startsWith('/') || path.startsWith('//') || path.split('?').length > 2 || /[%\\#]/.test(route)) return false;
  const params = new URLSearchParams(query), keys = [...params.keys()];
  if (new Set(keys).size !== keys.length) return false;
  const metadata = new RegExp('^' + prefix + '/entities/catalog[.](?:unit_of_measure|manufacturer|warehouse|item_group|item_group_parent)/field-set$', 'i').test(route);
  if (metadata) return method === 'GET' && keys.every(key => key === 'operation') && (!params.has('operation') || ['create', 'update'].includes(params.get('operation')!));
  const match = new RegExp('^' + prefix + '/(units|manufacturers|item-groups|warehouses)(?:/(' + uuid + ')(?:/(activate|deactivate|reparent|parents))?)?$', 'i').exec(route);
  if (!match) return false;
  const [, resource, object, action] = match;
  if (action) {
    if (['reparent', 'parents'].includes(action) && resource !== 'item-groups') return false;
    if (action !== 'parents') return method === 'POST' && keys.length === 0;
    if (method !== 'GET' || keys.some(key => !['limit', 'cursor', 'sort', 'valid_at'].includes(key))) return false;
    if (params.has('valid_at') && !/^\d{4}-\d\d-\d\d$/.test(params.get('valid_at')!)) return false;
  } else if (object) return ['GET', 'PATCH'].includes(method) && keys.length === 0;
  else {
    if (method === 'POST') return keys.length === 0;
    if (method !== 'GET') return false;
    const filters = ['q', 'cursor', 'limit', 'sort', 'is_active', 'code', ...(resource === 'units' ? ['dimension'] : resource === 'item-groups' ? ['allowed_kind'] : resource === 'warehouses' ? ['kind', 'is_system'] : [])];
    if (keys.some(key => !filters.includes(key))) return false;
    if (params.has('is_active') && !['true', 'false'].includes(params.get('is_active')!)) return false;
    if (params.has('is_system') && !['true', 'false'].includes(params.get('is_system')!)) return false;
    if (params.has('kind') && !['STORE', 'GODOWN', 'INTERNAL_TRANSIT'].includes(params.get('kind')!)) return false;
    if (params.has('dimension') && !['COUNT', 'MASS', 'VOLUME', 'LENGTH', 'AREA', 'TIME', 'JOB'].includes(params.get('dimension')!)) return false;
    if (params.has('allowed_kind') && !['GOODS', 'SERVICE', 'BOTH'].includes(params.get('allowed_kind')!)) return false;
    if (params.has('code') && !(params.get('code')!.length >= 1 && params.get('code')!.length <= 30)) return false;
    if (params.has('q') && !(params.get('q')!.trim().length >= 2 && params.get('q')!.length <= 200)) return false;
  }
  if (params.has('limit') && (!/^\d+$/.test(params.get('limit')!) || Number(params.get('limit')) < 1 || Number(params.get('limit')) > 200)) return false;
  return !params.has('cursor') || (params.get('cursor')!.length > 0 && params.get('cursor')!.length <= 4096);
}
