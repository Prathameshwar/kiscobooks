'use client';

import { Badge, Button, useFormatters } from '@janso/ui';
import * as D from '../lib/fixed-decimal';
import type { PurchaseProblem, PurchaseWorkspaceDraft, purchaseWorkspacePreview } from '../lib/purchase-workspace';

export function PurchaseWorkspaceTotals({ draft, preview, problems, onProblem }: {
  draft: PurchaseWorkspaceDraft;
  preview: ReturnType<typeof purchaseWorkspacePreview>; problems: readonly PurchaseProblem[];
  onProblem: (problem: PurchaseProblem) => void;
}) {
  const { money, date } = useFormatters();
  const figure = (amount: D.Fixed | null) => amount === null ? '—' : money(D.format(amount));
  const row = (label: string, amount: D.Fixed | null, grand = false) => <p key={label} className={'janso-entry__total' + (grand ? ' janso-entry__total--grand' : '')}>
    <span className="janso-entry__total-label">{label}</span><strong className="janso-entry__total-value">{figure(amount)}</strong></p>;
  return <aside className="janso-entry-workspace__aside" aria-label="Purchase totals">
    <section className="janso-entry__rail-card" aria-labelledby="purchase-summary-title">
      <div className="janso-entry-workspace__section-head"><h2 id="purchase-summary-title">Bill summary</h2><Badge>Provisional</Badge></div>
      {row('Line subtotal', preview.gross)}
      {row('Line discounts', preview.discount === null ? null : -preview.discount)}
      {row('After line discounts', preview.net)}
      {preview.components.discount !== 0n ? row('Document discounts', preview.components.discount === null ? null : -preview.components.discount) : null}
      {row('Supplier charges', preview.freight)}
      {preview.evidence ? preview.evidence.taxes.map(tax => row(tax.label, D.parse(tax.amount))) : row('Supplier tax', null)}
      {row('Bill total', preview.total, true)}
      <p className="janso-entry__provisional">{preview.evidence ? 'Uses a bounded supplied example recipe. Provisional only; no financial entry is created.' : 'Tax and charges need calculation evidence. A bill total is unavailable; missing amounts are not treated as zero.'}</p>
      {preview.recipientTax !== null && preview.recipientTax > 0n ? <><p className="janso-entry-workspace__caption">Separate recipient liability · excluded from supplier payable</p>{row('Recipient tax liability', preview.recipientTax)}</> : null}
      {preview.components.landedCharges !== null && preview.components.landedCharges > 0n ? <><p className="janso-entry-workspace__caption">Additional cost only · excluded from supplier payable</p>{row('Additional cost intention', preview.components.landedCharges)}</> : null}
    </section>
    <section className="janso-entry__rail-card" aria-label="Settlement intentions"><h2>Payment & terms</h2>
      <p className="janso-entry-workspace__caption">Due {preview.settlement.dueDate ? date(preview.settlement.dueDate) : '—'} · {draft.details.termsBasis === 'INVOICE_DATE' ? 'from invoice date' : 'from posting date'}</p>
      {row('Advances to apply', preview.settlement.advance)}{row('Payment to record', preview.settlement.payment)}
      {(preview.settlement.advance !== null && preview.settlement.advance > 0n) || (preview.settlement.payment !== null && preview.settlement.payment > 0n) ? row('Remaining if applied', preview.settlement.remaining, true) : null}
      <p className="janso-entry-workspace__caption">Proposed only. Nothing has been applied, paid or cleared.</p>
    </section>
    {draft.details.declaredTotal !== '' ? <section className="janso-entry__rail-card" aria-label="Supplier total comparison"><h2>Supplier total comparison</h2>
      {row('Original supplier total', preview.settlement.declared)}{draft.details.comparison === 'SUPPLIER_REVISED' ? row('Supplier revised total', preview.settlement.revised) : null}
      {row('Supplier minus calculated', preview.settlement.difference)}<p className="janso-entry-workspace__caption">{preview.settlement.difference === null ? 'Comparison needs complete calculation evidence.' : preview.settlement.difference === 0n ? 'Matches the provisional bill total.' : 'Difference needs correction or a matching supplier revision.'}</p>
    </section> : null}
    <section className="janso-entry__rail-card" aria-label="Entry guidance">
      <h2>Before you finish</h2>
      <p className="janso-entry-workspace__caption">Use the supplier’s own invoice number. Your internal voucher reference is assigned later.</p>
      <p className="janso-entry-workspace__caption">Check receipt quantity against what arrived, and billed quantity against the supplier’s invoice.</p>
    </section>
    {problems.length > 0 ? <section className="janso-entry__rail-card" aria-label="Purchase issues" role="region">
      <h2>{problems.length} {problems.length === 1 ? 'detail needs' : 'details need'} attention</h2>
      <ul className="janso-entry-workspace__issues">{problems.map(problem => <li key={problem.key}><Button variant="ghost" type="button" onClick={() => onProblem(problem)}>{problem.message}</Button></li>)}</ul>
    </section> : null}
  </aside>;
}
