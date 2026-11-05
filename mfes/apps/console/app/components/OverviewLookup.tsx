'use client';
import { useMemo, useState } from 'react';
import { SearchSelect } from '@janso/ui';
import { customerLedgerLookup } from '../lib/company-overview';

/**
 * Find one current customer and open their native ledger. Company totals elsewhere on the page
 * stay company-wide; this only locates a customer, which is a party read of its own.
 */
export function OverviewLookup({ company }: { company: string }) {
  const [customer, setCustomer] = useState<{ id: string; company: string } | null>(null);
  const customers = useMemo(() => customerLedgerLookup(company), [company]);
  const selected = customer?.company === company ? customer.id : null;
  return <div className="janso-overview__lookup">
    <SearchSelect label="Find customer ledger" value={selected} loadOptions={customers} scopeKey={company} minQueryLength={0} onChange={id => setCustomer(id ? { id, company } : null)} />
    {selected && <a className="janso-link" href={'/reports/workspace?report=PARTY_LEDGER&party_id=' + encodeURIComponent(selected)}>Open customer ledger</a>}
  </div>;
}
