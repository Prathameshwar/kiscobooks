/** Print requests carry saved identities; this boundary has no layout or posting writes. */
export function allowedPurchasePrintRequest(service: string, method: string, path: string): boolean {
  if (service !== 'vouchers' || /[\\#\x00-\x20\x7f]/.test(path)) return false;
  const uuid = '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}';
  const root = `/v1/companies/${uuid}`;
  if (method === 'POST') return new RegExp(`^${root}/vouchers/${uuid}/print-jobs$`, 'i').test(path);
  if (method !== 'GET') return false;
  if (new RegExp(`^${root}/voucher-print-jobs/${uuid}$`, 'i').test(path)) return true;
  const split = path.split('?');
  if (split.length !== 2 || !new RegExp(`^${root}/voucher-print-jobs/${uuid}/download$`, 'i').test(split[0]!)) return false;
  const params = new URLSearchParams(split[1]);
  return [...params].length === 1 && params.has('token')
    && /^[a-zA-Z0-9_.=-]{1,2000}$/.test(params.get('token')!);
}
