import { productFieldRequest as request } from './product-fields';
import { trackingId } from './stock-tracking-resources';
import type { Choice } from './voucher-fields';

type Target = { resource: string; id: string };
/** Current labels supplement captured evidence; they never replace its stored versions. */
export async function voucherReferenceLabels(company: string, targets: readonly Target[], signal: AbortSignal, onBatch?: (labels: ReadonlyMap<string, Choice>) => void): Promise<Map<string, Choice>> {
  const labels = new Map<string, Choice>();
  const bounded = targets.filter(row => ['accounts', 'parties', 'items'].includes(row.resource) && trackingId.test(row.id)).slice(0, 200);
  for (let offset = 0; offset < bounded.length && !signal.aborted; offset += 5) {
    await Promise.all(bounded.slice(offset, offset + 5).map(async ({ resource, id }) => {
      try {
        const row = await request<Choice & { company_id: string }>(resource === 'items' ? 'catalog' : 'accounting', 'GET', `/v1/companies/${company}/${resource}/${id}`, undefined, undefined, signal);
        if (row.id === id && row.company_id === company) labels.set(resource + '/' + id, row);
      } catch { /* Protected or absent current masters retain their captured IDs. */ }
    }));
    if (!signal.aborted) onBatch?.(new Map(labels));
  }
  return labels;
}
