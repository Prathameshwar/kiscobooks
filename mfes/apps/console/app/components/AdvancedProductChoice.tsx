'use client';
import { useCallback } from 'react';
import { SearchSelect, type SearchSelectLoader, type SearchSelectOption } from '@janso/ui';
import { masterRequest } from '../lib/catalog-master-api';

type Choice = { id: string; name?: string; code?: string; label?: string; value?: string; kind?: string; is_active?: boolean; is_variant_capable?: boolean };
type Page = { items: Choice[]; page: { has_more: boolean; next_cursor?: string | null } };
export function AdvancedProductChoice({ company, resource, label, value, selected, onChange, required, disabled, error, parent, kind }: {
  company: string; resource: string; label: string; value: string; selected?: string;
  onChange: (value: string, label: string) => void; required?: boolean; disabled?: boolean;
  error?: string; parent?: string; kind?: string;
}) {
  const source = ['product-types', 'warehouses'].includes(resource) ? resource : resource === 'attribute_definitions' ? 'attribute-definitions' : `option-sources/catalog.${resource}`;
  const load = useCallback<SearchSelectLoader>(async ({ q, cursor, signal }) => {
    const params = new URLSearchParams({ limit: '50' });
    if (q.trim().length >= 2) params.set('q', q.trim());
    if (cursor) params.set('cursor', cursor);
    if (parent) params.set('parent_id', parent);
    const page = await masterRequest<Page>({ path: `/v1/companies/${company}/${source}?${params}`, signal });
    return { items: page.items.filter(row => row.is_active !== false && (resource !== 'attribute_definitions' || row.is_variant_capable) && (!kind || !row.kind || row.kind === kind || row.kind === 'BOTH')).map(row => ({ id: row.value ?? row.id, label: row.label ?? row.name ?? row.code ?? 'Choice', meta: row.code })), nextCursor: page.page.has_more ? page.page.next_cursor ?? null : null };
  }, [company, source, parent, kind]);
  const current: SearchSelectOption | null = value ? { id: value, label: selected ?? 'Selected choice' } : null;
  return <SearchSelect label={label} value={value || null} selected={current} loadOptions={load} scopeKey={source + ':' + parent + ':' + kind} minQueryLength={0} required={required} clearable={!required} disabled={disabled} error={error} onChange={(id, option) => onChange(id ?? '', option?.label ?? '')} />;
}
