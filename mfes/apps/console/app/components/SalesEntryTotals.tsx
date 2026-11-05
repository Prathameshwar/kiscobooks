'use client';

import type { ReactNode } from 'react';
import { Badge, Button, InfoIcon, Notice, useFormatters } from '@janso/ui';
import * as D from '../lib/fixed-decimal';
import { isAvailable, type SalesEntryPolicy } from '../lib/sales-entry-policy';
import type { DraftProblem, ProblemTarget } from '../lib/sales-entry-draft';
import type { InvoicePreview } from '../lib/sales-entry-preview';

/**
 * The rail: a read-only ledger of truth-so-far.
 *
 * **Sticky**, for the same reason the document bar is: the total is the number a reader is
 * watching, and scrolling a long line list must not take it away.
 *
 * **Nothing here is typeable.** Calculation authority is the service's, in a versioned
 * dependency sequence — line prices, declared component stages, legal taxable bases and
 * components, rounding, then obligation, credits, settlement and remaining debt. A field in this
 * rail would be a second discount engine or a number added to make the books balance, and the
 * calculation contract forbids both. Components are entered where they belong — a line, or the
 * components drawer behind "Edit" — and *appear* here.
 *
 * The figures come from `previewInvoice`, which follows the same order the service does and is
 * exact. They are still labelled **provisional**, and that label is not scaffolding: anything
 * computed in a browser is an estimate, and a total that looks authoritative while being an
 * estimate is the worst thing that could be on this page.
 */

export type TotalsLine = {
  readonly label: string;
  /** `null` when unknown — shown as an em dash, never as zero. */
  readonly amount: string | null;
  readonly kind?: 'add' | 'deduct' | 'grand' | 'detail';
};

/** The rail's rows, from the preview and the policy. Pure, so it is testable without a DOM. */
export function totalsLines(preview: InvoicePreview, policy: SalesEntryPolicy): TotalsLine[] {
  const rows: TotalsLine[] = [{ label: 'Subtotal', amount: preview.subtotal }];
  const anyDiscount =
    isAvailable(policy.components.lineDiscount) ||
    isAvailable(policy.components.selectedLineDiscount) ||
    isAvailable(policy.components.documentDiscount);
  if (anyDiscount) rows.push({ label: 'Discounts', amount: preview.discounts.total, kind: 'deduct' });
  rows.push({ label: 'Taxable value', amount: preview.taxableValue });

  if (preview.tax === null) {
    rows.push({ label: 'Tax', amount: null });
  } else if (preview.supply === 'INTER_STATE') {
    rows.push({ label: 'IGST', amount: preview.tax.igst, kind: 'detail' });
  } else if (preview.supply === 'INTRA_STATE') {
    // Two components, shown as two rows: they are separately computed and separately
    // reported, and a single "GST" figure would hide which one a difference sits in.
    rows.push({ label: 'CGST', amount: preview.tax.cgst, kind: 'detail' });
    rows.push({ label: 'SGST', amount: preview.tax.sgst, kind: 'detail' });
  } else {
    rows.push({ label: 'Tax', amount: preview.tax.total });
  }

  if (isAvailable(policy.components.charges)) {
    rows.push({ label: 'Charges', amount: preview.charges, kind: 'add' });
  }
  if (isAvailable(policy.components.rounding)) {
    rows.push({ label: 'Round off', amount: preview.roundOff });
  }
  rows.push({ label: 'Total', amount: preview.total, kind: 'grand' });
  return rows;
}

export function SalesEntryTotals({
  preview,
  policy,
  problems,
  onEditComponents,
  onEditPayment,
  targetOf,
  onGoTo,
  children,
}: {
  preview: InvoicePreview;
  policy: SalesEntryPolicy;
  problems: readonly DraftProblem[];
  /** Opens the discounts-and-charges drawer. Absent for a reader who may not change the bill. */
  onEditComponents?: () => void;
  /** Opens the payment drawer. Absent for a reader who may not change the bill. */
  onEditPayment?: () => void;
  /** Where a problem is fixed — a line, a field, a drawer — named for the reader. */
  targetOf?: (problem: DraftProblem) => ProblemTarget | null;
  /** Takes the reader there. */
  onGoTo?: (target: ProblemTarget, field?: string) => void;
  /** More cards for the rail — the service's own calculation, when the page is connected. */
  children?: ReactNode;
}) {
  const { money, date } = useFormatters();
  const settlement = preview.settlement;
  const settles =
    isAvailable(policy.settlement.immediateTender) ||
    isAvailable(policy.settlement.advanceApplication) ||
    isAvailable(policy.settlement.credit);

  /**
   * A problem, and a way to get to where it is fixed.
   *
   * A list of problems a reader has to map back onto the page by counting rows is a list nobody
   * uses on a fifty-line bill. The button names the place — "Line 4", "Customer", "Payment" —
   * and goes there, so fixing is one press away.
   */
  const problemItem = (problem: DraftProblem) => {
    const target = onGoTo ? targetOf?.(problem) : null;
    return (
      <li key={`${problem.lineKey ?? 'doc'}-${problem.field}-${problem.message}`}>
        {target && onGoTo ? (
          <>
            <button type="button" className="janso-entry__goto" onClick={() => onGoTo(target, problem.field)}>
              {target.label}
            </button>{' '}
          </>
        ) : null}
        {problem.message}
      </li>
    );
  };
  const errors = problems.filter((problem) => problem.severity === 'error');
  const warnings = problems.filter((problem) => problem.severity === 'warning');
  const rows = totalsLines(preview, policy);

  return (
    <aside className="janso-entry__rail" aria-label="Invoice totals">
      <div className="janso-entry__rail-card">
        {rows.map((row) => (
          <p
            key={row.label}
            className={
              'janso-entry__total' +
              (row.kind === 'grand' ? ' janso-entry__total--grand' : '') +
              // A nil deduction is not signed: "− 0.00" reads as something taken off.
              (row.kind === 'deduct' && row.amount !== null && D.parse(row.amount) !== D.ZERO
                ? ' janso-entry__total--deduct'
                : '') +
              (row.kind === 'detail' ? ' janso-entry__total--detail' : '')
            }
          >
            <span className="janso-entry__total-label">{row.label}</span>
            <span className="janso-entry__total-value">
              {/* An em dash, not a zero. A figure that is not known yet and a figure that is
                * genuinely nothing are different facts, and printing `0.00` for the first is
                * how a reader concludes the tax is zero (design-system §5.3). */}
              {row.amount === null ? '—' : money(row.amount, { display: row.kind === 'grand' ? undefined : 'none' })}
            </span>
          </p>
        ))}

        {onEditComponents ? (
          <Button variant="ghost" onClick={onEditComponents}>
            Discounts and charges
          </Button>
        ) : null}


        <div className="janso-entry__provisional">
          <InfoIcon size={14} aria-hidden="true" />
          <div>
            <p>
              Provisional. The invoice is calculated and accepted by the service, which owns the
              tax base, component order and rounding.
            </p>
            {preview.unresolved.length > 0 ? (
              /* What the preview could not know, stated beside the figures it affects — not
               * hidden, because an unexplained em dash is as unhelpful as a wrong zero. */
              <ul className="janso-entry__unresolved">
                {preview.unresolved.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            ) : null}
          </div>
        </div>
      </div>

      {settles ? (
        /*
         * The settlement, as one equation: total, less advances, less money received, is what
         * is left owing. Payment method never changes revenue or tax, so it sits *below* the
         * invoice figures rather than among them.
         */
        <div className="janso-entry__rail-card" role="group" aria-label="Payment">
          {Number(settlement.advances) > 0 ? (
            <p className="janso-entry__total janso-entry__total--deduct">
              <span className="janso-entry__total-label">Advances applied</span>
              <span className="janso-entry__total-value">{money(settlement.advances, { display: 'none' })}</span>
            </p>
          ) : null}
          {Number(settlement.received) > 0 ? (
            <p className="janso-entry__total janso-entry__total--deduct">
              <span className="janso-entry__total-label">Received</span>
              <span className="janso-entry__total-value">{money(settlement.received, { display: 'none' })}</span>
            </p>
          ) : null}
          {Number(settlement.pendingClearance) > 0 ? (
            <p className="janso-entry__total janso-entry__total--deduct">
              <span className="janso-entry__total-label">Cheque, to clear</span>
              <span className="janso-entry__total-value">
                {money(settlement.pendingClearance, { display: 'none' })}
              </span>
            </p>
          ) : null}
          <p className="janso-entry__total janso-entry__total--grand">
            <span className="janso-entry__total-label">Left owing</span>
            <span className="janso-entry__total-value">
              {settlement.outstanding === null ? '—' : money(settlement.outstanding)}
            </span>
          </p>
          {settlement.dueDate ? (
            <p className="janso-entry__number-note">Due {date(settlement.dueDate)}</p>
          ) : null}
          {settlement.changeDue !== null && Number(settlement.changeDue) > 0 ? (
            /* A separate fact from cash tendered and cash applied — the one the person at the
             * counter actually needs to read. */
            <p className="janso-entry__change">
              Return {money(settlement.changeDue)} in change
            </p>
          ) : null}
          {onEditPayment ? (
            <Button variant="ghost" onClick={onEditPayment}>
              Payment
            </Button>
          ) : null}
        </div>
      ) : null}

      {policy.issuance.available === false ? (
        <Notice tone="info">{policy.issuance.reason}</Notice>
      ) : null}

      {errors.length > 0 ? (
        <div className="janso-entry__rail-card">
          <p className="janso-entry__rail-heading">
            <Badge tone="danger">{errors.length}</Badge>
            {errors.length === 1 ? 'thing to fix' : 'things to fix'}
          </p>
          <ul className="janso-entry__problems">{errors.slice(0, 6).map(problemItem)}</ul>
          {errors.length > 6 ? (
            <p className="janso-entry__number-note">and {errors.length - 6} more.</p>
          ) : null}
        </div>
      ) : null}

      {warnings.length > 0 ? (
        <div className="janso-entry__rail-card">
          <p className="janso-entry__rail-heading">
            {/* Warnings are stated and can be accepted — a warning may be deliberate. Only an
              * error blocks, which is the same split the designer's publish gate uses. */}
            <Badge tone="warn">{warnings.length}</Badge>
            {warnings.length === 1 ? 'thing to check' : 'things to check'}
          </p>
          <ul className="janso-entry__problems">{warnings.slice(0, 6).map(problemItem)}</ul>
        </div>
      ) : null}
      {children}
    </aside>
  );
}
