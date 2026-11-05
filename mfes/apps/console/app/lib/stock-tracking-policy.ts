import { trackingId } from './stock-tracking-resources';

/** One activated SKU profile lookup; no profile writes or arbitrary tax browse. */
export function allowedActivatedStockProfileRead(method: string, path: string): boolean {
  if (method !== 'GET' || !path.startsWith('/') || path.startsWith('//') || path.split('?').length > 2 || /[%\\#]/.test(path.split('?')[0]!)) return false;
  const url = new URL(path, 'https://service.invalid'), id = trackingId.source.slice(1, -1);
  return url.pathname === path.split('?')[0] && new RegExp(`^/v1/companies/${id}/item-inventory-profiles$`, 'i').test(url.pathname)
    && [...url.searchParams].length === 2 && url.searchParams.get('limit') === '2'
    && trackingId.test(url.searchParams.get('item_id') ?? '');
}

/** Explicit stock-registration surface; no arbitrary Accounting or stock-posting route. */
export function allowedStockTrackingRequest(method: string, path: string): boolean | undefined {
  if (!path.includes('/stock-tracking')) return undefined;
  if (!path.startsWith('/') || path.startsWith('//') || /[%\\#]/.test(path.split('?')[0]!) || path.split('?').length > 2) return false;
  const url = new URL(path, 'https://service.invalid'), id = trackingId.source.slice(1, -1), base = `/v1/companies/${id}/stock-tracking`;
  const params = url.searchParams;
  if (new Set(params.keys()).size !== [...params].length) return false;
  const only = (keys: string[]) => [...params.keys()].every(key => keys.includes(key));
  if (new RegExp(`^${base}/context/${id}$`, 'i').test(url.pathname)) return method === 'GET' && only(['resource']) && (!params.has('resource') || ['batches', 'serials', 'stock'].includes(params.get('resource')!));
  if (new RegExp(`^${base}/(?:batches|serials)/field-set$`, 'i').test(url.pathname)) return method === 'GET' && only(['action']) && (!params.has('action') || ['prepare', 'correct', 'hold', 'release', 'retire', 'reactivate'].includes(params.get('action')!));
  if (new RegExp(`^${base}/(?:batches|serials)$`, 'i').test(url.pathname)) return method === 'POST' ? !url.search : method === 'GET' && only(['q', 'sort', 'limit', 'cursor', 'item_id', 'status', 'is_held', ...(url.pathname.endsWith('/batches') ? ['expires_before'] : ['lot_id', 'never_received', 'receipt_eligible', 'source_movement_id'])]) && (!params.has('never_received') || ['true', 'false'].includes(params.get('never_received')!)) && (!params.has('receipt_eligible') || ['true', 'false'].includes(params.get('receipt_eligible')!)) && (!params.has('source_movement_id') || trackingId.test(params.get('source_movement_id')!));
  if (new RegExp(`^${base}/(?:batches|serials)/${id}/history$`, 'i').test(url.pathname)) return method === 'GET' && only(['limit', 'cursor', 'sort']);
  if (new RegExp(`^${base}/(?:batches|serials)/${id}/history/${id}$`, 'i').test(url.pathname)) return method === 'GET' && !url.search;
  if (url.search) return false;
  if (new RegExp(`^${base}/(?:batches|serials)/${id}$`, 'i').test(url.pathname)) return method === 'GET' || method === 'PATCH' && url.pathname.includes('/batches/');
  return method === 'POST' && new RegExp(`^${base}/(?:batches|serials)/${id}/(?:hold|release|retire|reactivate)$`, 'i').test(url.pathname);
}
