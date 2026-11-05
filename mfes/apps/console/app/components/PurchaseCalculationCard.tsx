'use client';

import { Badge, useFormatters } from '@janso/ui';
import type { PurchaseCalculation } from '../lib/purchase-api';
import * as D from '../lib/fixed-decimal';

/** The bill's lines as the person knows them, by the key Accounting calculated them under. */
export type CalculatedLine = { key: string; label: string };
const COMPONENT_NAMES: Record<string, string> = { CGST: 'CGST', SGST: 'SGST', UTGST: 'UTGST', IGST: 'IGST', CESS: 'Cess' };
const amount = (value: string) => D.parse(value) ?? D.ZERO;

/**
 * Accounting's own calculation of the saved bill. It exists only once there is one: before that
 * there is nothing to show, and a placeholder card would only reserve room for it.
 *
 * A bill with GST shows it the way it was worked out: each component once, then line by line. Tax the
 * supplier did not charge (reverse charge) is shown, and said to be the company's own to pay, because
 * it is not part of what the supplier is owed.
 */
export function PurchaseCalculationCard({ calculation, accepted, differs = false, revision, lines = [] }: {
  calculation: PurchaseCalculation; accepted: boolean; revision: number; lines?: readonly CalculatedLine[];
  /** The bill has an accepted calculation, and this one is not it. */
  differs?: boolean;
}) {
  const { money } = useFormatters();
  const rows = calculation.lines ?? [];
  const taxes = rows.flatMap(row => row.taxes ?? []);
  const totals = new Map<string, { code: string; charged: boolean; amount: D.Fixed }>();
  for (const tax of taxes) {
    const key = tax.code + (tax.supplier_charged ? ':charged' : ':reverse');
    totals.set(key, { code: tax.code, charged: tax.supplier_charged, amount: (totals.get(key)?.amount ?? D.ZERO) + amount(tax.amount) });
  }
  const reverse = taxes.some(tax => !tax.supplier_charged);
  const label = (key: string, index: number) => lines.find(line => line.key === key)?.label || 'Line ' + (index + 1);
  return <section className="janso-entry-workspace__panel" aria-label="Accounting calculation">
    <div className="janso-entry-workspace__section-head">
      <h2>Accounting calculation</h2>
      <Badge tone={differs ? 'warn' : accepted ? 'success' : 'info'}>{differs ? 'Differs from the accepted calculation' : accepted ? 'Accepted' : 'Ready to accept'}</Badge>
    </div>
    <dl className="janso-purchase-figures">
      <div><dt>Commercial total</dt><dd>{money(calculation.commercial_total)}</dd></div>
      <div><dt>Tax</dt><dd>{money(calculation.tax_total)}</dd></div>
      {[...totals.values()].map(row => <div key={row.code + row.charged} className="janso-purchase-figures__component"><dt>{COMPONENT_NAMES[row.code] ?? row.code}{row.charged ? '' : ' · reverse charge'}</dt><dd>{money(D.format(row.amount))}</dd></div>)}
      <div><dt>Rounding</dt><dd>{money(calculation.rounding)}</dd></div>
      <div data-emphasis="true"><dt>Supplier payable</dt><dd>{money(calculation.payable)}</dd></div>
      {calculation.supplier_difference != null ? <div><dt>Difference from supplier’s own total</dt><dd>{money(calculation.supplier_difference)}</dd></div> : null}
    </dl>
    {reverse ? <p className="janso-entry-workspace__caption">Reverse-charge GST is yours to pay to the government. It is part of the tax total above, and not part of the supplier payable.</p> : null}
    {taxes.length ? <table className="janso-purchase-tax-table">
      <caption>GST line by line</caption>
      <thead><tr><th scope="col">Line</th><th scope="col">Taxable value</th><th scope="col">GST</th><th scope="col">Line payable</th></tr></thead>
      <tbody>{rows.map((row, index) => <tr key={row.key}>
        <th scope="row">{label(row.key, index)}</th>
        <td>{money(row.taxable)}</td>
        <td>{money(D.format(D.add(D.ZERO, ...(row.taxes ?? []).map(tax => amount(tax.amount)))))}</td>
        <td>{money(row.payable)}</td>
      </tr>)}</tbody>
    </table> : null}
    <p className="janso-entry-workspace__caption">Calculated by Accounting for revision {revision}. {differs ? 'This is not the calculation that was accepted: Accounting now works out something different. Accept this calculation to submit the bill with it.' : accepted ? 'Accepted for submission.' : 'Review it, then accept it to submit the bill.'}</p>
  </section>;
}
