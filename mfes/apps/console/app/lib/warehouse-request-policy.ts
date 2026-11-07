const uuid = '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}';
export function allowedWarehouseIdentityLookup(method: string, path: string): boolean {
  const [route = '', query = ''] = path.split('?'), params = new URLSearchParams(query), keys = [...params.keys()];
  const match = new RegExp('^/v1/companies/' + uuid + '/(departments|tax-registrations)$', 'i').exec(route);
  if (!match || method !== 'GET' || path.split('?').length > 2 || /[%\\#]/.test(route) || new Set(keys).size !== keys.length || keys.some(key => !['q', 'id', 'limit', 'cursor'].includes(key))) return false;
  return (!params.has('q') || params.get('q')!.trim().length >= 2 && params.get('q')!.length <= (match[1] === 'departments' ? 20 : 100))
    && (!params.has('id') || new RegExp('^' + uuid + '$', 'i').test(params.get('id')!))
    && (!params.has('limit') || /^\d+$/.test(params.get('limit')!) && Number(params.get('limit')) >= 1 && Number(params.get('limit')) <= 200)
    && (!params.has('cursor') || params.get('cursor')!.length > 0 && params.get('cursor')!.length <= 3000);
}
export function allowedWarehouseAction(method: string, path: string): boolean | undefined {
  const route = path.split('?')[0] ?? '';
  const rootPattern = '^/v1/companies/' + uuid;
  if (/\/policy-releases|\/warehouse-policy|\/replenishment-policy|\/entities\/catalog[.](catalog_policy_release|item_warehouse_policy|item_warehouse_permission|item_replenishment_policy)\/field-set/i.test(route)) {
    if (new RegExp(rootPattern + '/entities/catalog[.](catalog_policy_release|item_warehouse_policy|item_warehouse_permission|item_replenishment_policy)/field-set$', 'i').test(route)) {
      const params = new URLSearchParams(path.split('?')[1] ?? '');
      return method === 'GET' && path.split('?').length <= 2 && !/[%\\#]/.test(route) && [...params.keys()].length <= 1 && [...params.keys()].every(key => key === 'operation') && (!params.has('operation') || ['update', 'publish'].includes(params.get('operation')!));
    }
    if (path.includes('?') || /[%\\#]/.test(path)) return false;
    if (new RegExp(rootPattern + '/policy-releases$', 'i').test(route)) return ['GET', 'POST'].includes(method);
    if (new RegExp(rootPattern + '/policy-releases/' + uuid + '$', 'i').test(route)) return method === 'GET';
    return new RegExp(rootPattern + '/items/' + uuid + '/(warehouse-policy|replenishment-policy)$', 'i').test(route) && ['GET', 'PUT'].includes(method);
  }
  if (!route.includes('/warehouse-configuration') && !route.includes('/operation-policy') && !/\/entities\/catalog\.(company_warehouse_configuration|warehouse_operation_policy_revision)\/field-set$/.test(route)) return undefined;
  if (new RegExp('^/v1/companies/' + uuid + '/entities/catalog[.](company_warehouse_configuration|warehouse_operation_policy_revision)/field-set$', 'i').test(route)) {
    const params = new URLSearchParams(path.split('?')[1] ?? '');
    return method === 'GET' && path.split('?').length <= 2 && !/[%\\#]/.test(route) && [...params.keys()].length <= 1 && [...params.keys()].every(key => key === 'operation') && (!params.has('operation') || ['create', 'update'].includes(params.get('operation')!));
  }
  if (path.includes('?') || /[%\\#]/.test(path)) return false;
  const root = '^/v1/companies/' + uuid;
  if (new RegExp(root + '/warehouse-configuration$', 'i').test(route)) return method === 'GET';
  if (new RegExp(root + '/warehouse-configuration/(bootstrap|defaults)$', 'i').test(route)) return method === 'POST';
  if (new RegExp(root + '/warehouses/' + uuid + '/operation-policy$', 'i').test(route)) return method === 'GET';
  return new RegExp(root + '/warehouses/' + uuid + '/operation-policy/(preview|publish)$', 'i').test(route) && method === 'POST';
}
