import { validMasterDate } from './catalog-masters';
const uuid = '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', prefix = '^/v1/companies/' + uuid;
export function allowedWarehouseStructureRequest(method: string, path: string): boolean | undefined {
  const [route = '', query = ''] = path.split('?');
  if (!/\/(?:warehouse-(?:groups|bins|structure)|entities\/catalog\.warehouse_(?:group|bin|group_parent|group_assignment)|warehouses\/[^/]+\/(?:primary-group|group-history))(?:\/|$)/.test(route)) return undefined;
  if (path.split('?').length > 2 || /[%\\#]/.test(route) || !path.startsWith('/') || path.startsWith('//')) return false;
  const params = new URLSearchParams(query), keys = [...params.keys()]; if (new Set(keys).size !== keys.length) return false;
  if (new RegExp(prefix + '/warehouse-structure$', 'i').test(route)) return method === 'GET' && keys.length === 1 && ['groups', 'bins'].includes(params.get('resource') ?? '');
  if (new RegExp(prefix + '/entities/catalog[.]warehouse_(?:group|bin|group_parent|group_assignment)/field-set$', 'i').test(route)) return method === 'GET' && keys.every(key => key === 'operation' && ['create', 'update'].includes(params.get(key)!));
  if (new RegExp(prefix + '/warehouses/' + uuid + '/primary-group$', 'i').test(route)) return method === 'PUT' && !keys.length;
  const history = new RegExp(prefix + '/(?:warehouse-groups/' + uuid + '/parents|warehouses/' + uuid + '/group-history)$', 'i').test(route);
  const collection = new RegExp(prefix + '/(warehouse-groups|warehouse-bins)(?:/(' + uuid + ')(?:/(activate|deactivate|reparent|children|members))?)?$', 'i').exec(route);
  if (!history && !collection) return false;
  const object = collection?.[2], action = collection?.[3], resource = collection?.[1];
  if (action && resource === 'warehouse-bins' && !['activate', 'deactivate'].includes(action)) return false;
  if (action && ['activate', 'deactivate', 'reparent'].includes(action)) return method === 'POST' && !keys.length;
  if (object && !action) return !keys.length && ['GET', 'PATCH'].includes(method);
  if (!history && !object && method === 'POST') return !keys.length;
  if (method !== 'GET') return false;
  const dated = history || action === 'children' || action === 'members';
  if ((action === 'children' || action === 'members') && !params.has('valid_at')) return false;
  return keys.every(key => {
    const value = params.get(key)!;
    if (key === 'limit') return /^\d+$/.test(value) && +value >= 1 && +value <= 200;
    if (key === 'cursor') return value.length > 0 && value.length <= 4096;
    if (key === 'sort') return (history ? ['id', '-id', 'valid_from', '-valid_from'] : ['id', '-id', 'code', '-code', 'name', '-name']).includes(value);
    if (key === 'valid_at') return dated && validMasterDate(value);
    if (key === 'q') return !history && value.trim().length >= 2 && value.length <= 200;
    if (key === 'is_active') return !history && ['true', 'false'].includes(value);
    if (key === 'warehouse_id') return resource === 'warehouse-bins' && new RegExp('^' + uuid + '$', 'i').test(value);
    return false;
  });
}
