'use client';

import { Badge, Checkbox, Notice, SearchSelect, SegmentedControl, Select, TextField } from '@janso/ui';
import type { SearchSelectLoader } from '@janso/ui';
import {
  isAvailable,
  isEditable,
  type EntryMode,
  type SalesEntryPolicy,
} from '../lib/sales-entry-policy';
import type { DraftAction, DraftProblem, SalesDraft } from '../lib/sales-entry-draft';

/**
 * The document bar: who, when, which series, which mode.
 *
 * **Sticky**, and that is the decision worth defending. Scrolling a fifty-line invoice must not
 * take away who you are billing — in Zoho Books and QuickBooks the header scrolls off, and
 * re-finding the customer to check it is the most common complaint about a long document.
 *
 * Each field's wrapper carries `data-entry-field`, which is how a problem in the rail takes the
 * reader to the field it is about without this component exporting refs.
 *
 * Every field here is rendered from policy, never from a list written in this file. The six
 * control properties stay separate: a field can be *available but not editable* (an automatic
 * number series), *available and required* (the customer), or *unavailable with a reason*
 * (a statutory artifact that is not released). Collapsing those into one boolean is how a form
 * hides something the API still demands.
 */

const MODE_LABELS: Record<EntryMode, string> = {
  ITEMS: 'Items',
  ACCOUNTS: 'Accounts',
  MIXED: 'Mixed',
};

export function SalesEntryHeader({
  draft,
  policy,
  problems,
  dispatch,
  loadCustomers,
  loadAddresses,
  resolveAddressState,
  priceLevels,
  canEdit = true,
}: {
  draft: SalesDraft;
  policy: SalesEntryPolicy;
  problems: readonly DraftProblem[];
  dispatch: (action: DraftAction) => void;
  loadCustomers: SearchSelectLoader;
  /** The chosen customer's addresses, for bill-to and ship-to. Absent, those fields are not offered. */
  loadAddresses?: (customerId: string) => SearchSelectLoader;
  /** An address's state — for a ship-to, the place of supply. */
  resolveAddressState?: (addressId: string) => string;
  /** The company's price levels. Absent, the fixture's list. */
  priceLevels?: readonly { value: string; label: string }[];
  /** False for a reader who may look but not change the bill: every field is then read-only. */
  canEdit?: boolean;
}) {
  const problemFor = (field: string) =>
    problems.find((problem) => problem.lineKey === null && problem.field === field);
  const errorFor = (field: string) =>
    problemFor(field)?.severity === 'error' ? problemFor(field)!.message : undefined;
  const warningFor = (field: string) =>
    problemFor(field)?.severity === 'warning' ? problemFor(field)!.message : undefined;
  /* Every warning about the customer — a credit limit and an overdue balance are two facts. */
  const customerWarnings = problems.filter(
    (problem) => problem.lineKey === null && problem.field === 'customerId' && problem.severity === 'warning',
  );
  const addresses = draft.customerId && loadAddresses ? loadAddresses(draft.customerId) : null;
  const party =
    (isAvailable(policy.party.billTo) || isAvailable(policy.party.shipTo) || isAvailable(policy.dates.supplyDate)) &&
    loadAddresses !== undefined;
  // The same order the preview uses for goods: ship-to, then bill-to, then the customer.
  const supplyState = draft.shipToState || draft.billToState || draft.customerState;
  const supplyFrom = draft.shipToState
    ? 'the ship-to address'
    : draft.billToState
      ? 'the bill-to address'
      : draft.customerState
        ? 'the customer'
        : null;

  return (
    <>
      <header className="janso-entry__bar" aria-label="Invoice details">
        <div className="janso-entry__bar-row janso-entry__bar-row--identity">
          <span className="janso-entry__bar-identity">
            <span className="janso-entry__number">
              {policy.numbering.preview ?? 'Number on issue'}
            </span>
            <span className="janso-entry__number-note">
              {/* A preview is provisional and reserves nothing — the allocator runs under a lock
                * at issue. Saying so here stops anyone quoting this number to a customer. */}
              {policy.numbering.mode === 'MANUAL'
                ? 'You will enter the number when this is issued.'
                : 'Provisional. The number is allocated when the invoice is issued.'}
            </span>
          </span>

          {policy.modes.allowed.length > 1 ? (
            <span className="janso-entry__bar-field janso-entry__mode">
              <SegmentedControl
                label="Entry mode"
                value={draft.mode}
                options={policy.modes.allowed.map((mode) => ({
                  value: mode,
                  label: MODE_LABELS[mode],
                }))}
                disabled={!canEdit}
                onChange={(mode) => dispatch({ type: 'mode', mode: mode as EntryMode })}
              />
            </span>
          ) : null}
        </div>

        <div className="janso-entry__bar-row">
          {isAvailable(policy.party.customer) ? (
            <span className="janso-entry__bar-field janso-entry__bar-field--party" data-entry-field="customerId">
              <SearchSelect
                label="Customer"
                value={draft.customerId}
                /* The draft already holds the chosen label, so a first paint names the customer
                 * without this control fetching to find out what it already knows. */
                selected={
                  draft.customerId
                    ? { id: draft.customerId, label: draft.customerLabel }
                    : null
                }
                loadOptions={loadCustomers}
                required={policy.party.customer.required}
                error={errorFor('customerId')}
                disabled={!canEdit || !policy.party.customer.editable}
                onChange={(id, option) =>
                  dispatch({
                    type: 'header',
                    patch: { customerId: id, customerLabel: option?.label ?? '' },
                  })
                }
              />
            </span>
          ) : (
            <Notice tone="warning">{policy.party.customer.reason}</Notice>
          )}

          {isAvailable(policy.dates.documentDate) ? (
            <span className="janso-entry__bar-field" data-entry-field="documentDate">
              <TextField
                label="Invoice date"
                type="date"
                value={draft.documentDate}
                error={errorFor('documentDate')}
                disabled={!canEdit || !policy.dates.documentDate.editable}
                onChange={(event) =>
                  dispatch({ type: 'header', patch: { documentDate: event.target.value } })
                }
              />
            </span>
          ) : null}

          {isAvailable(policy.dates.postingDate) ? (
            <span className="janso-entry__bar-field" data-entry-field="postingDate">
              <TextField
                label="Posting date"
                type="date"
                /* Its own field, never inferred from the invoice date: the posting date is what
                 * decides the period, and a late invoice posts into the open one (CLAUDE.md §6.4). */
                hint="Decides the accounting period."
                value={draft.postingDate}
                error={errorFor('postingDate')}
                disabled={!canEdit || !policy.dates.postingDate.editable}
                onChange={(event) =>
                  dispatch({ type: 'header', patch: { postingDate: event.target.value } })
                }
              />
            </span>
          ) : null}

          {isEditable(policy.pricing.priceLevel) ? (
            <span className="janso-entry__bar-field">
              <Select
                label="Price level"
                value={draft.priceLevel}
                disabled={!canEdit}
                options={[
                  { value: '', label: 'Catalog price' },
                  ...(priceLevels ?? [
                    { value: 'Retail', label: 'Retail' },
                    { value: 'Wholesale', label: 'Wholesale' },
                  ]),
                ]}
                onChange={(priceLevel) => dispatch({ type: 'header', patch: { priceLevel } })}
              />
            </span>
          ) : null}

          {isEditable(policy.pricing.taxInclusiveEntry) ? (
            <span className="janso-entry__bar-field janso-entry__bar-field--check">
              {/* A checkbox with its question beside it. The designer's switch carried only an
                * accessible name — on a form it was a bare pill nobody could read. */}
              <Checkbox
                checked={draft.taxInclusive}
                disabled={!canEdit}
                onChange={(event) =>
                  dispatch({ type: 'header', patch: { taxInclusive: event.target.checked } })
                }
              >
                Rates include tax
              </Checkbox>
            </span>
          ) : null}

          {isEditable(policy.settlement.credit) ? (
            <span className="janso-entry__bar-field janso-entry__bar-field--narrow" data-entry-field="creditDays">
              <TextField
                label="Credit days"
                inputMode="numeric"
                value={draft.creditDays}
                error={errorFor('creditDays')}
                disabled={!canEdit}
                onChange={(event) =>
                  dispatch({ type: 'header', patch: { creditDays: event.target.value } })
                }
              />
            </span>
          ) : null}
        </div>

        {warningFor('postingDate') ? (
          <Notice tone="warning">{warningFor('postingDate')}</Notice>
        ) : null}

      </header>

      {customerWarnings.map((warning) => (
        <Notice key={warning.message} tone="warning">
          {warning.message}
        </Notice>
      ))}

      {/* Who is billed, where it goes and when it was supplied. Read once, so under the sticky
        * band rather than in it; the place of supply it decides is said in words, because it is
        * what splits the tax into CGST + SGST or IGST. */}
      {party ? (
        <section className="janso-entry__party" aria-label="Billing and shipping">
          {isAvailable(policy.party.billTo) ? (
            <span className="janso-entry__bar-field" data-entry-field="billToId">
              <SearchSelect
                label="Bill to"
                hint="Left empty, the customer's registered address."
                value={draft.billToId}
                selected={draft.billToId ? { id: draft.billToId, label: draft.billToLabel } : null}
                scopeKey={draft.customerId ?? 'none'}
                minQueryLength={0}
                {...(addresses ? { loadOptions: addresses } : { options: [] })}
                disabled={!canEdit || !draft.customerId || !policy.party.billTo.editable}
                placeholder={draft.customerId ? 'Registered address' : 'Choose the customer first'}
                onChange={(id, option) =>
                  dispatch({
                  type: 'header',
                  patch: {
                    billToId: id,
                    billToLabel: option?.label ?? '',
                    billToState: id ? (resolveAddressState?.(id) ?? '') : '',
                  },
                })
                }
              />
            </span>
          ) : null}
          {isAvailable(policy.party.shipTo) ? (
            <span className="janso-entry__bar-field" data-entry-field="shipToId">
              <SearchSelect
                label="Ship to"
                hint="Left empty, the bill-to address."
                value={draft.shipToId}
                selected={draft.shipToId ? { id: draft.shipToId, label: draft.shipToLabel } : null}
                scopeKey={draft.customerId ?? 'none'}
                minQueryLength={0}
                {...(addresses ? { loadOptions: addresses } : { options: [] })}
                disabled={!canEdit || !draft.customerId || !policy.party.shipTo.editable}
                placeholder={draft.customerId ? 'Same as bill-to' : 'Choose the customer first'}
                onChange={(id, option) =>
                  dispatch({
                    type: 'header',
                    patch: {
                      shipToId: id,
                      shipToLabel: option?.label ?? '',
                      shipToState: id ? (resolveAddressState?.(id) ?? '') : '',
                    },
                  })
                }
              />
            </span>
          ) : null}
          {isAvailable(policy.dates.supplyDate) ? (
            <span className="janso-entry__bar-field" data-entry-field="supplyDate">
              <TextField
                label="Supply date"
                type="date"
                optionalNote="optional"
                hint="When the goods left or the service was done, if not on the invoice date."
                value={draft.supplyDate}
                disabled={!canEdit || !policy.dates.supplyDate.editable}
                onChange={(event) => dispatch({ type: 'header', patch: { supplyDate: event.target.value } })}
              />
            </span>
          ) : null}
          <p className="janso-entry__supply">
            {supplyFrom
              ? `Place of supply: ${supplyState}, from ${supplyFrom}.`
              : 'Place of supply: known once the customer is chosen.'}
          </p>
        </section>
      ) : null}

      {/* What a reader cannot do here, and why. A mechanic that is simply missing reads as a
        * bug; one that says why reads as a decision. Outside the bar: it is read once, and inside
        * it took a row of the sticky band away from the lines on every scroll. */}
      {!isAvailable(policy.statutory.eInvoice) ? (
        <p className="janso-entry__number-note">
          <Badge tone="neutral">Not available</Badge> {policy.statutory.eInvoice.reason}
        </p>
      ) : null}
    </>
  );
}
