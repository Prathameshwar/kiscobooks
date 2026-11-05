'use client';
import { useState } from 'react';
import { ArrowRightIcon, Card, CardBody, CardFooter, CardHeader, ListRow, SegmentedControl, WarnTriangleIcon } from '@janso/ui';
import type { Overview } from '../lib/company-overview';
import type { OverviewFormat } from '../lib/overview-format';
import { isPositive, shareOf } from '../lib/overview-shares';
import { OverviewLookup } from './OverviewLookup';

type Side = 'customers' | 'suppliers';
const SIDES = [{ value: 'customers' as const, label: 'Customers' }, { value: 'suppliers' as const, label: 'Suppliers' }];

/**
 * The five largest open balances on one side of the books, each linking to the party's native
 * ledger. Finding a customer and opening a party directory are party reads, separate from the
 * report read that produced these figures, so they stay behind their own permission.
 */
export function OverviewParties({ data, fmt, company, canReadParties }: { data: Overview; fmt: OverviewFormat; company: string; canReadParties: boolean }) {
  const [side, setSide] = useState<Side>('customers');
  const items = side === 'customers' ? data.receivables : data.payables;
  const title = side === 'customers' ? 'Who owes you' : 'Whom you owe';
  return <Card>
    <CardHeader title={title} subtitle={`Largest open balances at ${fmt.date(data.date_to)}`}
      action={<SegmentedControl label="Balances to show" value={side} options={SIDES} onChange={setSide} />} />
    <CardBody><div className="janso-flow">
      {items.parties.length > 0
        ? <div className="janso-overview__rows">
          {items.parties.map((party, index) => <ListRow key={party.party_id} rank={index + 1} primary={party.name}
            href={'/reports/workspace?report=PARTY_LEDGER&party_id=' + encodeURIComponent(party.party_id)}
            figure={fmt.money(party.outstanding)} share={shareOf(party.outstanding, items.gross)} tone={isPositive(party.overdue) ? 'warn' : 'brand'}
            meta={isPositive(party.overdue)
              ? <span className="janso-overview__overdue"><WarnTriangleIcon size={13} /> {fmt.money(party.overdue)} in overdue bills</span>
              : 'No overdue bills'} />)}
        </div>
        : <p className="janso-overview__quiet">{side === 'customers' ? 'No customer has an open balance.' : 'No supplier has an open balance.'}</p>}
      {side === 'customers' && canReadParties && <OverviewLookup company={company} />}
    </div></CardBody>
    {canReadParties && <CardFooter>
      <span>{items.parties.length > 0 ? `Top ${items.parties.length} by balance` : 'Nothing outstanding'}</span>
      <a className="janso-link janso-overview__more" href={side === 'customers' ? '/accounting/parties?role=CUSTOMER' : '/accounting/suppliers'}>
        {side === 'customers' ? 'Customer directory' : 'Supplier directory'} <ArrowRightIcon size={16} />
      </a>
    </CardFooter>}
  </Card>;
}
