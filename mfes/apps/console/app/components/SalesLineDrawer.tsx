'use client';

import { Drawer, FieldGrid, Notice, SegmentedControl, Select, TextField, useFormatters } from '@janso/ui';
import { isAvailable, type SalesEntryPolicy } from '../lib/sales-entry-policy';
import { freeQuantity, isRewardLine, shortQuantity, spokenPlaces } from '../lib/sales-entry-columns';
import {
  differenceDirection,
  isAccountLine,
  isGoodsLine,
  quantitiesDiffer,
  sameAmount,
  type DraftLine,
  type DraftProblem,
  type SalesDraft,
} from '../lib/sales-entry-draft';

/**
 * One line's long tail.
 *
 * Twelve columns is already more than fits a laptop, and the fields here are the ones a reader
 * touches on *some* lines rather than every line: where the goods come from, which batch, what
 * this line does to stock, why its quantities differ, why its rate does. Tally hides them behind
 * F12; Zoho Books uses a row expander; QuickBooks mostly does not have them at all.
 *
 * A `Drawer`, not a `Modal`: it is a side task on one row of a document that stays visible, and
 * a centred dialog over a grid loses the reader's place in it.
 *
 * **The reason fields live here on purpose.** A quantity difference and a rate override each
 * need a stated reason, and a reason typed into a narrow grid cell is a reason nobody reads. The
 * grid marks the row and names the missing field; this is where it gets answered.
 */

/*
 * What a goods line does to stock. "No stock effect" is not among them: the calculation contract
 * has no unrestricted "does not affect stock" switch on a goods line — goods billed here move
 * now, moved already on a delivery note, or move later. A service has no stock to move, and is
 * told so rather than offered a choice.
 */
const STOCK_INTENT = [
  { value: 'EXECUTE', label: 'Dispatch now' },
  { value: 'REFERENCE_EXISTING', label: 'Already dispatched' },
  { value: 'DEFERRED', label: 'Dispatch later' },
];

export function SalesLineDrawer({
  line,
  ordinal,
  draft,
  policy,
  problems,
  onPatch,
  onClose,
  canEdit = true,
}: {
  line: DraftLine;
  ordinal: number;
  draft: SalesDraft;
  policy: SalesEntryPolicy;
  problems: readonly DraftProblem[];
  onPatch: (patch: Partial<DraftLine>) => void;
  onClose: () => void;
  /**
   * False for a reader who may look but not change the bill. The detail still opens — what a
   * line carries is worth reading — but every field in it is read-only, as the grid's are.
   */
  canEdit?: boolean;
}) {
  const { money, quantity } = useFormatters();
  /** A quantity in a sentence: the company's separators, only the places it has. */
  const say = (value: string) => quantity(value, { precision: spokenPlaces(value) });
  const locked = !canEdit;
  const at = (field: string) =>
    problems.find((problem) => problem.lineKey === line.key && problem.field === field)?.message;
  // Quantities and their reasons belong to a line that has quantities; stock to goods.
  const measured = !isAccountLine(draft, line);
  const goods = isGoodsLine(draft, line);
  const direction = differenceDirection(line);
  const reasons = policy.quantities.differenceReasons.filter(
    (reason) => reason.applies === 'EITHER' || reason.applies === direction,
  );
  const free = line.rate.trim() !== '' && sameAmount(line.rate, '0');
  const reward = isRewardLine(line);
  // Any difference owes a reason — more leaving than charged for, or fewer. The reason picker
  // follows the rule that demands it, not only the case of it that is a bonus.
  const differ = quantitiesDiffer(line);
  const short = shortQuantity(line);

  return (
    <Drawer
      open
      title={`Line ${ordinal}${line.subjectLabel ? ` · ${line.subjectLabel}` : ''}`}
      size="md"
      onClose={onClose}
    >
      <div className="janso-entry__panel">
        <FieldGrid>
          <TextField
            disabled={locked}
            label="Description"
            hint="As it prints on the document."
            value={line.description}
            maxLength={500}
            onChange={(event) => onPatch({ description: event.target.value })}
          />
          {measured ? (
            <TextField
              disabled={locked}
              label="HSN/SAC"
              /* Required where applicable even on an accounts-only entry, per the calculation
               * contract — so it is captured, not inferred from a display preference. */
              hint="Statutory classification for this supply."
              value={line.hsnSac}
              maxLength={16}
              error={at('hsnSac')}
              onChange={(event) => onPatch({ hsnSac: event.target.value })}
            />
          ) : null}
        </FieldGrid>

        {measured && !goods ? (
          <Notice>A service moves no stock, so this line has no dispatch to choose.</Notice>
        ) : null}

        {goods ? (
          <>
            <SegmentedControl
              disabled={locked}
              label="What this line does to stock"
              showLabel
              value={line.stockIntent}
              options={STOCK_INTENT}
              onChange={(stockIntent) =>
                onPatch({ stockIntent: stockIntent as DraftLine['stockIntent'] })
              }
            />
            {/* The rule the calculation contract is emphatic about: goods billed against a
              * challan must not move a second time, and a deferred bill must not fabricate a
              * movement that has not happened. */}
            {line.stockIntent === 'REFERENCE_EXISTING' ? (
              <Notice>
                The goods have already moved on a delivery note, so this bill reconciles the
                billing and does not dispatch anything again.
              </Notice>
            ) : null}
            {at('stockIntent') ? <Notice tone="danger">{at('stockIntent')}</Notice> : null}
            {line.stockIntent === 'DEFERRED' ? (
              <Notice tone="warning">
                Nothing is dispatched by this bill. The movement is recorded when it happens and is
                linked back to this line.
              </Notice>
            ) : null}

            <FieldGrid>
              <TextField
                disabled={locked}
                label="Warehouse"
                value={line.warehouse}
                onChange={(event) => onPatch({ warehouse: event.target.value })}
              />
              <TextField
                disabled={locked}
                label="Batch or lot"
                value={line.batch}
                onChange={(event) => onPatch({ batch: event.target.value })}
              />
              <TextField
                disabled={locked}
                label="Expiry"
                type="date"
                /* A business date, never a datetime (CLAUDE.md §4). */
                value={line.expiry}
                onChange={(event) => onPatch({ expiry: event.target.value })}
              />
            </FieldGrid>
          </>
        ) : null}

        {differ && measured ? (
          <>
            {reward ? (
              <Notice tone="success">
                {say(line.billedQuantity)} charged, {say(freeQuantity(line))} free.{' '}
                {say(line.actualQuantity)} leave
                the warehouse and the cost covers all of them; the free units add nothing to the
                amount and do not deduct from it either.
              </Notice>
            ) : (
              <Notice tone="warning">
                {say(line.billedQuantity)} charged, {say(line.actualQuantity)} leave the
                warehouse — {say(short)}{' '}
                short. The customer is billed for more than is dispatched, so the reason is what
                the difference is checked against.
              </Notice>
            )}
            <Select
              disabled={locked}
              label="Why the quantities differ"
              value={line.quantityReason}
              /* Only the reasons that explain this direction: a short supply is not offered where
               * more leave than are billed, nor a bonus where fewer do. */
              options={[
                { value: '', label: 'Choose a reason' },
                ...reasons.map((reason) => ({ value: reason.label, label: reason.label })),
              ]}
              error={at('quantityReason')}
              onChange={(quantityReason) => onPatch({ quantityReason })}
            />
          </>
        ) : null}

        {isAvailable(policy.components.lineDiscount) ? (
          <SegmentedControl
            disabled={locked}
            label="Discount is"
            showLabel
            /* Which of the two is the *input*. The calculation contract forbids accepting a
             * percentage and an amount as two authorities for one benefit. */
            value={line.discountKind}
            options={[
              { value: 'PERCENT', label: 'A percentage' },
              { value: 'AMOUNT', label: 'An amount' },
            ]}
            /* The figure goes with the kind: 10% switched to an amount silently became ₹10. */
            onChange={(discountKind) =>
              onPatch({ discountKind: discountKind as DraftLine['discountKind'], discountInput: '' })
            }
          />
        ) : null}

        {free && isAvailable(policy.quantities.freeItem) ? (
          <Select
            disabled={locked}
            label="Why this line is free"
            /* Zero consideration is a declared purpose, never the accident of a blank rate. */
            hint="A sample, gift or replacement has its own tax purpose; the service applies it."
            value={line.freePurpose}
            options={[
              { value: '', label: 'Choose a purpose' },
              ...policy.quantities.freePurposes.map((purpose) => ({ value: purpose, label: purpose })),
            ]}
            error={at('freePurpose')}
            onChange={(freePurpose) => onPatch({ freePurpose })}
          />
        ) : null}

        {line.rateSource === 'MANUAL' && line.resolvedRate !== '' ? (
          <TextField
            disabled={locked}
            label="Why this rate differs from the price list"
            hint={`The list price is ${money(line.resolvedRate, { display: 'none' })}.`}
            value={line.rateReason}
            maxLength={200}
            error={at('rateReason')}
            onChange={(event) => onPatch({ rateReason: event.target.value })}
          />
        ) : null}

        <TextField

          disabled={locked}
          label="Note"
          hint="Kept with the line. Not printed unless the template asks for it."
          value={line.note}
          maxLength={500}
          onChange={(event) => onPatch({ note: event.target.value })}
        />
      </div>
    </Drawer>
  );
}
