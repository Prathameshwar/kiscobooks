'use client';
import { useCallback, useEffect, useState } from 'react';
import { SearchSelect, type SearchSelectLoader, type SearchSelectOption } from '@janso/ui';
import { masterRequest } from '../lib/catalog-master-api';
import { accountingRequest } from '../lib/accounting-configuration';
import { requestFailure } from '../lib/service-call';
import type { ServicePage } from '../lib/service-resource';
import { trackingBase, trackingId } from '../lib/stock-tracking-resources';
import { trackingRequest } from '../lib/stock-tracking';
import { useProductMode } from './ProductModeProvider';

type ReferenceRow = Record<string, unknown> & { id: string; company_id?: string; code?: string; name?: string; sku?: string; status?: string };
export function TrackingReference({ company, resource, label, value, onChange, required, disabled, error, itemId }: {
  company: string; resource: 'items' | 'batches' | 'parties'; label: string; value: string | null; onChange: (value: string | null) => void;
  required?: boolean; disabled?: boolean; error?: string; itemId?: string;
}) {
  const simple = useProductMode()?.data?.product_family_sku_enabled === false;
  const [selected, setSelected] = useState<SearchSelectOption | null>(null), [failure, setFailure] = useState('');
  const path = resource === 'batches' ? trackingBase(company, 'batches') : `/v1/companies/${company}/${resource}`;
  const reader = resource === 'batches' ? trackingRequest : resource === 'items' ? masterRequest : accountingRequest;
  const option = (row: ReferenceRow): SearchSelectOption => ({ id: row.id, label: String(row.sku ?? row.code ?? row.name ?? 'Protected record'), meta: row.sku && row.name ? row.name : undefined, disabled: row.status !== 'ACTIVE' });
  const load = useCallback<SearchSelectLoader>(async ({ q, cursor, signal }) => {
    const params = new URLSearchParams({ limit: '50', status: 'ACTIVE' });
    if (q.trim().length >= 2) params.set('q', q.trim());
    if (cursor) params.set('cursor', cursor);
    if (resource === 'batches' && itemId) params.set('item_id', itemId);
    const result = await reader<ServicePage<ReferenceRow>>({ path: path + '?' + params, signal });
    if (!Array.isArray(result.items) || !result.page || result.items.some(row => !trackingId.test(row.id))) throw { status: 502, message: 'Reference options could not be verified.' };
    return { items: result.items.map(option), nextCursor: result.page.has_more ? result.page.next_cursor : null };
  }, [reader, path, resource, itemId]);
  useEffect(() => {
    const controller = new AbortController(); setSelected(null); setFailure('');
    if (value && trackingId.test(value)) reader<ReferenceRow>({ path: path + '/' + value, signal: controller.signal }).then(row => {
      if (row.id !== value || row.company_id !== company) throw { status: 502, message: 'Reference ownership could not be verified.' };
      if (!controller.signal.aborted) setSelected(option(row));
    }).catch(reason => { if (!controller.signal.aborted) setFailure(requestFailure(reason).message); });
    return () => controller.abort();
  }, [value, company, path, reader]);
  return <SearchSelect label={simple && resource === 'items' ? 'Product' : label} value={value} selected={selected} loadOptions={load} scopeKey={`${company}:${resource}:${itemId ?? ''}`} onChange={onChange} required={required} disabled={disabled} error={error || failure} hint={resource === 'items' ? simple ? 'Choose an active product. Its published profile determines tracking requirements.' : 'Choose an active product/SKU. Its published profile determines tracking requirements.' : undefined} />;
}
