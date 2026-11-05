'use client';

import { Badge, Button, PageHeader } from '@janso/ui';
import { purchaseStatusView } from '../lib/purchase-page';
import type { PurchasePrintAction } from '../lib/purchase-print-action';

/**
 * The top of the live Purchase page: what this is, where the bill stands, and the two things a
 * person does from here besides filling it in — reopen a saved draft, or start another bill.
 * Everything about the record is a chip; everything to do is an action.
 */
export function PurchasePageHeader({ title, status, typeName, currency, canStartNew, locked, onDrafts, print = { kind: 'hidden' } }: {
  title: string; status: string | null; typeName?: string; currency: string;
  canStartNew: boolean; locked: boolean; onDrafts: () => void;
  /** Print of the last saved revision: a link when it may be printed, a disabled button saying why when it may not. */
  print?: PurchasePrintAction;
}) {
  const view = purchaseStatusView(status);
  return <PageHeader
    overline={<a className="janso-link" href="/vouchers">Purchases</a>}
    title={title}
    lede="Record an expense or service bill from a supplier, with or without GST. Purchases of stock cannot be recorded on this screen yet."
    meta={<>
      <Badge tone={view.tone}>{view.label}</Badge>
      {typeName ? <Badge variant="outline">{typeName}</Badge> : null}
      <Badge variant="outline">Amounts in {currency}</Badge>
    </>}
    actions={<>
      {print.kind === 'ready' ? <a className="janso-btn janso-btn--ghost" href={print.href}>Print</a> : null}
      {print.kind === 'blocked' ? <><Button variant="ghost" disabled aria-describedby="purchase-print-blocked">Print</Button><span id="purchase-print-blocked" className="janso-visually-hidden">{print.reason}</span></> : null}
      <Button variant="ghost" disabled={locked} onClick={onDrafts} data-purchase-drafts-trigger>Saved drafts</Button>
      {canStartNew ? <a className="janso-btn janso-btn--ghost" href="/vouchers/new/purchase">New purchase</a> : null}
    </>}
  />;
}
