'use client';

import { Badge, Button, Modal, Notice, ReviewList, useFormatters } from '@janso/ui';
import {
  isAccountLine,
  isBlank,
  sameAmount,
  type DraftLine,
  type DraftProblem,
  type SalesDraft,
} from '../lib/sales-entry-draft';
import { freeQuantity, shortQuantity, spokenPlaces } from '../lib/sales-entry-columns';
import { totalsLines } from './SalesEntryTotals';
import type { InvoicePreview } from '../lib/sales-entry-preview';
import type { SalesEntryPolicy } from '../lib/sales-entry-policy';
import { TENDER_LABELS } from '../lib/sales-entry-draft';

/**
 * "Preview": the bill as a reader should check it before saving.
 *
 * **Not a printout.** There is no renderer yet (invoice-design.md §9.1), and a mock of the
 * printed invoice drawn in the browser would be a second layout engine that disagrees with the
 * designer's. What a reader needs before saving is a summary they can check against what the
 * customer agreed — who, when, how much, how it is being paid, and what is still wrong — and that
 * is what this is.
 *
 * It saves from here too, because "check it, then save it" is one motion, and making someone
 * close a dialog to find the save button is a dialog that exists only to be dismissed.
 */
export function SalesReviewDialog({
  draft,
  preview,
  policy,
  problems,
  canSave,
  onSave,
  onClose,
}: {
  draft: SalesDraft;
  preview: InvoicePreview;
  policy: SalesEntryPolicy;
  problems: readonly DraftProblem[];
  canSave: boolean;
  onSave: () => void;
  onClose: () => void;
}) {
  const { money, date, quantity } = useFormatters();
  const say = (value: string) => quantity(value, { precision: spokenPlaces(value) });
  const errors = problems.filter((problem) => problem.severity === 'error');
  const warnings = problems.filter((problem) => problem.severity === 'warning');
  const lines = draft.lines.filter((line) => !isBlank(line));
  const known = (value: string | null) => (value === null ? '—' : money(value));
  const previewLines = new Map(preview.lines.map((entry) => [entry.key, entry]));
  /** What a checker looks for on a line: a departed price, free units, a short supply, a free line. */
  const flags = (line: DraftLine): string[] => {
    const out: string[] = [];
    if (line.rateSource === 'MANUAL' && line.resolvedRate !== '' && !sameAmount(line.rate, line.resolvedRate)) {
      out.push(`Override of ${money(line.resolvedRate, { display: 'none' })}`);
    }
    // Quantities only mean something on a line that has them.
    if (!isAccountLine(draft, line) && freeQuantity(line)) out.push(`${say(freeQuantity(line))} free`);
    if (!isAccountLine(draft, line) && shortQuantity(line)) out.push(`${say(shortQuantity(line))} short`);
    if (line.freePurpose) out.push(`Free: ${line.freePurpose}`);
    return out;
  };

  const settlement = preview.settlement;
  const payments =
    draft.tenders.length === 0
      ? 'Nothing received now'
      : draft.tenders
          .map(
            (tender) =>
              // A figure only when it is one: half-typed text is shown as unknown, not formatted
              // into something that looks like an amount. A cheque says it has yet to clear.
              `${TENDER_LABELS[tender.mode]} ${/^\d+(\.\d+)?$/.test(tender.amount) ? money(tender.amount) : '—'}${
                tender.mode === 'CHEQUE' ? ' (to clear)' : ''
              }`,
          )
          .join(' · ');

  return (
    <Modal
      open
      title="Check this bill before saving"
      size="lg"
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Keep editing
          </Button>
          <Button disabled={!canSave} onClick={onSave}>
            Save draft
          </Button>
        </>
      }
    >
      <div className="janso-entry__panel">
        {errors.length > 0 ? (
          <Notice tone="danger">
            {errors.length === 1 ? 'One thing must' : `${errors.length} things must`} be fixed before
            this can be saved: {errors.slice(0, 3).map((problem) => problem.message).join(' ')}
          </Notice>
        ) : null}
        {warnings.length > 0 ? (
          <Notice tone="warning">
            Saving with {warnings.length === 1 ? 'one thing' : `${warnings.length} things`} to check:{' '}
            {warnings.map((problem) => problem.message).join(' ')}
          </Notice>
        ) : null}

        <ReviewList
          items={[
            { label: 'Customer', value: draft.customerLabel || 'Not chosen' },
            {
              label: 'Dates',
              value: `Invoice ${date(draft.documentDate)} · posts ${date(draft.postingDate)}`,
            },
            {
              label: 'Lines',
              value: `${lines.length} ${lines.length === 1 ? 'line' : 'lines'} · ${
                draft.mode === 'ACCOUNTS' ? 'accounts' : draft.mode === 'MIXED' ? 'mixed' : 'items'
              }`,
            },
            ...(draft.shipToLabel ? [{ label: 'Ship to', value: draft.shipToLabel }] : []),
          ]}
        />

        {/* The lines, with what a checker looks for flagged on each. A count alone could not be
          * checked against what the customer agreed. */}
        <table className="janso-entry__review-lines">
          <caption className="janso-visually-hidden">Lines on this bill</caption>
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">{draft.mode === 'ACCOUNTS' ? 'Account' : 'Item'}</th>
              <th scope="col" data-align="end">Billed</th>
              <th scope="col" data-align="end">Rate</th>
              <th scope="col" data-align="end">Amount</th>
            </tr>
          </thead>
          <tbody>
            {lines.map((line) => {
              const figures = previewLines.get(line.key);
              const marks = flags(line);
              return (
                <tr key={line.key}>
                  <td>{draft.lines.indexOf(line) + 1}</td>
                  <td>
                    {line.subjectLabel || '—'}
                    {marks.map((mark) => (
                      <span key={mark} className="janso-entry__review-flag">
                        <Badge tone="warn">{mark}</Badge>
                      </span>
                    ))}
                  </td>
                  <td data-align="end">{isAccountLine(draft, line) ? '—' : line.billedQuantity ? say(line.billedQuantity) : '—'}</td>
                  <td data-align="end">{line.rate ? money(line.rate, { display: 'none', precision: 4 }) : '—'}</td>
                  <td data-align="end">{figures?.amount ? money(figures.amount, { display: 'none' }) : '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {/* Every row the rail shows, from the same function — so the two cannot disagree, and
          * the charges and round-off that made a total are where a checker can see them. */}
        <ReviewList
          items={[
            ...totalsLines(preview, policy).map((row) => ({
              label: row.label,
              value:
                row.amount === null
                  ? '—'
                  : row.kind === 'deduct' && !sameAmount(row.amount, '0')
                    ? `− ${money(row.amount)}`
                    : money(row.amount),
            })),
            { label: 'Received now', value: payments },
            ...(Number(settlement.advances) > 0
              ? [{ label: 'Advances applied', value: money(settlement.advances) }]
              : []),
            {
              label: 'Left owing',
              value:
                settlement.outstanding === null
                  ? '—'
                  : settlement.dueDate
                    ? `${money(settlement.outstanding)}, due ${date(settlement.dueDate)}`
                    : money(settlement.outstanding),
            },
            ...(settlement.changeDue !== null && Number(settlement.changeDue) > 0
              ? [{ label: 'Change to return', value: money(settlement.changeDue) }]
              : []),
          ]}
        />

        <p className="janso-entry__number-note">
          {/* The same honesty as the rail: these figures are an estimate until the service accepts
            * the bill, and the number shown is a preview that reserves nothing. */}
          Provisional figures. The service calculates and accepts the bill;{' '}
          {policy.issuance.available === false
            ? 'it is saved as a draft and not issued.'
            : 'the number is allocated when it is issued.'}
        </p>
      </div>
    </Modal>
  );
}
