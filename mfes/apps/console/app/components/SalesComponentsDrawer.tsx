'use client';

import {
  AmountField,
  Button,
  Checkbox,
  Drawer,
  Notice,
  SectionHeader,
  SegmentedControl,
  Select,
  TextField,
} from '@janso/ui';
import { isAvailable, type SalesEntryPolicy } from '../lib/sales-entry-policy';
import {
  CHARGE_LABELS,
  inSentence,
  isBlank,
  type DraftAction,
  type DraftCharge,
  type DraftDiscount,
  type DraftProblem,
  type SalesDraft,
} from '../lib/sales-entry-draft';

/**
 * Discounts above the line, and charges.
 *
 * One drawer for the two because they are the same kind of thing to the platform: shared
 * CHARGE/ADJUSTMENT components with a purpose, an input and a set of targets (calculation §4).
 * A *line* discount is not here — it is entered on its line, where it belongs, and appears in
 * the rail's discount figure from there.
 *
 * What this deliberately does **not** offer:
 *
 *  - **A second document discount.** Two "bill discounts" are two authorities for one benefit,
 *    which the contract does not accept. Stacked stages are the published stacking rules' job.
 *  - **Tax switches on a charge.** Whether freight is part of a supply's assessable value is a
 *    tax-profile result, resolved — not a checkbox a reader flips. The drawer says so.
 *  - **A free-typed total.** Nothing here sets an amount the rail then shows; the rail shows what
 *    the stages produce.
 */

const CHARGE_PURPOSES = (Object.keys(CHARGE_LABELS) as DraftCharge['purpose'][]).map((purpose) => ({
  value: purpose,
  label: CHARGE_LABELS[purpose],
}));

export function SalesComponentsDrawer({
  draft,
  policy,
  problems,
  dispatch,
  onUnstorable,
  onClose,
}: {
  draft: SalesDraft;
  policy: SalesEntryPolicy;
  problems: readonly DraftProblem[];
  dispatch: (action: DraftAction) => void;
  /**
   * A figure field holding text that cannot be stored, by its problem field — so the page can
   * refuse to save a value the reader cannot see. See `NumericInputOptions.onUnstorable`.
   */
  onUnstorable?: (field: string, problem: string | null) => void;
  onClose: () => void;
}) {
  const at = (key: string, field: string) =>
    problems.find((problem) => problem.lineKey === null && problem.field === `${key}.${field}`);
  const documentDiscount = draft.discounts.find((entry) => entry.scope === 'DOCUMENT');
  const selected = draft.discounts.filter((entry) => entry.scope === 'SELECTED');
  const lines = draft.lines
    .map((line, index) => ({ line, ordinal: index + 1 }))
    .filter(({ line }) => !isBlank(line));

  return (
    <Drawer open title="Discounts and charges" size="md" onClose={onClose}>
      <div className="janso-entry__panel">
        <SectionHeader
          title="Bill discount"
          description="On every line, after line and selected-line discounts. One per bill."
        />
        {!isAvailable(policy.components.documentDiscount) ? (
          <Notice>{policy.components.documentDiscount.reason}</Notice>
        ) : documentDiscount ? (
          <DiscountEditor
            discount={documentDiscount}
            problem={at(documentDiscount.key, 'input')}
            dispatch={dispatch}
            {...(onUnstorable ? { onUnstorable } : {})}
          />
        ) : (
          <Button variant="ghost" onClick={() => dispatch({ type: 'addDiscount', scope: 'DOCUMENT' })}>
            Add a bill discount
          </Button>
        )}

        <SectionHeader
          title="Discount on selected lines"
          description="On the lines you choose, before the bill discount."
        />
        {!isAvailable(policy.components.selectedLineDiscount) ? (
          <Notice>{policy.components.selectedLineDiscount.reason}</Notice>
        ) : (
          <>
            {selected.map((discount) => (
              <div key={discount.key} className="janso-flow">
                <DiscountEditor
                  discount={discount}
                  problem={at(discount.key, 'input')}
                  dispatch={dispatch}
                  {...(onUnstorable ? { onUnstorable } : {})}
                />
                {lines.length === 0 ? (
                  <Notice>Add a line first — there is nothing to choose yet.</Notice>
                ) : (
                  <fieldset className="janso-flow">
                    <legend className="janso-entry__number-note">Applies to</legend>
                    {lines.map(({ line, ordinal }) => (
                      <Checkbox
                        key={line.key}
                        checked={discount.lineKeys.includes(line.key)}
                        onChange={(event) =>
                          dispatch({
                            type: 'discount',
                            key: discount.key,
                            patch: {
                              lineKeys: event.target.checked
                                ? [...discount.lineKeys, line.key]
                                : discount.lineKeys.filter((key) => key !== line.key),
                            },
                          })
                        }
                      >
                        {`Line ${ordinal}${line.subjectLabel ? ` · ${line.subjectLabel}` : ''}`}
                      </Checkbox>
                    ))}
                    {at(discount.key, 'lineKeys') ? (
                      <p className="janso-error" role="alert">
                        {at(discount.key, 'lineKeys')!.message}
                      </p>
                    ) : null}
                  </fieldset>
                )}
              </div>
            ))}
            <Button variant="ghost" onClick={() => dispatch({ type: 'addDiscount', scope: 'SELECTED' })}>
              Add a discount on selected lines
            </Button>
          </>
        )}

        <SectionHeader title="Charges" description="Freight, packing, insurance or handling." />
        {!isAvailable(policy.components.charges) ? (
          <Notice>{policy.components.charges.reason}</Notice>
        ) : (
          <>
            {draft.charges.map((charge) => (
              <div key={charge.key} className="janso-form-grid">
                <Select
                  label="Charge"
                  value={charge.purpose}
                  options={CHARGE_PURPOSES}
                  onChange={(purpose) =>
                    dispatch({
                      type: 'charge',
                      key: charge.key,
                      patch: { purpose: purpose as DraftCharge['purpose'] },
                    })
                  }
                />
                <AmountField
                  label={`${CHARGE_LABELS[charge.purpose]} amount`}
                  value={charge.amount}
                  error={at(charge.key, 'amount')?.message}
                  onUnstorable={(problem) => onUnstorable?.(`${charge.key}.amount`, problem)}
                  onChange={(amount) => dispatch({ type: 'charge', key: charge.key, patch: { amount } })}
                />
                <TextField
                  label="Printed as"
                  optionalNote="optional"
                  value={charge.label}
                  maxLength={80}
                  onChange={(event) =>
                    dispatch({ type: 'charge', key: charge.key, patch: { label: event.target.value } })
                  }
                />
                <Button
                  variant="ghost"
                  aria-label={`Remove ${inSentence(CHARGE_LABELS[charge.purpose])}`}
                  onClick={() => dispatch({ type: 'removeCharge', key: charge.key })}
                >
                  Remove
                </Button>
              </div>
            ))}
            <Button variant="ghost" onClick={() => dispatch({ type: 'addCharge' })}>
              Add a charge
            </Button>
            {draft.charges.length > 0 ? (
              /* Not a switch for the reader to flip: whether a charge is taxable, apportioned into
               * the supply, or a non-tax adjustment is the tax profile's answer (calculation §4). */
              <Notice>
                Whether each charge is taxed is decided by the company&rsquo;s tax profile when the
                bill is accepted. The preview adds charges untaxed until then.
              </Notice>
            ) : null}
          </>
        )}
      </div>
    </Drawer>
  );
}

function DiscountEditor({
  discount,
  problem,
  dispatch,
  onUnstorable,
}: {
  discount: DraftDiscount;
  problem: DraftProblem | undefined;
  dispatch: (action: DraftAction) => void;
  onUnstorable?: (field: string, problem: string | null) => void;
}) {
  return (
    <div className="janso-form-grid">
      <SegmentedControl
        label="Discount is"
        showLabel
        /* Which of the two is the *input*: a percentage and an amount for the same benefit are
         * two authorities, and the contract accepts one. */
        value={discount.kind}
        options={[
          { value: 'PERCENT', label: 'A percentage' },
          { value: 'AMOUNT', label: 'An amount' },
        ]}
        onChange={(kind) =>
          // The figure goes with the kind: 10% switched to an amount would silently be ₹10.
          dispatch({ type: 'discount', key: discount.key, patch: { kind: kind as DraftDiscount['kind'], input: '' } })
        }
      />
      <AmountField
        label={discount.label}
        value={discount.input}
        unit={discount.kind === 'PERCENT' ? '%' : undefined}
        /* An approval threshold is a warning, not an error: above it the bill needs someone
         * to approve it, which the reader should know before saving rather than after. */
        error={problem?.severity === 'error' ? problem.message : undefined}
        hint={problem?.severity === 'warning' ? problem.message : undefined}
        onUnstorable={(message) => onUnstorable?.(`${discount.key}.input`, message)}
        onChange={(input) => dispatch({ type: 'discount', key: discount.key, patch: { input } })}
      />
      <Button
        variant="ghost"
        aria-label={`Remove ${inSentence(discount.label)}`}
        onClick={() => dispatch({ type: 'removeDiscount', key: discount.key })}
      >
        Remove
      </Button>
    </div>
  );
}
