import { trackingId } from './stock-tracking-resources';

/** Native stock reads, configuration and count observations; effects use approved vouchers. */
export function allowedStockRequest(method: string, path: string): boolean | undefined {
  if (!path.includes('/stock/') && !path.endsWith('/stock')) return undefined;
  if (!path.startsWith('/') || path.startsWith('//') || /[%\\#]/.test(path.split('?')[0]!) || path.split('?').length > 2) return false;
  const url = new URL(path, 'https://service.invalid'), id = trackingId.source.slice(1, -1);
  if (url.pathname !== path.split('?')[0]) return false;
  const base = `/v1/companies/${id}/stock`, params = url.searchParams;
  if (new Set(params.keys()).size !== [...params].length) return false;
  if (new RegExp(`^${base}/configuration$`, 'i').test(url.pathname)) return method === 'GET' && !url.search;
  if (new RegExp(`^${base}/positions/balance$`, 'i').test(url.pathname)) return method === 'GET' && params.has('item_id') && [...params].every(([key, value]) => ['item_id', 'warehouse_id'].includes(key) && trackingId.test(value));
  if (new RegExp(`^${base}/selection$`, 'i').test(url.pathname)) return method === 'POST' && !url.search;
  if (new RegExp(`^${base}/counts$`, 'i').test(url.pathname)) return method === 'POST' && !url.search;
  if (new RegExp(`^${base}/counts/${id}$`, 'i').test(url.pathname)) return method === 'GET' && !url.search;
  if (new RegExp(`^${base}/counts/${id}/observations$`, 'i').test(url.pathname)) return method === 'POST' && !url.search;
  if (new RegExp(`^${base}/opening-lines$`, 'i').test(url.pathname)) return method === 'GET' && params.has('stock_date') && [...params].every(([key, value]) => {
    if (key === 'stock_date') return /^\d{4}-\d{2}-\d{2}$/.test(value);
    if (key === 'q') return value.trim().length >= 2 && value.length <= 100;
    if (key === 'sort') return ['id', '-id'].includes(value);
    if (key === 'limit') return /^[1-9]\d{0,2}$/.test(value) && Number(value) <= 200;
    return key === 'cursor' && value.length > 0 && value.length <= 4096;
  });
  if (new RegExp(`^${base}/available-units$`, 'i').test(url.pathname)) return method === 'GET' && params.has('position_id') && params.has('stock_date') && [...params].every(([key, value]) => {
    if (key === 'position_id') return trackingId.test(value);
    if (key === 'stock_date') return /^\d{4}-\d{2}-\d{2}$/.test(value);
    if (key === 'operation') return ['SALE_ISSUE', 'TRANSFER_OUT', 'SUPPLIER_RETURN_ISSUE'].includes(value);
    if (key === 'q') return value.length <= 200;
    if (key === 'sort') return ['id', '-id'].includes(value);
    if (key === 'limit') return /^[1-9]\d{0,2}$/.test(value) && Number(value) <= 200;
    return key === 'cursor' && value.length > 0 && value.length <= 4096;
  });
  const resources = '(?:positions|movements|postings|cost-pools|account-policies)';
  if (new RegExp(`^${base}/${resources}/(?:field-set|${id})$`, 'i').test(url.pathname)) return method === 'GET' && !url.search;
  if (!new RegExp(`^${base}/${resources}$`, 'i').test(url.pathname)) return false;
  if (method === 'POST') return url.pathname.endsWith('/account-policies') && !url.search;
  return method === 'GET' && [...params].every(([key, value]) => {
    if (['item_id', 'warehouse_id', 'bin_id', 'lot_id', 'posting_id', 'voucher_id'].includes(key)) return trackingId.test(value);
    if (key === 'sort') return ['id', '-id'].includes(value);
    if (key === 'limit') return /^[1-9]\d{0,2}$/.test(value) && Number(value) <= 200;
    return key === 'cursor' && value.length > 0 && value.length <= 4096;
  });
}
