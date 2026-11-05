/**
 * The effective Sales policy, as the entry form reads it.
 *
 * **This is a proposal, not a service contract.** `docs/voucher-sales-configuration-plan.md` §3
 * says the effective-policy response *should* expose source revision IDs, allowed/required/
 * default/editable controls and reasons for disabled mechanics — and nothing implements it. This
 * file is that shape written down by building a form against it, which is the same ordering the
 * invoice designer used: the interface is reviewable before a contract is committed to a
 * migration, and it already found things reading a schema would not.
 *
 * The one rule worth stating twice: **the six control properties are separate.** §3 is explicit
 * that `availability`, `requiredness`, `default`, `editability`, `override permission/reason` and
 * `approval threshold` are different facts. Collapsing them into a boolean is how a form ends up
 * hiding a field the API still requires, or greying one a reader is allowed to override with a
 * reason. So `Control` carries all of them and the form asks the question it actually means.
 */

/** Why a mechanic is not offered. Shown, never swallowed — a disabled control must answer "why". */
export type Unavailable = { readonly available: false; readonly reason: string };

export type Available<T> = {
  readonly available: true;
  /** Must be supplied before the draft is valid. */
  readonly required: boolean;
  /** What the form starts with. A class may default a permitted value. */
  readonly default?: T;
  /**
   * Whether a reader may change it at all. Distinct from `available`: a policy can show a
   * resolved value it will not let anyone edit, which is how tax is presented.
   */
  readonly editable: boolean;
  /** Set when editing beyond the default needs a grant, and a stated reason. */
  readonly override?: { readonly permission: string; readonly reasonRequired: boolean };
  /** Set when a value past this threshold needs approval before the document can proceed. */
  readonly approvalAbove?: string;
};

export type Control<T = string> = Available<T> | Unavailable;

export function isAvailable<T>(control: Control<T>): control is Available<T> {
  return control.available;
}

/** A control a reader may actually type into right now. */
export function isEditable<T>(control: Control<T>): boolean {
  return control.available && control.editable;
}

/* ------------------------------------------------------------------ the sales envelope */

export type EntryMode = 'ITEMS' | 'ACCOUNTS' | 'MIXED';

/** How money was received at the point of billing. A cheque is not cleared bank cash. */
export type TenderMode = 'CASH' | 'UPI' | 'CARD' | 'BANK_TRANSFER' | 'CHEQUE';

/** A reason for a quantity difference, and which way it explains: more leave, fewer, or either. */
export type DifferenceReason = { readonly label: string; readonly applies: 'MORE' | 'LESS' | 'EITHER' };

/** A column in the line grid. Which ones exist is policy's answer, not a reader's preference. */
export type LineColumn =
  | 'item'
  | 'account'
  | 'description'
  | 'hsn_sac'
  | 'actual_quantity'
  | 'billed_quantity'
  | 'unit'
  | 'rate'
  | 'discount'
  | 'taxable_value'
  | 'tax_rate'
  | 'tax_amount'
  | 'amount';

export type SalesEntryPolicy = {
  /**
   * The revision IDs this form resolved against. Pinned to the draft, so an accepted
   * calculation can be re-checked against the policy that produced it rather than against
   * today's settings — a posted invoice is never reinterpreted (CLAUDE.md §6.17's reasoning).
   */
  readonly source: {
    readonly companyPolicyRevisionId: string;
    readonly typeRevisionId: string;
    readonly classRevisionId: string | null;
    readonly digest: string;
  };
  readonly modes: { readonly allowed: readonly EntryMode[]; readonly default: EntryMode };
  readonly party: {
    readonly customer: Control;
    readonly billTo: Control;
    readonly shipTo: Control;
    /** Narrowed by the class. An empty list means any permitted group. */
    readonly allowedGroups: readonly string[];
  };
  readonly dates: {
    readonly documentDate: Control<string>;
    /** Determines the period. Never `created_at`, never the document date (CLAUDE.md §6.4). */
    readonly postingDate: Control<string>;
    readonly supplyDate: Control<string>;
  };
  readonly numbering: {
    readonly mode: 'AUTOMATIC' | 'AUTOMATIC_WITH_OVERRIDE' | 'MANUAL';
    readonly series: Control<string>;
    /** What the next number will look like. A preview is provisional and reserves nothing. */
    readonly preview: string | null;
  };
  readonly pricing: {
    readonly priceLevel: Control<string>;
    readonly taxInclusiveEntry: Control<boolean>;
    readonly rateOverride: Control<string>;
  };
  readonly quantities: {
    /** Actual and billed are separate facts, so they are separate controls. */
    readonly actualVersusBilled: Control<boolean>;
    readonly rewardQuantity: Control<string>;
    readonly freeItem: Control<string>;
    /** Why a free line is free, when `freeItem` is available: a sample, a gift, a replacement. */
    readonly freePurposes: readonly string[];
    /**
     * Why actual and billed may differ, each with the direction it explains. A bonus explains
     * more leaving than is billed and a short supply fewer; offering either for the other would
     * accept evidence for something that did not happen.
     */
    readonly differenceReasons: readonly DifferenceReason[];
  };
  readonly components: {
    readonly lineDiscount: Control<string>;
    readonly selectedLineDiscount: Control<string>;
    readonly documentDiscount: Control<string>;
    readonly charges: Control<string>;
    readonly rounding: Control<string>;
  };
  readonly settlement: {
    readonly credit: Control<string>;
    readonly immediateTender: Control<string>;
    readonly splitTender: Control<boolean>;
    readonly advanceApplication: Control<string>;
    /**
     * The tender modes this bill type accepts — a bounded allowlist in the Sales envelope, not
     * whatever modes exist. A POS class may narrow it to cash and UPI; a B2B type to bank
     * transfer and cheque.
     */
    readonly tenderModes: readonly TenderMode[];
    /** Modes whose reference — a UTR, a cheque number — must be captured with the tender. */
    readonly referenceRequired: readonly TenderMode[];
  };
  /** Statutory surfaces stay gated until their profile is verified (§3, B19). */
  readonly statutory: { readonly eInvoice: Control<string>; readonly eWayBill: Control<string> };
  /**
   * Why the document cannot be issued from here, if it cannot.
   *
   * Always set today: Sales invoice issuance is rejected in Vouchers pending the statutory
   * profile, and the legal allocator belongs to Accounting under D05
   * (`voucher-sales-configuration-plan.md` §3.1). The form therefore offers Save draft and
   * Preview, and *says* this rather than showing a button that 400s.
   */
  readonly issuance: Unavailable | { readonly available: true };
};

/** The columns a mode asks for, before policy narrows them. */
export function columnsFor(mode: EntryMode, policy: SalesEntryPolicy): readonly LineColumn[] {
  const identity: readonly LineColumn[] =
    mode === 'ACCOUNTS' ? ['account', 'description'] : ['item', 'description', 'hsn_sac'];
  const measured: readonly LineColumn[] =
    mode === 'ACCOUNTS'
      ? []
      : isAvailable(policy.quantities.actualVersusBilled)
        ? ['actual_quantity', 'billed_quantity', 'unit']
        : ['billed_quantity', 'unit'];
  const discount: readonly LineColumn[] = isAvailable(policy.components.lineDiscount)
    ? ['discount']
    : [];
  return [
    ...identity,
    ...measured,
    'rate',
    ...discount,
    'taxable_value',
    'tax_rate',
    'tax_amount',
    'amount',
  ];
}

/** Columns a reader may never type into: the service resolves them. */
export const DERIVED_COLUMNS: ReadonlySet<LineColumn> = new Set<LineColumn>([
  'taxable_value',
  'tax_rate',
  'tax_amount',
  'amount',
]);

export const COLUMN_LABELS: Record<LineColumn, string> = {
  item: 'Item',
  account: 'Account',
  description: 'Description',
  hsn_sac: 'HSN/SAC',
  actual_quantity: 'Actual',
  billed_quantity: 'Billed',
  unit: 'Unit',
  rate: 'Rate',
  discount: 'Discount',
  taxable_value: 'Taxable value',
  tax_rate: 'Tax %',
  tax_amount: 'Tax',
  amount: 'Amount',
};

/* ------------------------------------------------------------------ the S1 fixture */

const on = (over: Partial<Available<string>> = {}): Control<string> => ({
  available: true,
  required: false,
  editable: true,
  ...over,
});

const off = (reason: string): Unavailable => ({ available: false, reason });

/**
 * What a company with India GST, item invoicing and credit sales would resolve to.
 *
 * A fixture for this phase, deliberately not the union of everything: a policy that enables
 * every mechanic would make the form look finished and would exercise none of the "this is
 * unavailable, and here is why" paths, which are the ones a real tenant meets first.
 *
 * The disabled entries are the real platform state, not invented restrictions — automatic
 * schemes, e-invoice and e-way bill each have their own delivery gate.
 */
export const SAMPLE_SALES_POLICY: SalesEntryPolicy = {
  source: {
    companyPolicyRevisionId: '01990000-0000-7000-8000-0000000000a1',
    typeRevisionId: '01990000-0000-7000-8000-0000000000a2',
    classRevisionId: null,
    digest: 'sha256:provisional-fixture',
  },
  modes: { allowed: ['ITEMS', 'ACCOUNTS', 'MIXED'], default: 'ITEMS' },
  party: {
    customer: on({ required: true }),
    billTo: on(),
    shipTo: on(),
    allowedGroups: [],
  },
  dates: {
    documentDate: on({ required: true, default: '' }),
    postingDate: on({ required: true, default: '' }),
    supplyDate: on(),
  },
  numbering: {
    mode: 'AUTOMATIC',
    // Not editable: an automatic series allocates under an owner lock at issue, and a preview
    // reserves nothing (`voucher-sales-configuration-plan.md` §3.1).
    series: { available: true, required: true, editable: false, default: 'SI/26-27/' },
    preview: 'SI/26-27/0001',
  },
  pricing: {
    priceLevel: on({ default: 'Retail' }),
    taxInclusiveEntry: { available: true, required: false, editable: true, default: false },
    rateOverride: on({
      override: { permission: 'vouchers.edit', reasonRequired: true },
      approvalAbove: '10',
    }),
  },
  quantities: {
    actualVersusBilled: { available: true, required: false, editable: true, default: false },
    rewardQuantity: on({ override: { permission: 'vouchers.edit', reasonRequired: true } }),
    freeItem: off('An independent gift or sample needs its own authorisation and tax purpose.'),
    freePurposes: ['Sample', 'Gift', 'Warranty replacement'],
    differenceReasons: [
      { label: 'Manual bonus quantity', applies: 'MORE' },
      { label: 'Short supply', applies: 'LESS' },
      { label: 'Measured variance', applies: 'EITHER' },
    ],
  },
  components: {
    lineDiscount: on(),
    selectedLineDiscount: on(),
    documentDiscount: on({ approvalAbove: '5' }),
    charges: on(),
    rounding: on({ default: 'NEAREST_1' }),
  },
  settlement: {
    credit: on({ default: '30' }),
    immediateTender: on(),
    splitTender: { available: true, required: false, editable: true, default: false },
    advanceApplication: on(),
    tenderModes: ['CASH', 'UPI', 'CARD', 'BANK_TRANSFER', 'CHEQUE'],
    referenceRequired: [],
  },
  statutory: {
    eInvoice: off('The statutory artifact profile is not released for this company yet.'),
    eWayBill: off('Transport evidence and the e-way-bill profile are not released yet.'),
  },
  issuance: off(
    'Issuing a Sales invoice needs the statutory numbering profile, which is not released. Save a draft and preview it.',
  ),
};
