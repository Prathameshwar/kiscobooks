/**
 * The shared voucher vocabulary (docs/vouchers-plan.md §2 — the 22 kinds).
 *
 * Restated here rather than fetched, because the `design` service validates the *shape* of a kind
 * and does not own the list — it is code-defined in `vouchers`
 * (`vouchers/domain/registry.py`, which a test of this file mirrors). A select is still better
 * than a free text box: the service's pattern would accept `SAILS` happily, and a rule that never
 * matches anything is indistinguishable from no rule at all.
 *
 * **Not a client module, on purpose.** The Voucher print pages resolve their `[kind]` segment on
 * the server, and a function exported from a `'use client'` file is a client reference there, not
 * something a Server Component can call.
 */
export type VoucherKindEntry = { value: string; label: string };

/** `Label — what it is`. The text before the dash is the name; the rest is what a card says. */
export const VOUCHER_KINDS: readonly VoucherKindEntry[] = [
  { value: 'SALES', label: 'Sales — invoice, cash or credit sale' },
  { value: 'PURCHASE', label: 'Purchase — supplier bill' },
  { value: 'CREDIT_NOTE', label: 'Credit note — sales return or supplier credit' },
  { value: 'DEBIT_NOTE', label: 'Debit note — purchase return or supplier debit' },
  { value: 'RECEIPT', label: 'Receipt — customer settlement or income' },
  { value: 'PAYMENT', label: 'Payment — supplier settlement or expense' },
  { value: 'CONTRA', label: 'Contra — between own cash and bank' },
  { value: 'JOURNAL', label: 'Journal — accrual, provision or correction' },
  { value: 'DELIVERY_NOTE', label: 'Delivery note — dispatch of goods' },
  { value: 'RECEIPT_NOTE', label: 'Receipt note — goods received' },
  { value: 'REJECTIONS_IN', label: 'Rejections in — returned by a customer' },
  { value: 'REJECTIONS_OUT', label: 'Rejections out — returned to a supplier' },
  { value: 'STOCK_JOURNAL', label: 'Stock journal — transfer or adjustment' },
  { value: 'PHYSICAL_STOCK', label: 'Physical stock — counted reconciliation' },
  { value: 'MATERIAL_IN', label: 'Material in — job-work receipt' },
  { value: 'MATERIAL_OUT', label: 'Material out — job-work issue' },
  { value: 'SALES_ORDER', label: 'Sales order — customer commitment with delivery schedule' },
  { value: 'PURCHASE_ORDER', label: 'Purchase order — supplier commitment with receipt schedule' },
  { value: 'JOB_WORK_IN_ORDER', label: 'Job-work order in — work accepted from a principal' },
  { value: 'JOB_WORK_OUT_ORDER', label: 'Job-work order out — work assigned to a subcontractor' },
  { value: 'MEMORANDUM', label: 'Memorandum — provisional internal transaction' },
  { value: 'REVERSING_JOURNAL', label: 'Reversing journal — time-bounded what-if adjustment' },
];

/**
 * Where a voucher type is configured — the one place a kind's derived types are named and changed.
 * The Sales, Purchase and import screens send people to the same address.
 */
export const MANAGE_VOUCHER_TYPES = '/masters/voucher-types';

const SEPARATOR = ' — ';
const entry = (kind: string) => VOUCHER_KINDS.find((candidate) => candidate.value === kind);

/** "Sales", "Credit note" — the short name, and the raw code for a kind this list does not know. */
export function kindLabel(kind: string): string {
  return entry(kind)?.label.split(SEPARATOR)[0] ?? kind;
}

/** What the kind is, capitalised and without a full stop: "Invoice, cash or credit sale". */
export function kindSummary(kind: string): string {
  const [, ...rest] = entry(kind)?.label.split(SEPARATOR) ?? [];
  const summary = rest.join(SEPARATOR);
  return summary.charAt(0).toUpperCase() + summary.slice(1);
}

/** "PRO_FORMA" → "Pro forma". Profiles are the service's codes, so this is only their wording. */
export function profileLabel(profile: string): string {
  const words = profile.toLowerCase().replaceAll('_', ' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export type VoucherKindGroup = {
  key: string;
  title: string;
  description: string;
  kinds: readonly string[];
};

/**
 * The four families of docs/vouchers-plan.md §2.1–2.4, in that order — the same grouping the plan
 * uses, so a reader can follow a card back to the document that defines it. Every kind sits in
 * exactly one group (a test pins the partition), which is what keeps a card from being listed
 * twice or not at all when the vocabulary grows.
 */
export const VOUCHER_KIND_GROUPS: readonly VoucherKindGroup[] = [
  {
    key: 'accounting',
    title: 'Accounting',
    description: 'Invoices, notes, receipts, payments and journals.',
    kinds: ['SALES', 'PURCHASE', 'CREDIT_NOTE', 'DEBIT_NOTE', 'RECEIPT', 'PAYMENT', 'CONTRA', 'JOURNAL'],
  },
  {
    key: 'inventory',
    title: 'Inventory',
    description: 'Delivery and receipt notes, returns, stock journals and job-work material.',
    kinds: [
      'DELIVERY_NOTE',
      'RECEIPT_NOTE',
      'REJECTIONS_IN',
      'REJECTIONS_OUT',
      'STOCK_JOURNAL',
      'PHYSICAL_STOCK',
      'MATERIAL_IN',
      'MATERIAL_OUT',
    ],
  },
  {
    key: 'orders',
    title: 'Orders and commitments',
    description: 'Orders placed with or accepted from others, before anything is fulfilled.',
    kinds: ['SALES_ORDER', 'PURCHASE_ORDER', 'JOB_WORK_IN_ORDER', 'JOB_WORK_OUT_ORDER'],
  },
  {
    key: 'general',
    title: 'General and non-posting',
    description: 'Internal documents that never reach the books.',
    kinds: ['MEMORANDUM', 'REVERSING_JOURNAL'],
  },
];

/**
 * The URL segment for a kind: `CREDIT_NOTE` → `credit-note`, matching `/vouchers/new/stock-adjustment`
 * and the rest of the console's kebab-case paths.
 */
export function kindSlug(kind: string): string {
  return kind.toLowerCase().replaceAll('_', '-');
}

/** The kind a URL segment names, or `null` — never a guess, so an unknown segment is a 404. */
export function kindFromSlug(slug: string): string | null {
  return VOUCHER_KINDS.find((candidate) => kindSlug(candidate.value) === slug)?.value ?? null;
}
