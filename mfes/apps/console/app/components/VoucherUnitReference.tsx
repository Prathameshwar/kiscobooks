'use client';
import { useMemo } from 'react';
import { SearchSelect } from '@janso/ui';
import { productFieldRequest } from '../lib/product-fields';
import { lookup } from '../lib/voucher-fields';
import { useServiceRead } from '../lib/service-resource';
import type { ServiceRequest } from '../lib/service-call';
import { trackingId } from '../lib/stock-tracking-resources';

const request = <T,>(command: ServiceRequest) => productFieldRequest<T>('catalog', 'GET', command.path, undefined, undefined, command.signal);

/** Base units selected by a product still need their protected human-readable label. */
export function VoucherUnitReference({ company, label, value, disabled, baseOnly, onChange }: { company: string; label: string; value: string; disabled: boolean; baseOnly: boolean; onChange: (id: string | null) => void }) {
  const units = useMemo(() => lookup(company, 'units'), [company]);
  const read = useServiceRead<{ id: string; company_id: string; name?: string; code?: string }>(value && trackingId.test(value) ? '/v1/companies/' + company + '/units/' + value : undefined, request, row => {
    if (row.id !== value || row.company_id !== company) throw { status: 502, message: 'Unit ownership could not be verified.' };
  });
  const current = read.data?.id === value && read.data.company_id === company ? read.data : null;
  const selected = value ? { id: value, label: current?.name ?? current?.code ?? (read.loading ? 'Loading unit…' : 'Unit unavailable'), meta: current?.code, disabled: !current } : null;
  return <SearchSelect label={label} value={value || null} selected={selected} disabled={disabled || baseOnly} loadOptions={units} scopeKey={company} minQueryLength={0} onChange={onChange} error={read.failure?.message} hint={baseOnly ? 'Physical stock uses the product’s base unit.' : undefined} />;
}
