import { trackingId } from './stock-tracking-resources';

/** A fixed Accounting-only surface; URL normalization and duplicate query keys fail closed. */
export function allowedFinancialOpeningRequest(service: string, method: string, path: string): boolean {
  if (service !== 'accounting' || !path.startsWith('/') || path.startsWith('//') ||
      path.split('?').length > 2 || /[%\\#\x00-\x20\x7f]/.test(path.split('?')[0]!)) return false;
  const url = new URL(path, 'https://opening.invalid');
  const query = url.searchParams, id = trackingId.source.slice(1, -1);
  if (url.pathname !== path.split('?')[0] || new Set(query.keys()).size !== query.size ||
      [...query.values()].some(value => /[\x00-\x1f\x7f]/.test(value))) return false;
  const base = `/v1/companies/${id}`, root = `${base}/opening-batches`;
  const plain = (verb: string) => method === verb && !query.size;
  const list = (filters: string[] = []) => method === 'GET' && [...query].every(([key, value]) => {
    if (key === 'limit') return /^[1-9]\d{0,2}$/.test(value) && +value <= 200;
    if (key === 'sort') return ['id', '-id'].includes(value);
    if (key === 'cursor') return value.length > 0 && value.length <= 4096;
    if (!filters.includes(key)) return false;
    if (['account_id', 'party_id', 'journal_id'].includes(key)) return trackingId.test(value);
    if (key === 'role') return ['CUSTOMER', 'SUPPLIER'].includes(value);
    if (key === 'side') return ['DEBIT', 'CREDIT'].includes(value);
    if (key === 'currency') return /^[A-Z]{3}$/.test(value);
    if (key === 'source_key') return /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$/.test(value);
    if (key === 'status') return ['PENDING', 'WITHDRAWN'].includes(value);
    return key === 'state' && ['STAGED', 'READY', 'COMMITTED', 'BLOCKED', 'CANCELLED'].includes(value);
  });
  const ticket = () => method === 'GET' && query.size === 1 && !!query.get('token') && query.get('token')!.length <= 4096;
  if (new RegExp(`^${root}$`, 'i').test(url.pathname)) return list();
  if (new RegExp(`^${root}/${id}$`, 'i').test(url.pathname)) return plain('GET');
  if (new RegExp(`^${root}/(?:readiness|capabilities|workspaces/field-set)$`, 'i').test(url.pathname)) return plain('GET');
  if (new RegExp(`^${root}/party-balances$`, 'i').test(url.pathname)) return list(['status', 'role', 'party_id']);
  if (new RegExp(`^${root}/master-balances/capture$`, 'i').test(url.pathname)) return plain('GET');
  if (new RegExp(`^${root}/master-balances$`, 'i').test(url.pathname)) return list(['status', 'account_id']) && (!query.has('limit') || +query.get('limit')! <= 50);
  if (new RegExp(`^${root}/master-balances/${id}/withdraw$`, 'i').test(url.pathname)) return plain('POST');
  if (new RegExp(`^${root}/party-balances/${id}/withdraw$`, 'i').test(url.pathname)) return plain('POST');
  if (new RegExp(`^${base}/finance/field-sets/(?:opening-batches|journals|journal-lines|open-items)$`, 'i').test(url.pathname)) return plain('GET');
  if (new RegExp(`^${root}/workspaces(?:/preview)?$`, 'i').test(url.pathname)) return plain('POST');
  if (new RegExp(`^${base}/journals/${id}$`, 'i').test(url.pathname)) return plain('GET');
  if (new RegExp(`^${base}/journals/${id}/(?:post|void|reversal)$`, 'i').test(url.pathname)) return plain('POST');
  if (new RegExp(`^${base}/journal-lines$`, 'i').test(url.pathname)) return query.has('journal_id') && list(['journal_id']);
  const workspace = `${root}/workspaces/${id}`;
  if (new RegExp(`^${workspace}/journals/${id}/recovery$`, 'i').test(url.pathname)) return plain('GET');
  if (new RegExp(`^${workspace}(?:/(?:declaration|reconciliation|export-ticket|entries/${id}(?:/posting-link)?|revisions/${id}))?$`, 'i').test(url.pathname)) return plain('GET');
  if (new RegExp(`^${workspace}/entries$`, 'i').test(url.pathname)) return list(['account_id', 'party_id', 'role', 'side', 'currency', 'source_key']);
  if (new RegExp(`^${workspace}/revisions$`, 'i').test(url.pathname)) return list();
  if (new RegExp(`^${workspace}/export$`, 'i').test(url.pathname)) return ticket();
  if (new RegExp(`^${workspace}/(?:replace|prepare-drafts|finalize|void)$`, 'i').test(url.pathname)) return plain('POST');
  const imports = `${base}/financial-opening-imports`;
  if (new RegExp(`^${imports}$`, 'i').test(url.pathname)) return plain('POST') || list(['state']);
  if (new RegExp(`^${imports}/(?:template|${id}(?:/(?:report-ticket|declaration))?)$`, 'i').test(url.pathname)) return plain('GET');
  if (new RegExp(`^${imports}/${id}/report$`, 'i').test(url.pathname)) return ticket();
  return new RegExp(`^${imports}/${id}/(?:validate|commit|prepare-drafts|cancel)$`, 'i').test(url.pathname) && plain('POST');
}
