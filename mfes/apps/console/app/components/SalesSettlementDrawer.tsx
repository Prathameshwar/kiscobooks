'use client';

import { useEffect, useState } from 'react';
import {
  AmountField,
  Button,
  Drawer,
  Notice,
  SectionHeader,
  Select,
  TextField,
  useFormatters,
} from '@janso/ui';
import * as D from '../lib/fixed-decimal';
import { isAvailable, type SalesEntryPolicy, type TenderMode } from '../lib/sales-entry-policy';
import {
  REFERENCE_LABELS,
  TENDER_LABELS,
  inSentence,
  type DraftAction,
  type DraftProblem,
  type SalesDraft,
} from '../lib/sales-entry-draft';
import type { InvoicePreview } from '../lib/sales-entry-preview';

/** An open advance the customer has on account, as Accounting projects it. */
export type OpenAdvance = { readonly id: string; readonly label: string; readonly available: string };

export type AdvanceLoader = (customerId: string) => Promise<readonly OpenAdvance[]>;

/**
 * How the bill is being paid.
 *
 * Three separate mechanisms, because the platform keeps them separate (Sales configuration §1):
 * credit terms, money received now in one or more modes, and existing advances applied. They
 * meet in **one settlement equation** — total, less advances, less money received, is what is
 * left owing — and **payment method never changes revenue or tax**. A UPI payment and a cash
 * payment for the same bill produce the same invoice; only the settlement differs.
 *
 * What this deliberately does not do:
 *
 *  - **Treat an advance as a receipt.** Applying one points at an open credit Accounting already
 *    holds. No new money moves, so there is no mode, no reference and no tender for it.
 *  - **Hold a card number.** A card tender carries the gateway's approval code and nothing else,
 *    and a reference that looks like a card number is refused (CLAUDE.md §5.10).
 *  - **Return change on anything but cash.** Nobody hands back change on a UPI payment; money
 *    received beyond the bill that cash cannot return is an error to fix, not a credit to keep.
 */
/** The smaller of an advance's balance and what the bill still owes; `null` when nothing is owed. */
export function advanceToApply(available: string, outstanding: string | null): string | null {
  const balance = D.parse(available.trim());
  const owing = outstanding === null ? null : D.parse(outstanding);
  if (balance === null || owing === null || owing <= D.ZERO) return null;
  return D.format(D.min(balance, owing));
}

export function SalesSettlementDrawer({
  draft,
  policy,
  preview,
  problems,
  dispatch,
  loadAdvances,
  onUnstorable,
  onClose,
}: {
  draft: SalesDraft;
  policy: SalesEntryPolicy;
  preview: InvoicePreview;
  problems: readonly DraftProblem[];
  dispatch: (action: DraftAction) => void;
  loadAdvances?: AdvanceLoader;
  /**
   * A figure field holding text that cannot be stored, by its problem field — so the page can
   * refuse to save a value the reader cannot see. See `NumericInputOptions.onUnstorable`.
   */
  onUnstorable?: (field: string, problem: string | null) => void;
  onClose: () => void;
}) {
  const { money, date } = useFormatters();
  const at = (key: string, field: string) =>
    problems.find((problem) => problem.lineKey === null && problem.field === `${key}.${field}`);
  const tendersProblem = problems.find((problem) => problem.field === 'tenders');
  // The rail links "advances are more than the bill" here, so here is where it has to be said.
  const advancesProblem = problems.find((problem) => problem.lineKey === null && problem.field === 'advances');
  const settlement = preview.settlement;
  const outstanding = settlement.outstanding;
  const canSplit = isAvailable(policy.settlement.splitTender);
  const canAddTender =
    isAvailable(policy.settlement.immediateTender) && (canSplit || draft.tenders.length === 0);

  const [advances, setAdvances] = useState<readonly OpenAdvance[] | null>(null);
  const [advanceFailure, setAdvanceFailure] = useState<string | null>(null);
  /* Bumped by "Try again": a failure that tells the reader to retry has to offer the retry. */
  const [advanceAttempt, setAdvanceAttempt] = useState(0);
  useEffect(() => {
    if (!draft.customerId || !loadAdvances || !isAvailable(policy.settlement.advanceApplication)) {
      setAdvances(null);
      return;
    }
    let current = true;
    setAdvanceFailure(null);
    loadAdvances(draft.customerId).then(
      (open) => {
        if (current) setAdvances(open);
      },
      () => {
        if (current) setAdvanceFailure('Open advances could not be loaded.');
      },
    );
    // A switch of customer while the request is in flight must not paint the previous
    // customer's credit as this one's.
    return () => {
      current = false;
    };
  }, [advanceAttempt, draft.customerId, loadAdvances, policy.settlement.advanceApplication]);

  return (
    <Drawer open title="Payment" size="md" onClose={onClose}>
      <div className="janso-entry__panel">
        <div className="janso-entry__settle-summary" aria-live="polite">
          <span className="janso-entry__total-label">Left to settle</span>
          <span className="janso-entry__settle-figure">
            {outstanding === null ? '—' : money(outstanding)}
          </span>
        </div>
        {outstanding === null ? (
          <Notice>
            The amount left to settle is known once the bill&rsquo;s total is — complete the lines
            first.
          </Notice>
        ) : null}

        <SectionHeader
          title="Received now"
          description={
            canSplit
              ? 'One or more payment modes. Each keeps its own reference.'
              : 'One payment mode for this bill type.'
          }
        />
        {!isAvailable(policy.settlement.immediateTender) ? (
          <Notice>{policy.settlement.immediateTender.reason}</Notice>
        ) : (
          <>
            {draft.tenders.map((tender) => {
              const needsReference = policy.settlement.referenceRequired.includes(tender.mode);
              return (
                <div key={tender.key} className="janso-form-grid">
                  <Select
                    label="Mode"
                    value={tender.mode}
                    options={policy.settlement.tenderModes.map((mode) => ({
                      value: mode,
                      label: TENDER_LABELS[mode],
                    }))}
                    onChange={(mode) =>
                      dispatch({ type: 'tender', key: tender.key, patch: { mode: mode as TenderMode } })
                    }
                  />
                  <AmountField
                    label={`${TENDER_LABELS[tender.mode]} amount`}
                    value={tender.amount}
                    error={at(tender.key, 'amount')?.message}
                    onUnstorable={(problem) => onUnstorable?.(`${tender.key}.amount`, problem)}
                    onChange={(amount) =>
                      dispatch({ type: 'tender', key: tender.key, patch: { amount } })
                    }
                  />
                  <TextField
                    label={REFERENCE_LABELS[tender.mode]}
                    {...(needsReference ? {} : { optionalNote: 'optional' })}
                    hint={
                      tender.mode === 'CARD'
                        ? 'The approval code only. Card numbers are never stored.'
                        : tender.mode === 'CHEQUE'
                          ? 'Recorded now; cleared when the bank confirms it.'
                          : undefined
                    }
                    value={tender.reference}
                    maxLength={40}
                    autoComplete="off"
                    error={at(tender.key, 'reference')?.message}
                    onChange={(event) =>
                      dispatch({ type: 'tender', key: tender.key, patch: { reference: event.target.value } })
                    }
                  />
                  {tender.mode === 'CHEQUE' ? (
                    <>
                      <TextField
                        label="Cheque date"
                        type="date"
                        required
                        /* A post-dated or stale cheque is a warning: it is recorded, and the
                         * reader is told it cannot be presented yet, or that a bank will refuse it. */
                        value={tender.instrumentDate}
                        error={
                          at(tender.key, 'instrumentDate')?.severity === 'error'
                            ? at(tender.key, 'instrumentDate')?.message
                            : undefined
                        }
                        hint={
                          at(tender.key, 'instrumentDate')?.severity === 'warning'
                            ? at(tender.key, 'instrumentDate')?.message
                            : undefined
                        }
                        onChange={(event) =>
                          dispatch({
                            type: 'tender',
                            key: tender.key,
                            patch: { instrumentDate: event.target.value },
                          })
                        }
                      />
                      <TextField
                        label="Bank"
                        optionalNote="optional"
                        hint="The bank the cheque is drawn on, as printed on it."
                        value={tender.bank}
                        maxLength={80}
                        autoComplete="off"
                        onChange={(event) =>
                          dispatch({ type: 'tender', key: tender.key, patch: { bank: event.target.value } })
                        }
                      />
                    </>
                  ) : null}
                  <Button
                    variant="ghost"
                    aria-label={`Remove ${inSentence(TENDER_LABELS[tender.mode])} payment`}
                    onClick={() => dispatch({ type: 'removeTender', key: tender.key })}
                  >
                    Remove
                  </Button>
                </div>
              );
            })}
            {tendersProblem ? (
              <p className="janso-error" role="alert">
                {tendersProblem.message}
              </p>
            ) : null}
            {canAddTender ? (
              <div className="janso-entry__settle-actions">
                {policy.settlement.tenderModes.map((mode) => (
                  <Button
                    key={mode}
                    variant="ghost"
                    /*
                     * The commonest case in one press: receive exactly what is left, in this mode.
                     * It is still an amount the reader can see and change, not a hidden "paid in
                     * full" flag.
                     */
                    onClick={() =>
                      dispatch({
                        type: 'addTender',
                        mode,
                        ...(outstanding !== null && Number(outstanding) > 0 ? { amount: outstanding } : {}),
                      })
                    }
                  >
                    {outstanding !== null && Number(outstanding) > 0
                      ? `Receive ${money(outstanding)} by ${inSentence(TENDER_LABELS[mode])}`
                      : `Add ${inSentence(TENDER_LABELS[mode])}`}
                  </Button>
                ))}
              </div>
            ) : null}
          </>
        )}

        <SectionHeader
          title="Advances"
          description="Credit this customer already has on account. Applying it moves no new money."
        />
        {!isAvailable(policy.settlement.advanceApplication) ? (
          <Notice>{policy.settlement.advanceApplication.reason}</Notice>
        ) : !draft.customerId ? (
          <Notice>Choose the customer first — an advance belongs to the party who paid it.</Notice>
        ) : advanceFailure ? (
          <Notice tone="danger">
            {advanceFailure}{' '}
            <button
              type="button"
              className="janso-entry__goto"
              onClick={() => setAdvanceAttempt((attempt) => attempt + 1)}
            >
              Try again
            </button>
          </Notice>
        ) : advances === null ? (
          <p className="janso-entry__number-note">Loading open advances…</p>
        ) : advances.length === 0 ? (
          <p className="janso-entry__number-note">This customer has no unallocated advances.</p>
        ) : (
          <>
          {advancesProblem ? (
            <p className="janso-error" role="alert">
              {advancesProblem.message}
            </p>
          ) : null}
          <ul className="janso-entry__advances">
            {advances.map((open) => {
              const applied = draft.advances.find((entry) => entry.sourceId === open.id);
              return (
                <li key={open.id} className="janso-entry__advance">
                  <span className="janso-entry__advance-label">
                    {open.label}
                    <span className="janso-entry__number-note"> · {money(open.available)} unallocated</span>
                  </span>
                  {applied ? (
                    <span className="janso-form-grid">
                      <AmountField
                        label={`Apply from ${open.label}`}
                        value={applied.amount}
                        error={at(applied.key, 'amount')?.message}
                        onUnstorable={(problem) => onUnstorable?.(`${applied.key}.amount`, problem)}
                        onChange={(amount) => dispatch({ type: 'advance', key: applied.key, amount })}
                      />
                      <Button
                        variant="ghost"
                        aria-label={`Remove ${open.label}`}
                        onClick={() => dispatch({ type: 'removeAdvance', key: applied.key })}
                      >
                        Remove
                      </Button>
                    </span>
                  ) : (
                    <Button
                      variant="ghost"
                      /*
                       * Prefilled with what it can actually settle: the smaller of what is left
                       * on the advance and what the bill still owes. A blank amount that is
                       * immediately an error was a second step every time.
                       */
                      onClick={() =>
                        dispatch({
                          type: 'applyAdvance',
                          sourceId: open.id,
                          sourceLabel: open.label,
                          available: open.available,
                          ...(advanceToApply(open.available, outstanding) !== null
                            ? { amount: advanceToApply(open.available, outstanding)! }
                            : {}),
                        })
                      }
                    >
                      Apply
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
          </>
        )}

        {isAvailable(policy.settlement.credit) ? (
          <>
            <SectionHeader title="On credit" description="Whatever is left is owed on these terms." />
            <p className="janso-entry__number-note">
              {settlement.dueDate
                ? `${money(outstanding ?? '0')} due on ${date(settlement.dueDate)}, ${draft.creditDays} days from the invoice date.`
                : outstanding !== null && Number(outstanding) === 0
                  ? 'Nothing is left on credit.'
                  : 'Set credit days in the bill details to give the balance a due date.'}
            </p>
          </>
        ) : null}
      </div>
    </Drawer>
  );
}
