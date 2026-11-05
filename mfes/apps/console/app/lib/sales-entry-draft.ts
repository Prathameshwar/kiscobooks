import type { EntryMode, SalesEntryPolicy, TenderMode } from './sales-entry-policy';
import { isAvailable } from './sales-entry-policy';
import * as D from './fixed-decimal';

/**
 * The draft a creation page accumulates, and the only thing that changes it.
 *
 * Pure and reducer-shaped, like the designer's `history.ts` and `publication.ts`, for the same
 * reasons: none of it needs a rendered component to test, the rules can be read in one file
 * rather than inferred from six components, and when the service arrives this moves behind its
 * API unchanged.
 *
 * **Every amount and quantity here is a `string`.** Money is `DECIMAL(19,4)` (CLAUDE.md §4) and
 * a float round-trip silently re-scales it; `0.1 + 0.2` is the canonical demonstration and an
 * invoice total is the worst place to meet it. Arithmetic is the service's job — this file
 * stores what was typed and never adds two of them up.
 */

/** One entered line. `null` means "not supplied", which is different from `"0"`. */
export type DraftLine = {
  readonly key: string;
  /** The chosen SKU or account, by id. The label is a lookup concern, not draft state. */
  readonly subjectId: string | null;
  readonly subjectLabel: string;
  /**
   * Whether the subject is an item or an account — fixed when it is chosen, by the lookup it
   * was chosen from. Switching mode keeps the lines (see `reduceDraft`), so this is how a line
   * whose subject no longer fits the mode is *found*, rather than silently repriced.
   */
  readonly subjectKind: 'ITEM' | 'ACCOUNT' | null;
  /**
   * Goods or a service, from the item master. Only goods move stock, so only a goods line is
   * held to a stock intent that moves something — and a service is never offered one.
   */
  readonly subjectNature: 'GOODS' | 'SERVICE' | null;
  readonly description: string;
  readonly hsnSac: string;
  /** What physically moves. Equal to billed unless a reward or variance says otherwise. */
  readonly actualQuantity: string;
  /** What the customer pays for. The consideration basis. */
  readonly billedQuantity: string;
  readonly unit: string;
  readonly rate: string;
  /**
   * What the price source supplied for this line, if anything did. Empty when no price book,
   * tier or history produced one.
   *
   * Kept beside `rate` because **an override is a departure from a resolved price**, not merely
   * a typed one. Without this, the first rate typed on a fresh line counted as an override and
   * every ordinary line demanded a reason — which the reducer tests caught immediately, and
   * which would have made the form unusable.
   */
  readonly resolvedRate: string;
  /** Where the *current* rate came from, so an override is visible rather than silent. */
  readonly rateSource: 'PRICE_LEVEL' | 'QUANTITY_TIER' | 'LAST_SOLD' | 'MANUAL';
  readonly rateReason: string;
  /** Normalised into a CHARGE/ADJUSTMENT component on save; the cell is only the input. */
  readonly discountInput: string;
  readonly discountKind: 'PERCENT' | 'AMOUNT';
  /** Required when actual and billed differ — a bare difference is not evidence. */
  readonly quantityReason: string;
  /**
   * Why a line carries no consideration — a sample, a gift, a replacement — from the policy's
   * list. A zero line is refused without one: zero consideration is a declared purpose, never
   * an accident of a blank rate or a 100% discount (commercial configuration §4.2).
   */
  readonly freePurpose: string;

  /* — the long tail, edited in the row drawer rather than in a column — */

  /**
   * What this line does to stock, explicitly.
   *
   * `NONE` for a service, `EXECUTE` to dispatch now, `REFERENCE_EXISTING` when a delivery note
   * already moved the goods, `DEFERRED` when billing runs ahead of fulfilment. The calculation
   * contract is emphatic that there is **no unrestricted "does not affect stock" switch** on an
   * ordinary goods line: goods billed against a challan must not move a second time, and a
   * deferred bill must not fabricate a movement that has not happened.
   */
  readonly stockIntent: 'NONE' | 'EXECUTE' | 'REFERENCE_EXISTING' | 'DEFERRED';
  readonly warehouse: string;
  readonly batch: string;
  /** A business date, never a datetime (CLAUDE.md §4). */
  readonly expiry: string;
  /** Per-supply income ledger, where the policy does not use one common account. */
  readonly incomeLedger: string;
  readonly note: string;
  /**
   * The tax rate the resolver supplied for this supply, in percent; `''` while unresolved.
   *
   * **Resolved, never typed.** The jurisdiction adapter determines lawful base, rates and
   * components (calculation §5); there is no input for this anywhere in the form, and a line
   * whose rate is unknown previews its tax as unknown rather than as zero.
   */
  readonly taxRate: string;
};

/**
 * A discount above the line: on chosen lines, or on the whole document.
 *
 * Both normalise to the same shared CHARGE/ADJUSTMENT component on save (calculation §4) — the
 * scope is a native fact of the component, not a different mechanism. A *line* discount is not
 * here: it is entered on the line, and lives there.
 */
export type DraftDiscount = {
  readonly key: string;
  readonly scope: 'DOCUMENT' | 'SELECTED';
  readonly kind: 'PERCENT' | 'AMOUNT';
  readonly input: string;
  /** The lines a `SELECTED` discount targets. Ignored for `DOCUMENT`, which takes all. */
  readonly lineKeys: readonly string[];
  readonly label: string;
};

/**
 * A charge on the document: freight, packing, insurance, handling.
 *
 * Commercial, tax and inventory treatment are three separate policy results (calculation §4),
 * resolved by the service — not three switches a reader flips. So the draft holds what was
 * charged and why, and nothing about how it is taxed.
 */
export type DraftCharge = {
  readonly key: string;
  readonly purpose: 'FREIGHT' | 'PACKING' | 'INSURANCE' | 'HANDLING' | 'OTHER';
  readonly amount: string;
  readonly label: string;
};

/**
 * Money received at the point of billing.
 *
 * Mode, amount and reference are separate native facts (data model §4). A UTR or a cheque number
 * is a *reference*, not an idempotency key and not proof of settlement. **No card number is ever
 * held** — a card tender carries the gateway's approval code and nothing more (CLAUDE.md §5.10).
 */
export type DraftTender = {
  readonly key: string;
  readonly mode: TenderMode;
  readonly amount: string;
  readonly reference: string;
  /** A business date: when the instrument is dated, which for a cheque is not when it clears. */
  readonly instrumentDate: string;
  /** The drawee bank, for a cheque. A name as written on it, not an account number. */
  readonly bank: string;
};

/**
 * An existing advance applied to this bill.
 *
 * It points at an open credit Accounting already holds — **it is not another receipt**, and
 * applying it creates no new money (data model §4). `available` is a projection of the source's
 * unallocated balance; Accounting locks and checks the authoritative one at acceptance.
 */
export type DraftAdvance = {
  readonly key: string;
  readonly sourceId: string;
  readonly sourceLabel: string;
  readonly available: string;
  readonly amount: string;
};

export type SalesDraft = {
  readonly mode: EntryMode;
  readonly customerId: string | null;
  readonly customerLabel: string;
  readonly billToId: string | null;
  readonly billToLabel: string;
  /** The bill-to address's state: the place of supply for services, and for goods with no ship-to. */
  readonly billToState: string;
  readonly shipToId: string | null;
  readonly shipToLabel: string;
  /**
   * The ship-to address's state. For goods it is the place of supply, which — not the
   * customer's registered state — decides CGST + SGST against IGST. Empty when no ship-to was
   * chosen, and the customer's state stands.
   */
  readonly shipToState: string;
  readonly documentDate: string;
  readonly postingDate: string;
  readonly supplyDate: string;
  readonly priceLevel: string;
  readonly taxInclusive: boolean;
  readonly creditDays: string;
  readonly lines: readonly DraftLine[];
  readonly discounts: readonly DraftDiscount[];
  readonly charges: readonly DraftCharge[];
  readonly tenders: readonly DraftTender[];
  readonly advances: readonly DraftAdvance[];
  /**
   * The customer's state, from the party master. For India GST it decides whether a supply is
   * intra-state (CGST + SGST) or inter-state (IGST) — a fact about the party, carried on the
   * draft so the preview can split tax without a second lookup.
   */
  readonly customerState: string;
  /**
   * The customer's credit position, as the party master projects it: the limit, what is already
   * owed, and how much of that is overdue. A projection for a warning — Accounting holds the
   * ledger, and a limit is enforced (or not) by the service.
   */
  readonly customerCredit: CustomerCredit | null;
  /** Bumped on every accepted change, so "nothing entered yet" is answerable. */
  readonly revision: number;
};

export type CustomerCredit = {
  /** `''` when the customer has no limit. */
  readonly limit: string;
  readonly outstanding: string;
  readonly overdue: string;
};

let sequence = 0;
/** A stable key per row. Not an id — the service assigns those. */
function nextKey(): string {
  sequence += 1;
  return `line-${sequence}`;
}

/**
 * The first line's key, fixed rather than counted.
 *
 * `initialDraft` runs during the server render too, where the module counter keeps rising across
 * requests: the server painted `line-7` while the client's first line was `line-1`. React does not
 * repair an attribute mismatch on hydration, so the grid read a row key from the DOM that its own
 * rows did not have, and Tab, Enter and "go to line 1" stopped working. Every later key comes from
 * a reader's action, which only ever happens in the browser, so the counter is safe for those.
 */
export const FIRST_LINE_KEY = 'line-0';

export function emptyLine(key: string = nextKey()): DraftLine {
  return {
    key,
    subjectId: null,
    subjectLabel: '',
    subjectKind: null,
    subjectNature: null,
    description: '',
    hsnSac: '',
    actualQuantity: '',
    billedQuantity: '',
    unit: '',
    rate: '',
    resolvedRate: '',
    rateSource: 'MANUAL',
    rateReason: '',
    discountInput: '',
    discountKind: 'PERCENT',
    quantityReason: '',
    freePurpose: '',
    stockIntent: 'EXECUTE',
    warehouse: '',
    batch: '',
    expiry: '',
    incomeLedger: '',
    note: '',
    taxRate: '',
  };
}

function nextComponentKey(prefix: string): string {
  sequence += 1;
  return `${prefix}-${sequence}`;
}

export function emptyDiscount(scope: DraftDiscount['scope']): DraftDiscount {
  return {
    key: nextComponentKey('discount'),
    scope,
    kind: 'PERCENT',
    input: '',
    lineKeys: [],
    label: scope === 'DOCUMENT' ? 'Bill discount' : 'Discount on selected lines',
  };
}

export function emptyCharge(purpose: DraftCharge['purpose'] = 'FREIGHT'): DraftCharge {
  return { key: nextComponentKey('charge'), purpose, amount: '', label: '' };
}

/**
 * The draft a form opens on.
 *
 * Defaults come from policy rather than from this file. A class may default a permitted value,
 * and a form that hardcoded its own would quietly disagree with the envelope it is bound to.
 */
export function initialDraft(policy: SalesEntryPolicy, today: string): SalesDraft {
  const fallback = <T,>(control: { available: boolean }, value: T | undefined, last: T): T =>
    control.available && value !== undefined ? value : last;
  return {
    mode: policy.modes.default,
    customerId: null,
    customerLabel: '',
    billToId: null,
    billToLabel: '',
    billToState: '',
    shipToId: null,
    shipToLabel: '',
    shipToState: '',
    documentDate: fallback(policy.dates.documentDate, undefined, today),
    // The same day by default, and a *separate* field on purpose: the posting date determines
    // the period and is never inferred from the document date (CLAUDE.md §6.4).
    postingDate: fallback(policy.dates.postingDate, undefined, today),
    supplyDate: '',
    priceLevel: isAvailable(policy.pricing.priceLevel)
      ? (policy.pricing.priceLevel.default ?? '')
      : '',
    taxInclusive: isAvailable(policy.pricing.taxInclusiveEntry)
      ? (policy.pricing.taxInclusiveEntry.default ?? false)
      : false,
    creditDays: isAvailable(policy.settlement.credit) ? (policy.settlement.credit.default ?? '') : '',
    lines: [emptyLine(FIRST_LINE_KEY)],
    discounts: [],
    charges: [],
    tenders: [],
    advances: [],
    customerState: '',
    customerCredit: null,
    revision: 0,
  };
}

export type DraftAction =
  | { readonly type: 'mode'; readonly mode: EntryMode }
  | { readonly type: 'header'; readonly patch: Partial<SalesDraft> }
  | { readonly type: 'line'; readonly key: string; readonly patch: Partial<DraftLine> }
  | { readonly type: 'addLine' }
  | { readonly type: 'insertLine'; readonly after: string }
  /**
   * What a master supplied for a line, arriving after the choice: applied only if the line still
   * holds that subject, so a slow answer for the previous item cannot land on the next one.
   */
  | { readonly type: 'resolveLine'; readonly key: string; readonly subjectId: string; readonly patch: Partial<DraftLine> }
  /** The same for the customer's state and credit. */
  | { readonly type: 'resolveCustomer'; readonly customerId: string; readonly patch: Partial<SalesDraft> }
  /** Several lines at once, as one change — a re-price after the price level moved. */
  | { readonly type: 'patchLines'; readonly patches: Readonly<Record<string, Partial<DraftLine>>> }
  | { readonly type: 'removeLine'; readonly key: string }
  | { readonly type: 'duplicateLine'; readonly key: string }
  | { readonly type: 'moveLine'; readonly key: string; readonly by: -1 | 1 }
  | { readonly type: 'addDiscount'; readonly scope: DraftDiscount['scope'] }
  | { readonly type: 'discount'; readonly key: string; readonly patch: Partial<DraftDiscount> }
  | { readonly type: 'removeDiscount'; readonly key: string }
  | { readonly type: 'addCharge'; readonly purpose?: DraftCharge['purpose'] }
  | { readonly type: 'charge'; readonly key: string; readonly patch: Partial<DraftCharge> }
  | { readonly type: 'removeCharge'; readonly key: string }
  | { readonly type: 'addTender'; readonly mode: TenderMode; readonly amount?: string }
  | { readonly type: 'tender'; readonly key: string; readonly patch: Partial<DraftTender> }
  | { readonly type: 'removeTender'; readonly key: string }
  | {
      readonly type: 'applyAdvance';
      readonly sourceId: string;
      readonly sourceLabel: string;
      readonly available: string;
      /** What to apply, when the caller knows — the smaller of available and still owing. */
      readonly amount?: string;
    }
  | { readonly type: 'advance'; readonly key: string; readonly amount: string }
  | { readonly type: 'removeAdvance'; readonly key: string };

export function reduceDraft(draft: SalesDraft, action: DraftAction): SalesDraft {
  const bumped = (next: Partial<SalesDraft>): SalesDraft => ({
    ...draft,
    ...next,
    revision: draft.revision + 1,
  });
  switch (action.type) {
    case 'mode':
      /*
       * Switching mode keeps the lines. The mode changes which columns are *shown* and how the
       * draft validates — it does not select a different store (data model §4) — so discarding
       * the lines would be this form inventing a rule the platform does not have. A line whose
       * subject no longer fits the mode is reported by `draftProblems`, not deleted.
       */
      return action.mode === draft.mode ? draft : bumped({ mode: action.mode });
    case 'header':
      if ('customerId' in action.patch && action.patch.customerId !== draft.customerId) {
        // An advance belongs to the party who paid it. Changing the customer while keeping the
        // previous one's credit applied would settle this bill with someone else's money — and
        // the previous customer's addresses are not this one's either.
        return bumped({
          billToId: null,
          billToLabel: '',
          billToState: '',
          shipToId: null,
          shipToLabel: '',
          shipToState: '',
          customerCredit: null,
          ...action.patch,
          advances: [],
        });
      }
      return bumped(action.patch);
    case 'line':
      return bumped({
        lines: draft.lines.map((line) =>
          line.key === action.key ? applyLine(line, action.patch) : line,
        ),
      });
    case 'addLine':
      return bumped({ lines: [...draft.lines, emptyLine()] });
    case 'insertLine': {
      const index = draft.lines.findIndex((line) => line.key === action.after);
      if (index < 0) return bumped({ lines: [...draft.lines, emptyLine()] });
      return bumped({
        lines: [...draft.lines.slice(0, index + 1), emptyLine(), ...draft.lines.slice(index + 1)],
      });
    }
    case 'resolveLine': {
      const target = draft.lines.find((line) => line.key === action.key);
      if (!target || target.subjectId !== action.subjectId) return draft;
      return bumped({
        lines: draft.lines.map((line) => (line.key === action.key ? applyLine(line, action.patch) : line)),
      });
    }
    case 'resolveCustomer':
      return draft.customerId === action.customerId ? bumped(action.patch) : draft;
    case 'patchLines':
      // Applied as given, not through `applyLine`: a re-price sets the rate *and* its source
      // together, and the typed-rate coupling there would second-guess the source it was told.
      return bumped({
        lines: draft.lines.map((line) => {
          const patch = action.patches[line.key];
          return patch ? { ...line, ...patch } : line;
        }),
      });
    case 'removeLine':
      // Never below one row: an empty grid has nothing to type into, and "add a line" as the
      // only thing on screen is a worse empty state than one blank row.
      return draft.lines.length <= 1
        ? draft
        : bumped({
            lines: draft.lines.filter((line) => line.key !== action.key),
            // A targeted discount that still names a removed line would be an allocation to a
            // target that no longer exists — which the contract rejects. Drop the reference.
            discounts: draft.discounts.map((entry) => ({
              ...entry,
              lineKeys: entry.lineKeys.filter((key) => key !== action.key),
            })),
          });
    case 'duplicateLine': {
      const index = draft.lines.findIndex((line) => line.key === action.key);
      const source = draft.lines[index];
      if (!source) return draft;
      /*
       * A copy, with its own key — and **without the reasons**. A quantity-difference reason
       * and a rate-override reason justify *that* line; carrying them onto a duplicate would
       * let an approved exception be multiplied by pressing Ctrl+D, which is exactly the kind
       * of evidence laundering the override contract exists to prevent.
       */
      const copy: DraftLine = {
        ...source,
        key: nextKey(),
        quantityReason: '',
        rateReason: '',
        freePurpose: '',
      };
      return bumped({
        lines: [...draft.lines.slice(0, index + 1), copy, ...draft.lines.slice(index + 1)],
      });
    }
    case 'moveLine': {
      const index = draft.lines.findIndex((line) => line.key === action.key);
      const target = index + action.by;
      if (index < 0 || target < 0 || target >= draft.lines.length) return draft;
      const lines = [...draft.lines];
      const [moved] = lines.splice(index, 1);
      lines.splice(target, 0, moved!);
      /*
       * Order is presentation. The calculation contract says document row order alone cannot
       * change a result — component stages and eligible bases decide that — so moving a line
       * re-reads the document, never re-prices it.
       */
      return bumped({ lines });
    }
    case 'addDiscount':
      // One document discount at a time: two "bill discounts" would be two authorities for the
      // same benefit, which the calculation contract does not accept. Stacked stages belong to
      // the published stacking rules, not to a second row typed by hand.
      if (action.scope === 'DOCUMENT' && draft.discounts.some((entry) => entry.scope === 'DOCUMENT')) {
        return draft;
      }
      return bumped({ discounts: [...draft.discounts, emptyDiscount(action.scope)] });
    case 'discount':
      return bumped({
        discounts: draft.discounts.map((entry) =>
          entry.key === action.key ? { ...entry, ...action.patch } : entry,
        ),
      });
    case 'removeDiscount':
      return bumped({ discounts: draft.discounts.filter((entry) => entry.key !== action.key) });
    case 'addCharge':
      return bumped({ charges: [...draft.charges, emptyCharge(action.purpose)] });
    case 'charge':
      return bumped({
        charges: draft.charges.map((entry) =>
          entry.key === action.key ? { ...entry, ...action.patch } : entry,
        ),
      });
    case 'removeCharge':
      return bumped({ charges: draft.charges.filter((entry) => entry.key !== action.key) });
    case 'addTender':
      return bumped({
        tenders: [
          ...draft.tenders,
          {
            key: nextComponentKey('tender'),
            mode: action.mode,
            amount: action.amount ?? '',
            reference: '',
            instrumentDate: '',
            bank: '',
          },
        ],
      });
    case 'tender':
      return bumped({
        tenders: draft.tenders.map((entry) => {
          if (entry.key !== action.key) return entry;
          /*
           * A reference belongs to its mode — a UTR is not an approval code — so changing the
           * mode clears it. That is also what stops a card number typed under Card, refused,
           * and then kept by switching the mode to Cash.
           */
          const modeChanged = action.patch.mode !== undefined && action.patch.mode !== entry.mode;
          return { ...entry, ...(modeChanged ? { reference: '' } : {}), ...action.patch };
        }),
      });
    case 'removeTender':
      return bumped({ tenders: draft.tenders.filter((entry) => entry.key !== action.key) });
    case 'applyAdvance':
      // One application per source: applying the same advance twice is how one credit gets
      // spent twice, which Accounting's lock exists to stop and this should not invite.
      if (draft.advances.some((entry) => entry.sourceId === action.sourceId)) return draft;
      return bumped({
        advances: [
          ...draft.advances,
          {
            key: nextComponentKey('advance'),
            sourceId: action.sourceId,
            sourceLabel: action.sourceLabel,
            available: action.available,
            amount: action.amount ?? '',
          },
        ],
      });
    case 'advance':
      return bumped({
        advances: draft.advances.map((entry) =>
          entry.key === action.key ? { ...entry, amount: action.amount } : entry,
        ),
      });
    case 'removeAdvance':
      return bumped({ advances: draft.advances.filter((entry) => entry.key !== action.key) });
    default:
      return draft;
  }
}

/**
 * One patch to one line, with the two couplings a reader expects and nothing else.
 *
 * Billed quantity follows actual while they agree, so the ordinary case stays one keystroke
 * per row; once they differ, the difference is deliberate and is left alone. Typing a rate
 * marks it `MANUAL`, because an override that does not look like one is the whole problem.
 */
function applyLine(line: DraftLine, patch: Partial<DraftLine>): DraftLine {
  const next = { ...line, ...patch };
  if (patch.actualQuantity !== undefined && patch.billedQuantity === undefined) {
    if (line.actualQuantity === line.billedQuantity) {
      return { ...next, billedQuantity: patch.actualQuantity };
    }
  }
  if (patch.rate !== undefined && line.freePurpose && D.parse(patch.rate.trim()) !== D.ZERO) {
    // A purpose declares a *free* line. Once it has a price it is not free, and a stale purpose
    // would go on flagging it "Free" in the preview.
    return applyLine({ ...line, freePurpose: '' }, patch);
  }
  if (patch.rate !== undefined && patch.rateSource === undefined && patch.rate !== line.rate) {
    // Back to the resolved figure is not an override any more, so the badge goes quiet again
    // and the reason stops being required. Typing the same number the catalog offered should
    // not leave a line looking amended.
    // Compared as decimals: `2450.00` is the list price of 2450, not a departure from it.
    const source =
      line.resolvedRate !== '' && sameAmount(patch.rate, line.resolvedRate) ? 'PRICE_LEVEL' : 'MANUAL';
    return { ...next, rateSource: source };
  }
  return next;
}

/** Two amounts as decimals: `2450` and `2450.00` are one figure. Text that is not one is not. */
export function sameAmount(a: string, b: string): boolean {
  const left = D.parse(a.trim());
  const right = D.parse(b.trim());
  return left !== null && right !== null && left === right;
}

/**
 * Whether a line is an account line — priced as one amount, with no quantity and no stock.
 * Every line on an accounts-only bill is; on a mixed bill, the lines whose subject is an account.
 */
export function isAccountLine(draft: Pick<SalesDraft, 'mode'>, line: DraftLine): boolean {
  return draft.mode === 'ACCOUNTS' || (draft.mode === 'MIXED' && line.subjectKind === 'ACCOUNT');
}

/** Whether a line is goods, so it moves stock: an item the master did not call a service. */
export function isGoodsLine(draft: Pick<SalesDraft, 'mode'>, line: DraftLine): boolean {
  return !isAccountLine(draft, line) && line.subjectNature !== 'SERVICE';
}

/** Which way actual and billed differ, or `null` when they do not or cannot be compared. */
export function differenceDirection(line: DraftLine): 'MORE' | 'LESS' | null {
  const actual = D.parse(line.actualQuantity.trim());
  const billed = D.parse(line.billedQuantity.trim());
  if (actual === null || billed === null || actual === billed) return null;
  return actual > billed ? 'MORE' : 'LESS';
}

/** Options a caller can pass so a check that needs the reader's grants can make it. */
export type ProblemOptions = {
  /** Whether the reader holds a permission key. Presentation only — the service decides. */
  readonly granted?: (key: string) => boolean;
  /** The company's money and date formatters, for figures and dates quoted in a sentence. */
  readonly formatMoney?: (value: string) => string;
  readonly formatDate?: (iso: string) => string;
};

/* ------------------------------------------------------------------ what is wrong with it */

export type DraftProblem = {
  readonly severity: 'error' | 'warning';
  /** The line this is about, or `null` for the document. */
  readonly lineKey: string | null;
  readonly field: string;
  readonly message: string;
};

/** Whether a row has been touched at all. A blank trailing row is not an error. */
export function isBlank(line: DraftLine): boolean {
  return (
    !line.subjectId &&
    !line.description.trim() &&
    !line.actualQuantity.trim() &&
    !line.billedQuantity.trim() &&
    !line.rate.trim()
  );
}

const DECIMAL = /^\d{1,15}(\.\d{1,4})?$/;

/**
 * Whether a line's actual and billed quantities are different amounts — compared as decimals,
 * so `10` and `10.0` are the same quantity and owe no reason. Either side missing or not a
 * number is not a difference: that line has a different problem.
 */
export function quantitiesDiffer(line: DraftLine): boolean {
  const actual = D.parse(line.actualQuantity.trim());
  const billed = D.parse(line.billedQuantity.trim());
  return actual !== null && billed !== null && actual !== billed;
}

/** A positive decimal within the platform's four-place storage scale. */
export function isQuantity(value: string): boolean {
  return DECIMAL.test(value.trim()) && Number(value) > 0;
}

/** Zero is a legitimate rate — a reward unit has one — so this allows it. */
export function isAmount(value: string): boolean {
  return DECIMAL.test(value.trim());
}

/**
 * Everything wrong with the draft, as the form would say it.
 *
 * Client-side and advisory: the service validates all of this again, and the hard rules
 * (taxability, stock admission, period state) are its alone. What this buys is telling a
 * reader before a round trip rather than after one — nothing here is a security boundary.
 */
export function draftProblems(
  draft: SalesDraft,
  policy: SalesEntryPolicy,
  options: ProblemOptions = {},
): readonly DraftProblem[] {
  const problems: DraftProblem[] = [];
  const doc = (field: string, message: string, severity: DraftProblem['severity'] = 'error') =>
    problems.push({ severity, lineKey: null, field, message });
  /* Figures and dates in a sentence, the way the company writes them. */
  const money = (value: string) => options.formatMoney?.(value) ?? value;
  const day = (iso: string) => options.formatDate?.(iso) ?? iso;

  if (policy.party.customer.available && policy.party.customer.required && !draft.customerId) {
    doc('customerId', 'Choose the customer this is billed to.');
  }
  if (!draft.documentDate) doc('documentDate', 'A document date is required.');
  if (!draft.postingDate) doc('postingDate', 'A posting date is required.');
  if (draft.postingDate && draft.documentDate && draft.postingDate < draft.documentDate) {
    // A warning, not an error: a late posting is legitimate and the open period decides. The
    // service owns `assert_postable`; this only says "did you mean that?".
    doc('postingDate', 'The posting date is before the document date.', 'warning');
  }

  const entered = draft.lines.filter((line) => !isBlank(line));
  if (entered.length === 0) doc('lines', 'Add at least one line.');

  for (const line of entered) {
    const at = (field: string, message: string, severity: DraftProblem['severity'] = 'error') =>
      problems.push({ severity, lineKey: line.key, field, message });

    if (!line.subjectId) {
      at(
        'subjectId',
        draft.mode === 'ACCOUNTS' ? 'Choose an account.' : draft.mode === 'MIXED' ? 'Choose an item or an account.' : 'Choose an item.',
      );
    } else if (draft.mode === 'ACCOUNTS' && line.subjectKind === 'ITEM') {
      // Switching mode keeps the line; it must not keep it *quietly*. An item on an
      // accounts-only bill would be priced as one unit and move no stock.
      at('subjectId', 'This line is an item, and an accounts-only bill takes accounts. Choose an account, or switch back to Items.');
    } else if (draft.mode === 'ITEMS' && line.subjectKind === 'ACCOUNT') {
      at('subjectId', 'This line is an account, and an items bill takes items. Choose an item, or switch to Accounts or Mixed.');
    }
    if (isGoodsLine(draft, line) && line.stockIntent === 'NONE') {
      // No unrestricted "does not affect stock" switch on a goods line (calculation contract):
      // goods billed here either move now, moved already on a delivery note, or move later.
      at('stockIntent', 'Goods move stock. Choose dispatch now, already dispatched or dispatch later.');
    }
    if (!isAccountLine(draft, line)) {
      if (!isQuantity(line.billedQuantity)) at('billedQuantity', 'Enter a billed quantity.');
      if (line.actualQuantity.trim() && !isQuantity(line.actualQuantity)) {
        at('actualQuantity', 'Enter an actual quantity.');
      }
      if (quantitiesDiffer(line)) {
        const direction = differenceDirection(line);
        const reason = policy.quantities.differenceReasons.find((entry) => entry.label === line.quantityReason);
        if (!isAvailable(policy.quantities.actualVersusBilled)) {
          // Not recorded at all here, so there is no reason to ask for — one problem, not two.
        } else if (!line.quantityReason) {
          // The documented rule: an actual-versus-billed difference alone is not evidence of
          // an authorised bonus (commercial configuration §4.1).
          at('quantityReason', 'Say why the actual and billed quantities differ.');
        } else if (reason && direction && reason.applies !== 'EITHER' && reason.applies !== direction) {
          // "Short supply" on a line where more leaves than is billed is a reason for a
          // different line — accepted, it would be evidence for something that did not happen.
          at(
            'quantityReason',
            direction === 'MORE'
              ? `“${reason.label}” is for fewer leaving than are billed. Here more leave.`
              : `“${reason.label}” is for more leaving than are billed. Here fewer leave.`,
          );
        }
        if (!isAvailable(policy.quantities.actualVersusBilled)) {
          at('actualQuantity', 'This company does not record a quantity difference on a sale.');
        }
      }
    }
    if (!isAmount(line.rate)) {
      at('rate', 'Enter a rate.');
    } else if (D.parse(line.rate.trim()) === D.ZERO) {
      // Refused as a *route to free*: zero consideration is not zero taxable value or zero
      // cost, and a blank or zero rate is not a declaration of anything (§4.2). A free line is
      // allowed only where the policy allows one, and only with its purpose said.
      if (!isAvailable(policy.quantities.freeItem)) at('rate', policy.quantities.freeItem.reason);
      else if (!line.freePurpose) at('freePurpose', 'Choose why this line is free.');
    }
    /*
     * A reason is owed for **departing from a resolved price**, not for typing one. With no
     * price book, tier or history behind a line there is nothing to depart from, and demanding
     * a justification for the only rate anyone could have entered is noise that trains people
     * to type "n/a".
     */
    // A zero rate is its own problem (above); stacking an override and an approval on it says
    // the same thing three times.
    const overridden =
      line.rateSource === 'MANUAL' &&
      line.resolvedRate !== '' &&
      isAmount(line.rate) &&
      D.parse(line.rate.trim()) !== D.ZERO &&
      !sameAmount(line.rate, line.resolvedRate);
    if (overridden) {
      const control = policy.pricing.rateOverride;
      if (!isAvailable(control)) {
        // Forbidden is forbidden: the override used to pass silently when the control was off.
        at('rate', `${control.reason} The list price is ${money(line.resolvedRate)}.`);
      } else {
        const override = control.override;
        const denied = Boolean(override?.permission && options.granted && !options.granted(override.permission));
        if (denied) {
          at('rate', 'Changing the list price needs a permission you do not have. Use the list price, or ask someone who can.');
        } else if (override?.reasonRequired && !line.rateReason) {
          at('rateReason', 'Say why this rate differs from the price list.');
        }
        const list = D.parse(line.resolvedRate.trim());
        const typed = D.parse(line.rate.trim());
        // Approval is for an override that may stand; a refused one needs no approver.
        if (!denied && control.approvalAbove && list !== null && typed !== null && list > D.ZERO) {
          // How far from the list, in percent, against the policy's approval threshold.
          const gap = typed > list ? typed - list : list - typed;
          const threshold = D.parse(control.approvalAbove);
          // gap ÷ list > threshold ÷ 100, cross-multiplied so nothing is rounded on the way.
          if (threshold !== null && gap * 100n * D.ONE > list * threshold) {
            at(
              'rate',
              `This rate is more than ${control.approvalAbove}% from the list price of ${money(line.resolvedRate)} and needs approval before the bill can proceed.`,
              'warning',
            );
          }
        }
      }
    }
    if (line.discountInput.trim()) {
      if (!isAmount(line.discountInput)) at('discountInput', 'Enter a discount.');
      else if (line.discountKind === 'PERCENT' && Number(line.discountInput) > 100) {
        at('discountInput', 'A percentage discount cannot exceed 100.');
      } else if (!isAvailable(policy.components.lineDiscount)) {
        at('discountInput', policy.components.lineDiscount.reason);
      }
    }
  }
  /* — components above the line — */
  for (const discount of draft.discounts) {
    const at = (field: string, message: string) =>
      problems.push({ severity: 'error', lineKey: null, field: `${discount.key}.${field}`, message });
    const control =
      discount.scope === 'DOCUMENT'
        ? policy.components.documentDiscount
        : policy.components.selectedLineDiscount;
    if (!isAvailable(control)) {
      at('scope', control.reason);
      continue;
    }
    if (!discount.input.trim()) at('input', `Enter the ${inSentence(discount.label)}.`);
    else if (!isAmount(discount.input)) at('input', `Enter the ${inSentence(discount.label)} as a number.`);
    else if (discount.kind === 'PERCENT' && Number(discount.input) > 100) {
      at('input', 'A percentage discount cannot exceed 100.');
    } else if (
      control.approvalAbove &&
      discount.kind === 'PERCENT' &&
      (D.parse(discount.input.trim()) ?? D.ZERO) > (D.parse(control.approvalAbove) ?? D.ZERO)
    ) {
      // Above the approval threshold is not wrong — it needs someone to approve it, and the
      // reader should know that before they save rather than after. An *amount* is measured
      // on what it comes to, in the preview: a 5% threshold checked only against percentages
      // let an amount of 82% straight through.
      problems.push({
        severity: 'warning',
        lineKey: null,
        field: `${discount.key}.input`,
        message: `A ${inSentence(discount.label)} above ${control.approvalAbove}% needs approval before the bill can proceed.`,
      });
    }
    if (discount.scope === 'SELECTED') {
      // A target that exists but was emptied applies nothing, so it does not count either.
      const live = discount.lineKeys.filter((key) =>
        draft.lines.some((line) => line.key === key && !isBlank(line)),
      );
      if (live.length === 0) at('lineKeys', 'Choose the lines this discount applies to.');
    }
  }

  for (const charge of draft.charges) {
    const at = (field: string, message: string) =>
      problems.push({ severity: 'error', lineKey: null, field: `${charge.key}.${field}`, message });
    if (!isAvailable(policy.components.charges)) {
      at('purpose', policy.components.charges.reason);
      continue;
    }
    if (!isAmount(charge.amount) || D.parse(charge.amount.trim()) === D.ZERO) {
      at('amount', `Enter the ${inSentence(CHARGE_LABELS[charge.purpose])} amount.`);
    }
  }
  /* — settlement — */
  if (draft.creditDays.trim() && !/^\d{1,3}$/.test(draft.creditDays.trim())) {
    doc('creditDays', 'Credit days is a whole number of days, up to 999.');
  }
  if (draft.tenders.length > 0 && !isAvailable(policy.settlement.immediateTender)) {
    doc('tenders', policy.settlement.immediateTender.reason);
  }
  if (draft.tenders.length > 1 && !isAvailable(policy.settlement.splitTender)) {
    doc('tenders', 'This bill type takes one payment mode at a time.');
  }
  for (const tender of draft.tenders) {
    const at = (field: string, message: string) =>
      problems.push({ severity: 'error', lineKey: null, field: `${tender.key}.${field}`, message });
    if (!policy.settlement.tenderModes.includes(tender.mode)) {
      at('mode', `${TENDER_LABELS[tender.mode]} is not accepted on this bill type.`);
    }
    if (!isAmount(tender.amount) || D.parse(tender.amount.trim()) === D.ZERO) {
      at('amount', `Enter the ${inSentence(TENDER_LABELS[tender.mode])} amount.`);
    }
    if (tender.mode === 'CHEQUE') {
      const dated = tender.instrumentDate;
      if (!dated) {
        at('instrumentDate', 'Enter the date on the cheque.');
      } else if (draft.documentDate && dated > draft.documentDate) {
        problems.push({
          severity: 'warning',
          lineKey: null,
          field: `${tender.key}.instrumentDate`,
          message: `This cheque is post-dated: it cannot be presented before ${day(dated)}.`,
        });
      } else if (draft.documentDate && dated < (addMonths(draft.documentDate, -3) ?? '')) {
        problems.push({
          severity: 'warning',
          lineKey: null,
          field: `${tender.key}.instrumentDate`,
          message: 'This cheque is dated more than three months before the bill. Banks normally refuse a cheque that old.',
        });
      }
    }
    if (policy.settlement.referenceRequired.includes(tender.mode) && !tender.reference.trim()) {
      at('reference', `Enter the ${inSentence(REFERENCE_LABELS[tender.mode])}.`);
    }
    // A long run of digits on a card tender is a card number someone has typed into the
    // reference. It is refused outright rather than stored: raw card data is never kept, and
    // the place it would be kept is exactly here (CLAUDE.md §5.10).
    if (tender.mode === 'CARD' && /\d{12,19}/.test(tender.reference.replace(/\D/g, ''))) {
      at('reference', 'That looks like a card number. Enter only the approval code — card numbers are never stored.');
    }
  }
  if (draft.advances.length > 0 && !isAvailable(policy.settlement.advanceApplication)) {
    doc('advances', policy.settlement.advanceApplication.reason);
  }
  for (const advance of draft.advances) {
    const at = (field: string, message: string) =>
      problems.push({ severity: 'error', lineKey: null, field: `${advance.key}.${field}`, message });
    const applied = D.parse(advance.amount.trim());
    const available = D.parse(advance.available.trim());
    if (!isAmount(advance.amount) || applied === D.ZERO) {
      at('amount', `Enter how much of ${advance.sourceLabel} to apply.`);
    } else if (applied !== null && available !== null && applied > available) {
      // Exact: a float said 999999999999999.9999 was not more than ...9998.
      // Source-capped: an advance cannot be applied beyond what is left of it — no new money is
      // created by applying one (data model §4).
      at('amount', `Only ${money(advance.available)} of ${advance.sourceLabel} is unallocated.`);
    }
  }
  return problems;
}

/** A business date moved by whole calendar months, clamped to the month's last day. */
export function addMonths(isoDate: string, months: number): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]) - 1 + months;
  const day = Number(match[3]);
  const last = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  return new Date(Date.UTC(year, month, Math.min(day, last))).toISOString().slice(0, 10);
}

/**
 * A label as it reads mid-sentence: "Enter the cheque number", but "Enter the UTR" and "Enter
 * the UPI amount". Lower-casing a whole label turns an acronym into a word nobody uses.
 */
export function inSentence(label: string): string {
  const [first = '', second = ''] = label;
  return second && second === second.toUpperCase() && /[A-Z]/.test(second)
    ? label
    : first.toLowerCase() + label.slice(1);
}

export const TENDER_LABELS: Record<TenderMode, string> = {
  CASH: 'Cash',
  UPI: 'UPI',
  CARD: 'Card',
  BANK_TRANSFER: 'Bank transfer',
  CHEQUE: 'Cheque',
};

/** What each mode's reference *is*, so the field can say what it wants. */
export const REFERENCE_LABELS: Record<TenderMode, string> = {
  CASH: 'Receipt reference',
  UPI: 'UTR',
  CARD: 'Approval code',
  BANK_TRANSFER: 'UTR or transfer reference',
  CHEQUE: 'Cheque number',
};

export const CHARGE_LABELS: Record<DraftCharge['purpose'], string> = {
  FREIGHT: 'Freight',
  PACKING: 'Packing',
  INSURANCE: 'Insurance',
  HANDLING: 'Handling',
  OTHER: 'Other charge',
};

/** Whether a draft could be saved. Errors block; warnings are stated and accepted. */
export function isSavable(draft: SalesDraft, policy: SalesEntryPolicy, options: ProblemOptions = {}): boolean {
  return !draftProblems(draft, policy, options).some((problem) => problem.severity === 'error');
}

/** Where on the page a problem is fixed, and what that place is called. */
export type ProblemTarget =
  | { readonly kind: 'line'; readonly lineKey: string; readonly label: string }
  | { readonly kind: 'detail'; readonly lineKey: string; readonly label: string }
  | { readonly kind: 'field'; readonly field: string; readonly label: string }
  | { readonly kind: 'panel'; readonly panel: 'components' | 'payment'; readonly label: string };

/** Line fields that live in the line's detail drawer rather than in a grid cell. */
const DETAIL_FIELDS = new Set(['quantityReason', 'rateReason', 'freePurpose', 'stockIntent']);

const HEADER_FIELDS: Record<string, string> = {
  customerId: 'Customer',
  documentDate: 'Invoice date',
  postingDate: 'Posting date',
  creditDays: 'Credit days',
};

/**
 * Where a problem is fixed.
 *
 * A problem list a reader has to map back onto the page by eye is one nobody uses, so every
 * problem names a place: a line, a field of the document bar, or the drawer it lives in. The
 * component problems carry their component's key as the field's prefix, and are routed by
 * looking that key up on the draft rather than by parsing it — a key's spelling is not a
 * contract. `null` only for a problem this page has nowhere to send.
 */
export function problemTarget(problem: DraftProblem, draft: SalesDraft): ProblemTarget | null {
  if (problem.lineKey) {
    const ordinal = draft.lines.findIndex((line) => line.key === problem.lineKey) + 1;
    if (ordinal === 0) return null;
    // The reasons have no cell: they are answered in the line's detail, so that is where the
    // link goes — a link to the row would leave the reader looking for a field that is not there.
    return DETAIL_FIELDS.has(problem.field)
      ? { kind: 'detail', lineKey: problem.lineKey, label: `Line ${ordinal}` }
      : { kind: 'line', lineKey: problem.lineKey, label: `Line ${ordinal}` };
  }
  const header = HEADER_FIELDS[problem.field];
  if (header) return { kind: 'field', field: problem.field, label: header };
  if (problem.field === 'lines') {
    const first = draft.lines[0];
    return first ? { kind: 'line', lineKey: first.key, label: 'Lines' } : null;
  }
  const owner = problem.field.split('.')[0] ?? '';
  if (draft.discounts.some((entry) => entry.key === owner) || draft.charges.some((entry) => entry.key === owner)) {
    return { kind: 'panel', panel: 'components', label: 'Discounts and charges' };
  }
  if (
    problem.field === 'tenders' ||
    problem.field === 'advances' ||
    draft.tenders.some((entry) => entry.key === owner) ||
    draft.advances.some((entry) => entry.key === owner)
  ) {
    return { kind: 'panel', panel: 'payment', label: 'Payment' };
  }
  return null;
}
