'use client';

import { Badge, useFormatters } from '@janso/ui';
import type { SupplierBalance } from '../lib/purchase-supplier-balance';

/** `Cr`/`Dr` is the books' word; the badge says what it means for this bill. Each is text, so neither rests on colour alone. */
const SIDES = {
  CR: { mark: 'Cr', meaning: 'To pay', tone: 'warn' },
  DR: { mark: 'Dr', meaning: 'To receive', tone: 'info' },
  NIL: { mark: '', meaning: 'Settled', tone: 'neutral' },
} as const;

/**
 * One figure under the Supplier field: what the company owes this supplier (or is owed) before this bill.
 * It sits in a live region, so a screen reader hears it arrive, and it never takes focus or disables a
 * field: the balance is read in the background and the bill can be filled in meanwhile.
 */
export function PurchaseSupplierBalance({ balance }: { balance: SupplierBalance | undefined }) {
  const { money, date } = useFormatters();
  if (!balance) return null;
  const side = balance.status === 'ready' ? SIDES[balance.side] : null;
  return <div className="janso-purchase-balance" role="status" aria-live="polite" data-purchase-balance={balance.status}>
    <span className="janso-purchase-balance__label">Balance</span>
    {balance.status === 'loading' ? <span className="janso-purchase-balance__note">Checking the balance…</span> : null}
    {balance.status === 'unavailable' ? <span className="janso-purchase-balance__note">Not available right now. You can carry on with the bill.</span> : null}
    {balance.status === 'ready' && side ? <>
      <strong className="janso-purchase-balance__amount">{money(balance.amount)}{side.mark ? <span className="janso-purchase-balance__side"> {side.mark}</span> : null}</strong>
      <Badge tone={side.tone}>{side.meaning}</Badge>
      <span className="janso-purchase-balance__note">As of {date(balance.asOf)}, before this bill</span>
    </> : null}
  </div>;
}
