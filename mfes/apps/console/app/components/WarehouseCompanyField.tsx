'use client';
import { useCallback, useEffect, useState } from 'react';
import { SearchSelect, type SearchSelectLoader, type SearchSelectOption } from '@janso/ui';
import { masterRequest } from '../lib/catalog-master-api';

type Row = { id: string; code?: string; name?: string; number?: string; regime?: string; jurisdiction_code?: string };
type Page = { items: Row[]; page: { has_more: boolean; next_cursor: string | null } };
const option = (row: Row): SearchSelectOption => ({ id: row.id, label: row.name ?? row.number ?? row.code ?? 'Record', meta: row.number ? [row.regime, row.jurisdiction_code].filter(Boolean).join(' · ') : row.code });
export function WarehouseCompanyField({ company, type, value, canRead, onChange, ...props }: {
  company: string; type: 'department' | 'tax-registration'; value: string | null; canRead: boolean;
  label: string; name: string; disabled?: boolean; required?: boolean; error?: string; hint?: string;
  onChange: (value: string | null) => void;
}) {
  const base = `/v1/companies/${company}/${type === 'department' ? 'departments' : 'tax-registrations'}`;
  const [selected, setSelected] = useState<SearchSelectOption | null>(null);
  useEffect(() => {
    const controller = new AbortController(); setSelected(null);
    if (!canRead || !value) return;
    masterRequest<Page>({ service: 'identity', path: base + '?id=' + value + '&limit=1', signal: controller.signal })
      .then(page => { if (!controller.signal.aborted) setSelected(page.items.some(row => row.id === value) ? option(page.items.find(row => row.id === value)!) : { id: value, label: 'Saved ' + type + ' (unavailable)' }); })
      .catch(() => { if (!controller.signal.aborted) setSelected({ id: value, label: 'Saved ' + type + ' (unavailable)' }); });
    return () => controller.abort();
  }, [base, value, canRead, type]);
  const lookup = useCallback<SearchSelectLoader>(async ({ q, cursor, signal }) => {
    if (!canRead) return { items: [], nextCursor: null };
    if (q.length > (type === 'department' ? 20 : 100)) throw new Error('Search by a shorter code or registration number.');
    const params = new URLSearchParams({ limit: '50' }); if (q.trim().length >= 2) params.set('q', q.trim()); if (cursor) params.set('cursor', cursor);
    const page = await masterRequest<Page>({ service: 'identity', path: base + '?' + params, signal });
    return { items: page.items.map(option), nextCursor: page.page.has_more ? page.page.next_cursor : null };
  }, [base, canRead, type]);
  return <SearchSelect {...props} value={value} selected={value ? selected ?? { id: value, label: 'Saved ' + type } : null} scopeKey={company + ':' + type} loadOptions={lookup} minQueryLength={0}
    disabled={props.disabled || !canRead} hint={!canRead ? 'Read access is needed to change this optional link. The saved value is retained.' : type === 'department' ? 'Optional. Search by department code.' : 'Optional. Search by tax registration number.'} onChange={(id, choice) => { setSelected(choice); onChange(id); }} />;
}
