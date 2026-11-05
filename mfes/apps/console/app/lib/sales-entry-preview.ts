import * as D from './fixed-decimal';
import { isAvailable, type SalesEntryPolicy } from './sales-entry-policy';
import {
  inSentence,
  isAccountLine,
  isGoodsLine,
  isAmount,
  isBlank,
  isQuantity,
  type DraftLine,
  type DraftProblem,
  type SalesDraft,
} from './sales-entry-draft';

/**
 * The provisional invoice preview: what the rail shows while someone types.
 *
 * **Not the calculation.** The service accepts the invoice, in a versioned dependency sequence it
 * owns — line prices, declared component stages, legal taxable bases and components, rounding,
 * then obligation and settlement (calculation §5). This file follows that same order so that the
 * two usually agree, and it is *shaped like* the service's accepted result so that wiring the real
 * one is a change of data source. Where it cannot know something — a tax rate nobody resolved, how
 * a charge is taxed, which state a customer is in — it says so in `unresolved` and shows the figure
 * as unknown, never as zero.
 *
 * Exact throughout: every figure is a `bigint` at the storage scale (`fixed-decimal`), so when the
 * preview and the accepted invoice differ it is because of a rule, never because of floating point.
 *
 * ## The order, and why it matters
 *
 * 1. **Base.** Billed quantity × rate. A tax-inclusive rate is brought back to its pre-tax base
 *    first, because every stage below applies to the pre-tax value.
 * 2. **Line discount**, on its own line.
 * 3. **Selected-line discounts**, on the lines they name.
 * 4. **Document discount**, on every line.
 *
 *    Each stage applies to what the stage before it left — so 10% then 5% is 14.5% of the
 *    original, not 15% (calculation §4). An amount is apportioned across its target lines by
 *    remaining value with the **largest-remainder** method, so the parts reconcile to the whole to
 *    the paisa — an allocation that does not reconcile to its source is rejected by the contract.
 * 5. **Tax**, per line, on its own taxable value, each component rounded half-up.
 * 6. **Charges**, added after tax. How a charge is taxed is a tax-profile result the service
 *    resolves, so the preview adds them untaxed and *says so*.
 * 7. **Round off** to the configured increment, as an explicit line — never by nudging tax.
 */

export type SupplyKind = 'INTRA_STATE' | 'INTER_STATE' | 'UNKNOWN';

export type PreviewLine = {
  readonly key: string;
  /** Billed quantity × pre-tax rate. */
  readonly base: string;
  readonly lineDiscount: string;
  /** Selected-line and document discounts together, as allocated to this line. */
  readonly allocatedDiscount: string;
  readonly taxableValue: string;
  /** In percent, or `null` while unresolved. */
  readonly taxRate: string | null;
  readonly tax: string | null;
  /** Taxable value plus tax — what the line contributes before charges and rounding. */
  readonly amount: string | null;
};

export type InvoicePreview = {
  readonly status: 'PROVISIONAL';
  readonly lines: readonly PreviewLine[];
  readonly subtotal: string;
  readonly discounts: { readonly line: string; readonly selected: string; readonly document: string; readonly total: string };
  readonly taxableValue: string;
  readonly supply: SupplyKind;
  /** `null` when any counted line's rate is unresolved — a partial tax total is a wrong one. */
  readonly tax: { readonly cgst: string | null; readonly sgst: string | null; readonly igst: string | null; readonly total: string } | null;
  readonly charges: string;
  readonly roundOff: string | null;
  readonly total: string | null;
  /**
   * What the bill leaves owing, by one equation: total, less advances applied, less money
   * received. Payment method never changes revenue or tax — it only changes this.
   */
  readonly settlement: Settlement;
  /** Why a figure is unknown, in sentences. Shown beside the figures, not hidden. */
  readonly unresolved: readonly string[];
  /** Which rules produced this, so a difference from the accepted invoice can be explained. */
  readonly rules: readonly string[];
  /** Figures the preview capped to stay a sale, as problems; see `previewProblems`. */
  readonly overruns: readonly DraftProblem[];
};

export type Settlement = {
  /** Existing credit applied. Not new money — it points at an open item Accounting holds. */
  readonly advances: string;
  /** Cash, UPI, card and bank transfer: recorded as received. */
  readonly received: string;
  /** Cheques: recorded, and not yet cleared bank cash. */
  readonly pendingClearance: string;
  /** `null` while the total is unknown — a remaining debt cannot be known before the debt. */
  readonly outstanding: string | null;
  /**
   * Cash handed back. Cash tendered, cash applied and change returned are separate facts
   * (data model §4); this is the third of them, only ever out of cash.
   */
  readonly changeDue: string | null;
  /** Received beyond the bill that no cash tender can return as change. */
  readonly excess: string | null;
  /** The credit due date, when anything is left owing on credit terms. A business date. */
  readonly dueDate: string | null;
};

export type PreviewContext = {
  /** The issuing company's registered state, for the intra/inter-state decision. */
  readonly companyState: string;
  /** The company's amount precision: component amounts round here. */
  readonly places: number;
  /**
   * The company's money formatter, for figures quoted in a sentence — `50,000.00`, not
   * `50000.00`. Absent, figures are quoted as computed.
   */
  readonly formatMoney?: (value: string) => string;
};

const ONE_HUNDRED = D.parse('100')!;

/**
 * The largest figure a `DECIMAL(19,4)` column holds is fifteen integer digits. Each input is
 * capped there, but a product or a sum of them is not — 100,000 × 99,999,999,999 is seventeen
 * digits — so a computed figure at or past this is refused rather than shown and saved.
 */
const STORAGE_LIMIT = D.parse('1000000000000000')!;

export function previewInvoice(
  draft: SalesDraft,
  policy: SalesEntryPolicy,
  context: PreviewContext,
): InvoicePreview {
  const places = context.places;
  /** A figure in a sentence, the way the company writes figures. */
  const say = (value: D.Fixed) => {
    const text = D.format(value, places);
    return context.formatMoney ? context.formatMoney(text) : text;
  };
  const unresolved: string[] = [];
  const rules: string[] = [
    'Each discount applies to what the stage before it left.',
    'Amounts are apportioned by remaining value, largest remainder.',
    'Tax components round half-up per line.',
  ];

  /* ---- 1. which lines count, and their pre-tax base ---- */

  type Working = {
    key: string;
    line: DraftLine;
    base: D.Fixed;
    /**
     * Set on a tax-inclusive line once its figures are taken back to pre-tax: what the customer
     * pays for it after every discount, which the base and the tax must add back to exactly.
     */
    inclusive: D.Fixed | null;
    lineDiscount: D.Fixed;
    allocated: D.Fixed;
    /** The selected-line and document shares inside `allocated`, kept apart for the rail. */
    selected: D.Fixed;
    document: D.Fixed;
    /** The last bill-level discount that took something from this line. */
    takenBy: string | null;
    rate: D.Fixed | null;
  };

  const working: Working[] = [];
  const overruns: DraftProblem[] = [];
  /**
   * A discount past its approval threshold, measured on what it *comes to* — not on how it was
   * typed. An amount of 20,000 on a 24,500 bill is 82% whether or not anyone typed a `%`.
   */
  const approval = (
    lineKey: string | null,
    field: string,
    applied: D.Fixed,
    pool: D.Fixed,
    threshold: string,
    label: string,
  ) => {
    const limit = D.parse(threshold);
    if (limit === null || pool <= D.ZERO) return;
    // applied ÷ pool > limit ÷ 100, cross-multiplied so nothing rounds on the way.
    if (applied * 100n * D.ONE <= pool * limit) return;
    const share = D.format(D.div(applied * 100n, pool), 2);
    overruns.push({
      severity: 'warning',
      lineKey,
      field,
      message: `The ${label} comes to ${share}% of what it applies to; above ${threshold}% needs approval before the bill can proceed.`,
    });
  };
  /** An inclusive line left out for want of a tax rate: the total is then not known either. */
  let excluded = false;
  draft.lines.forEach((line, index) => {
    if (isBlank(line)) return;
    if (
      (draft.mode === 'ACCOUNTS' && line.subjectKind === 'ITEM') ||
      (draft.mode === 'ITEMS' && line.subjectKind === 'ACCOUNT')
    ) {
      // Priced as the mode would price it, an item on an accounts bill becomes one unit of its
      // rate. A wrong figure is worse than an absent one; `draftProblems` says why.
      unresolved.push(`Line ${index + 1} does not fit this mode, so it is not in the totals.`);
      return;
    }
    // An account line is one amount: no quantity, and none asked for.
    const quantityText = isAccountLine(draft, line) ? '1' : line.billedQuantity;
    if (!isQuantity(quantityText) || !isAmount(line.rate)) {
      unresolved.push(`Line ${index + 1} is not complete, so it is not in the totals yet.`);
      return;
    }
    const quantity = D.parse(quantityText)!;
    const rate = D.parse(line.rate)!;
    const taxRate = line.taxRate.trim() !== '' ? D.parse(line.taxRate) : null;

    /*
     * On a tax-inclusive bill the base stays the *inclusive* figure through every discount stage,
     * and is taken back to pre-tax only after them (below). A discount on an inclusive price is
     * then inclusive too — ₹18 off a ₹118 line at 18% leaves ₹100, which is what a counter clerk
     * quoting "₹118, ₹18 off" means — and a percentage gives the same answer either way.
     */
    const base = D.round(D.mul(quantity, rate), places);
    if (draft.taxInclusive) {
      if (taxRate === null) {
        // An inclusive rate cannot be taken back to its base without knowing what is inside
        // it. Counting the inclusive figure as the base would overstate the taxable value —
        // and leaving the line out while still showing a total would understate the bill.
        unresolved.push(`Line ${index + 1}'s tax is not resolved, so its tax-inclusive rate cannot be split.`);
        excluded = true;
        return;
      }
    }

    /* ---- 2. the line's own discount ---- */
    let lineDiscount = D.ZERO;
    if (line.discountInput.trim() && isAmount(line.discountInput) && isAvailable(policy.components.lineDiscount)) {
      const input = D.parse(line.discountInput)!;
      lineDiscount =
        line.discountKind === 'PERCENT'
          ? D.round(D.percent(base, D.min(input, ONE_HUNDRED)), places)
          : D.min(D.round(input, places), base);
      if (line.discountKind === 'AMOUNT' && D.round(input, places) > base) {
        // Capped so the preview stays a sale — but said, because the draft still carries the
        // larger figure and would hand it over.
        overruns.push({
          severity: 'error',
          lineKey: line.key,
          field: 'discountInput',
          message: `The discount is more than the line's value of ${say(base)}.`,
        });
      }
      const control = policy.components.lineDiscount;
      if (control.approvalAbove) {
        approval(line.key, 'discountInput', lineDiscount, base, control.approvalAbove, 'line discount');
      }
    }
    working.push({
      key: line.key,
      line,
      base,
      inclusive: null,
      lineDiscount,
      allocated: D.ZERO,
      selected: D.ZERO,
      document: D.ZERO,
      takenBy: null,
      rate: taxRate,
    });
  });

  const remaining = (entry: Working) => entry.base - entry.lineDiscount - entry.allocated;

  /* ---- 3 and 4. selected-line, then document discounts ---- */

  let selectedTotal = D.ZERO;
  let documentTotal = D.ZERO;
  const stages = [
    ...draft.discounts.filter((entry) => entry.scope === 'SELECTED'),
    ...draft.discounts.filter((entry) => entry.scope === 'DOCUMENT'),
  ];
  for (const discount of stages) {
    const control =
      discount.scope === 'DOCUMENT'
        ? policy.components.documentDiscount
        : policy.components.selectedLineDiscount;
    if (!isAvailable(control) || !isAmount(discount.input)) continue;
    const targets =
      discount.scope === 'DOCUMENT'
        ? working
        : working.filter((entry) => discount.lineKeys.includes(entry.key));
    if (targets.length === 0) continue;

    const input = D.parse(discount.input)!;
    let shares: D.Fixed[];
    if (discount.kind === 'PERCENT') {
      const rate = D.min(input, ONE_HUNDRED);
      shares = targets.map((entry) => D.round(D.percent(remaining(entry), rate), places));
    } else {
      // An amount never exceeds what it is discounting: a negative taxable value is not a sale.
      const pool = targets.reduce((sum, entry) => sum + remaining(entry), D.ZERO);
      const amount = D.min(D.round(input, places), pool);
      if (D.round(input, places) > pool) {
        overruns.push({
          severity: 'error',
          lineKey: null,
          field: `${discount.key}.input`,
          message: `The ${inSentence(discount.label)} is more than the ${say(pool)} it applies to.`,
        });
      }
      shares = D.allocate(amount, targets.map(remaining), places);
    }
    const before = targets.reduce((sum, entry) => sum + remaining(entry), D.ZERO);
    targets.forEach((entry, index) => {
      entry.allocated += shares[index]!;
      if (discount.scope === 'DOCUMENT') entry.document += shares[index]!;
      else entry.selected += shares[index]!;
      if (shares[index]! > D.ZERO) entry.takenBy = discount.key;
    });
    const applied = shares.reduce((sum, share) => sum + share, D.ZERO);
    // A percentage is checked as typed, by the draft; an amount only shows its size here.
    // Over its pool it is already an error; "comes to 100%" on top of that says nothing new.
    if (control.approvalAbove && discount.kind === 'AMOUNT' && D.round(input, places) <= before) {
      approval(null, `${discount.key}.input`, applied, before, control.approvalAbove, inSentence(discount.label));
    }
  }

  /*
   * ---- 4½. an inclusive bill, back to pre-tax ----
   *
   * What the customer pays for each line is now known: its inclusive figure less every discount.
   * Taken back to pre-tax — `× 100 ÷ (100 + rate)`, multiplied before dividing so no precision
   * is thrown away — that is the taxable value, and the tax is whatever is left, so the two add
   * back to the inclusive figure exactly (100 at 18% bills 100.00, never 100.01). The discounts
   * the rail shows are the pre-tax difference, shared across the stages that made it.
   */
  if (draft.taxInclusive) {
    for (const entry of working) {
      if (entry.rate === null) continue;
      const divisor = D.add(ONE_HUNDRED, entry.rate);
      const pays = remaining(entry);
      const basePre = D.round(D.div(entry.base * 100n, divisor), places);
      const taxable = D.round(D.div(pays * 100n, divisor), places);
      const weights = [entry.lineDiscount, entry.selected, entry.document];
      const discount = basePre - taxable;
      const parts =
        weights.some((weight) => weight > D.ZERO) && discount > D.ZERO
          ? D.allocate(discount, weights, places)
          : [D.ZERO, D.ZERO, D.ZERO];
      entry.inclusive = pays;
      entry.base = basePre;
      entry.lineDiscount = parts[0]!;
      entry.selected = parts[1]!;
      entry.document = parts[2]!;
      entry.allocated = parts[1]! + parts[2]!;
    }
  }
  selectedTotal = working.reduce((sum, entry) => sum + entry.selected, D.ZERO);
  documentTotal = working.reduce((sum, entry) => sum + entry.document, D.ZERO);

  /* ---- 5. tax, per line ---- */

  // The place of supply: the ship-to address when one is chosen — goods are supplied where they
  // are delivered — and the customer's registered state otherwise.
  // Services are supplied where the customer is billed. A bill with goods on it takes the
  // goods' place of supply, which is the one that decides how most such bills are taxed; a
  // mixed bill shipped to another state is the service's to split per line.
  const goodsOnBill = working.some((entry) => isGoodsLine(draft, entry.line));
  const supplyState = goodsOnBill
    ? draft.shipToState || draft.billToState || draft.customerState
    : draft.billToState || draft.customerState;
  const supply: SupplyKind =
    !supplyState || !context.companyState
      ? 'UNKNOWN'
      : supplyState.toLowerCase() === context.companyState.toLowerCase()
        ? 'INTRA_STATE'
        : 'INTER_STATE';

  let taxResolved = true;
  let cgst = D.ZERO;
  let sgst = D.ZERO;
  let igst = D.ZERO;
  const lines: PreviewLine[] = working.map((entry) => {
    const taxable = remaining(entry);
    if (entry.rate === null) {
      taxResolved = false;
      return {
        key: entry.key,
        base: D.format(entry.base, places),
        lineDiscount: D.format(entry.lineDiscount, places),
        allocatedDiscount: D.format(entry.allocated, places),
        taxableValue: D.format(taxable, places),
        taxRate: null,
        tax: null,
        amount: null,
      };
    }
    /*
     * CGST and SGST are each computed at half the rate and rounded separately — not one tax
     * figure halved — because that is how the components exist, and halving a rounded total can
     * disagree with them by a paisa. IGST is the whole rate, once.
     */
    const half = D.div(entry.rate, D.parse('2')!);
    let central = D.round(D.percent(taxable, half), places);
    let state = D.round(D.percent(taxable, half), places);
    let integrated = D.round(D.percent(taxable, entry.rate), places);
    if (entry.inclusive !== null) {
      /*
       * A tax-inclusive price is a promise about the total: what the customer was quoted is
       * what they pay. So the tax is what is left of the inclusive figure once the base is
       * taken out — not the base times the rate again, which rounds twice and lands a paisa off
       * (100 at 18% would bill 100.01). The halves are split so they add back exactly, the
       * second taking the remainder.
       */
      const whole = entry.inclusive - taxable;
      integrated = whole;
      central = D.round(D.div(whole, D.parse('2')!), places);
      state = whole - central;
    }
    const lineTax = supply === 'INTER_STATE' ? integrated : central + state;
    if (supply === 'INTER_STATE') igst += integrated;
    else {
      cgst += central;
      sgst += state;
    }
    return {
      key: entry.key,
      base: D.format(entry.base, places),
      lineDiscount: D.format(entry.lineDiscount, places),
      allocatedDiscount: D.format(entry.allocated, places),
      taxableValue: D.format(taxable, places),
      taxRate: D.format(entry.rate, 2),
      tax: D.format(lineTax, places),
      amount: D.format(taxable + lineTax, places),
    };
  });

  if (!taxResolved) {
    unresolved.push('Some lines have no resolved tax rate, so the tax and the total are not known yet.');
  }

  /*
   * Zero consideration, however it was reached. A zero rate is refused by the draft; this finds
   * the other routes to the same place — a rate that rounds to nothing (1 × 0.004), a 100% line
   * discount, an amount discount equal to the line — each of which billed 0.00 with no word.
   */
  const freeAllowed = isAvailable(policy.quantities.freeItem);
  /*
   * Said where it is fixed: the line's own discount, or the bill-level discount that took the
   * line to nothing — once per discount, not once per line it emptied. And worded by what the
   * policy allows: asking for a free-item purpose where free lines are not allowed asks for
   * something nobody can give.
   */
  const giveaway = freeAllowed
    ? 'A line given away is entered at a zero rate with its purpose, not discounted to nothing.'
    : 'This bill type does not allow free lines.';
  const reported = new Set<string>();
  for (const entry of working) {
    const rateText = entry.line.rate.trim();
    if (remaining(entry) !== D.ZERO || D.parse(rateText) === D.ZERO) continue;
    if (freeAllowed && entry.line.freePurpose) continue;
    if (entry.lineDiscount > D.ZERO) {
      overruns.push({
        severity: 'error',
        lineKey: entry.key,
        field: 'discountInput',
        message: `This discount takes the line to nothing. ${giveaway}`,
      });
    } else if (entry.takenBy) {
      if (reported.has(entry.takenBy)) continue;
      reported.add(entry.takenBy);
      const label = draft.discounts.find((discount) => discount.key === entry.takenBy)?.label ?? 'discount';
      overruns.push({
        severity: 'error',
        lineKey: null,
        field: `${entry.takenBy}.input`,
        message: `The ${inSentence(label)} takes a line to nothing. ${giveaway}`,
      });
    } else {
      overruns.push({
        severity: 'error',
        lineKey: entry.key,
        field: 'rate',
        message: 'This line comes to nothing once its rate is rounded to the company’s precision. Check the rate.',
      });
    }
  }
  for (const line of lines) {
    // The base and taxable value too: with a tax rate unresolved the amount is unknown, and a
    // seventeen-digit line was then saved without a word.
    const figures = [line.base, line.taxableValue, line.amount];
    if (figures.some((figure) => figure !== null && D.parse(figure)! >= STORAGE_LIMIT)) {
      overruns.push({
        severity: 'error',
        lineKey: line.key,
        field: 'rate',
        message: 'This line comes to more than the platform can store. Check the quantity and the rate.',
      });
    }
  }
  if (supply === 'UNKNOWN' && working.length > 0) {
    // Not "the same either way": IGST rounds once and CGST + SGST round twice, so the two can
    // differ by a paisa per line. The figure is shown as intra-state until the customer says.
    unresolved.push(
      'Choose a customer to know whether this is an intra-state or an inter-state supply. Tax is shown as CGST + SGST until then; an inter-state split can differ by a paisa of rounding.',
    );
  }

  /* ---- 6. charges ---- */

  /*
   * An amount that rounds to nothing at the company's precision — 0.004 at two places — passed
   * the "not zero" check and then counted as 0.00. It is said, not silently dropped.
   */
  const vanishes = (key: string, text: string, what: string) => {
    const value = D.parse(text.trim());
    if (value !== null && value > D.ZERO && D.round(value, places) === D.ZERO) {
      overruns.push({
        severity: 'error',
        lineKey: null,
        field: `${key}.amount`,
        message: `${text.trim()} is less than the smallest ${what} this company records (${D.format(10n ** BigInt(D.SCALE - places), places)}).`,
      });
    }
  };

  let charges = D.ZERO;
  if (isAvailable(policy.components.charges)) {
    for (const charge of draft.charges) {
      if (isAmount(charge.amount)) charges += D.round(D.parse(charge.amount)!, places);
      vanishes(charge.key, charge.amount, 'charge');
    }
    if (draft.charges.length > 0) {
      unresolved.push(
        'How a charge is taxed is resolved by the service, so the preview adds charges untaxed.',
      );
    }
  }

  /* ---- totals and 7. round off ---- */

  const subtotal = working.reduce((sum, entry) => sum + entry.base, D.ZERO);
  const lineDiscounts = working.reduce((sum, entry) => sum + entry.lineDiscount, D.ZERO);
  const taxableValue = working.reduce((sum, entry) => sum + remaining(entry), D.ZERO);
  const taxTotal = cgst + sgst + igst;

  let roundOff: D.Fixed | null = null;
  let total: D.Fixed | null = null;
  if (taxResolved && !excluded) {
    const unrounded = taxableValue + taxTotal + charges;
    if (isAvailable(policy.components.rounding) && policy.components.rounding.default === 'NEAREST_1') {
      const rounded = D.roundTo(unrounded, D.parse('1')!);
      roundOff = rounded - unrounded;
      total = rounded;
      rules.push('The total rounds half-up to the nearest whole unit, shown as its own line.');
    } else {
      roundOff = D.ZERO;
      total = unrounded;
    }
  }

  /* ---- 8. settlement: one equation ---- */

  let advances = D.ZERO;
  let requestedAdvances = D.ZERO;
  if (isAvailable(policy.settlement.advanceApplication)) {
    for (const advance of draft.advances) {
      if (!isAmount(advance.amount) || !isAmount(advance.available)) continue;
      // Source-capped: never more than the advance still has unallocated.
      advances += D.min(D.round(D.parse(advance.amount)!, places), D.parse(advance.available)!);
      requestedAdvances += D.round(D.parse(advance.amount)!, places);
      vanishes(advance.key, advance.amount, 'amount');
    }
  }
  let received = D.ZERO;
  let pending = D.ZERO;
  let cash = D.ZERO;
  if (isAvailable(policy.settlement.immediateTender)) {
    for (const tender of draft.tenders) {
      if (!isAmount(tender.amount)) continue;
      const amount = D.round(D.parse(tender.amount)!, places);
      if (tender.mode === 'CHEQUE') pending += amount;
      else received += amount;
      if (tender.mode === 'CASH') cash += amount;
      vanishes(tender.key, tender.amount, 'amount');
    }
  }
  if (pending > D.ZERO) {
    unresolved.push('A cheque is recorded now and cleared when the bank confirms it.');
  }

  let outstanding: D.Fixed | null = null;
  let changeDue: D.Fixed | null = null;
  let excess: D.Fixed | null = null;
  if (total !== null) {
    // An advance larger than the bill is applied only up to the bill: the rest stays on the
    // advance for another document, rather than becoming a negative debt here.
    if (advances > total) {
      // Said as well as capped: the draft carries the larger figures and would hand them over.
      overruns.push({
        severity: 'error',
        lineKey: null,
        field: 'advances',
        message: `Advances of ${say(requestedAdvances)} are more than the bill of ${say(total)}. Reduce an advance.`,
      });
      advances = total;
    }
    const remaining = total - advances - received - pending;
    if (remaining >= D.ZERO) {
      outstanding = remaining;
      changeDue = D.ZERO;
      excess = D.ZERO;
    } else {
      outstanding = D.ZERO;
      const over = -remaining;
      // Change comes out of cash and only out of cash: nobody hands back change on a UPI
      // payment. Anything over that is money received beyond the bill.
      changeDue = D.min(over, cash);
      excess = over - changeDue;
    }
  }

  if ((total !== null && total >= STORAGE_LIMIT) || subtotal >= STORAGE_LIMIT || taxableValue >= STORAGE_LIMIT) {
    overruns.push({
      severity: 'error',
      lineKey: null,
      field: 'total',
      message: 'The bill comes to more than the platform can store. Check the quantities and the rates.',
    });
  }

  /*
   * The customer's credit, as the party master projects it: a warning, not a block. Whether a
   * limit stops a bill is the service's policy to apply; this tells the clerk before saving.
   */
  const position = draft.customerCredit;
  if (position) {
    const owed = D.parse(position.outstanding) ?? D.ZERO;
    const limit = position.limit ? D.parse(position.limit) : null;
    const overdue = D.parse(position.overdue) ?? D.ZERO;
    // Only a bill that leaves something on credit can take anyone over a limit: one paid in
    // full at the counter adds nothing to what is owed.
    if (limit !== null && outstanding !== null && outstanding > D.ZERO && owed + outstanding > limit) {
      overruns.push({
        severity: 'warning',
        lineKey: null,
        field: 'customerId',
        message: `This bill takes ${draft.customerLabel || 'the customer'} ${say(owed + outstanding - limit)} over their credit limit of ${say(limit)}.`,
      });
    }
    // Said as soon as the customer is chosen — not only once every line is complete.
    if (overdue > D.ZERO) {
      overruns.push({
        severity: 'warning',
        lineKey: null,
        field: 'customerId',
        message: `${draft.customerLabel || 'The customer'} already has ${say(overdue)} overdue.`,
      });
    }
  }

  if (draft.taxInclusive && (draft.discounts.length > 0 || working.some((entry) => entry.lineDiscount > D.ZERO))) {
    // Stated, because a clerk could expect either; this is the rule the page applies, and the
    // one the service must confirm (voucher-sales-entry-ui.md, decision S8-1).
    unresolved.push(
      'Rates include tax, so discounts come off the tax-inclusive price — ₹18 off a ₹118 line at 18% leaves ₹100 to pay.',
    );
  }

  const credit = isAvailable(policy.settlement.credit) && /^\d{1,3}$/.test(draft.creditDays.trim());
  const dueDate =
    outstanding !== null && outstanding > D.ZERO && credit && draft.documentDate
      ? addDays(draft.documentDate, Number(draft.creditDays))
      : null;

  const split = (value: D.Fixed, applies: boolean) =>
    supply === 'UNKNOWN' ? null : applies ? D.format(value, places) : D.format(D.ZERO, places);

  return {
    status: 'PROVISIONAL',
    lines,
    subtotal: D.format(subtotal, places),
    discounts: {
      line: D.format(lineDiscounts, places),
      selected: D.format(selectedTotal, places),
      document: D.format(documentTotal, places),
      total: D.format(lineDiscounts + selectedTotal + documentTotal, places),
    },
    taxableValue: D.format(taxableValue, places),
    supply,
    tax: taxResolved
      ? {
          cgst: split(cgst, supply === 'INTRA_STATE'),
          sgst: split(sgst, supply === 'INTRA_STATE'),
          igst: split(igst, supply === 'INTER_STATE'),
          total: D.format(taxTotal, places),
        }
      : null,
    charges: D.format(charges, places),
    roundOff: roundOff === null ? null : D.format(roundOff, places),
    total: total === null ? null : D.format(total, places),
    settlement: {
      advances: D.format(advances, places),
      received: D.format(received, places),
      pendingClearance: D.format(pending, places),
      outstanding: outstanding === null ? null : D.format(outstanding, places),
      changeDue: changeDue === null ? null : D.format(changeDue, places),
      excess: excess === null ? null : D.format(excess, places),
      dueDate,
    },
    unresolved,
    rules,
    overruns,
  };
}

/**
 * A business date plus whole days, as a business date.
 *
 * UTC arithmetic on the calendar date alone, so a due date never shifts by a day because a
 * browser is east of Greenwich — business dates are dates, never datetimes (CLAUDE.md §4).
 */
export function addDays(isoDate: string, days: number): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
  if (!match) return null;
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]) + days));
  return date.toISOString().slice(0, 10);
}

/**
 * What the arithmetic says is wrong. Separate from `draftProblems` because it needs computed
 * figures: an amount discount larger than what it discounts, advances larger than the bill,
 * money received beyond the bill. The preview caps each of these so it stays a sale, and each
 * cap is stated here, because the draft still carries the larger figure.
 */
export function previewProblems(preview: InvoicePreview): DraftProblem[] {
  const problems: DraftProblem[] = [...preview.overruns];
  const excess = preview.settlement.excess;
  if (excess !== null && D.parse(excess)! > D.ZERO) {
    problems.push({
      severity: 'error',
      lineKey: null,
      field: 'tenders',
      // Retaining an overpayment as customer credit is a deliberate act with its own
      // accounting; it is not something a bill should do because the amounts were mistyped.
      message: `${excess} more than the bill has been received, and only cash can be handed back as change. Reduce a payment.`,
    });
  }
  return problems;
}
