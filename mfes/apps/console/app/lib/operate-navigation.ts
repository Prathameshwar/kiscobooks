import { kindFromSlug, kindLabel, kindSlug, kindSummary } from './voucher-kinds';
import { isTypeId } from './voucher-type-routes';

export type OperateFamily = { key: string; title: string; description: string; kinds: readonly string[] };
export type OperateArea = { key: string; title: string; description: string; families: readonly OperateFamily[] };
const adjustments: OperateFamily = { key: 'adjustments', title: 'Adjustments', description: 'Journals, provisions and internal adjustments.', kinds: ['JOURNAL', 'REVERSING_JOURNAL', 'MEMORANDUM'] };
export const OPERATE_AREAS: readonly OperateArea[] = [
  { key: 'income', title: 'Income', description: 'Sales, customer receipts and related vouchers.', families: [
    { key: 'sales', title: 'Sales', description: 'Invoices, customer returns, orders and dispatches.', kinds: ['SALES', 'CREDIT_NOTE', 'SALES_ORDER', 'DELIVERY_NOTE'] },
    { key: 'receipts', title: 'Receipts', description: 'Customer settlements and other money received.', kinds: ['RECEIPT'] }, adjustments,
  ] },
  { key: 'expense', title: 'Expense', description: 'Purchases, supplier payments and related vouchers.', families: [
    { key: 'purchase', title: 'Purchase', description: 'Supplier bills, purchase returns, notes, orders and goods received.', kinds: ['PURCHASE', 'DEBIT_NOTE', 'CREDIT_NOTE', 'PURCHASE_ORDER', 'RECEIPT_NOTE'] },
    { key: 'payments', title: 'Payments', description: 'Supplier settlements and other money paid.', kinds: ['PAYMENT'] },
    { key: 'transfers', title: 'Cash and bank transfers', description: 'Move money between your own cash and bank accounts.', kinds: ['CONTRA'] }, adjustments,
  ] },
  { key: 'inventory', title: 'Inventory', description: 'Goods movements, stock adjustments and job work.', families: [
    { key: 'receiving', title: 'Goods received', description: 'Receive goods and return rejected goods to suppliers.', kinds: ['RECEIPT_NOTE', 'REJECTIONS_OUT'] },
    { key: 'dispatch', title: 'Goods dispatched', description: 'Dispatch goods and receive customer rejections.', kinds: ['DELIVERY_NOTE', 'REJECTIONS_IN'] },
    { key: 'stock', title: 'Stock adjustments', description: 'Transfers, adjustments and counted stock reconciliation.', kinds: ['STOCK_JOURNAL', 'PHYSICAL_STOCK'] },
    { key: 'job-work', title: 'Job work', description: 'Material movements and work accepted or assigned.', kinds: ['MATERIAL_IN', 'MATERIAL_OUT', 'JOB_WORK_IN_ORDER', 'JOB_WORK_OUT_ORDER'] },
  ] },
];
export const operateArea = (key: string) => OPERATE_AREAS.find(area => area.key === key);
export const operateFamily = (area: OperateArea, key: string) => area.families.find(family => family.key === key);
export const areaHref = (area: OperateArea) => '/operate/' + area.key;
export const familyHref = (area: OperateArea, family: OperateFamily) => areaHref(area) + '/' + family.key;
export const listHref = (area: OperateArea, family: OperateFamily, kind: string, typeId?: string) =>
  familyHref(area, family) + '/' + kindSlug(kind) + (typeId ? '?type_id=' + typeId : '');
export function workflowLabel(area: OperateArea, kind: string): string {
  if (kind === 'DEBIT_NOTE' && area.key === 'expense') return 'Purchase returns / debit notes';
  if (kind === 'CREDIT_NOTE') return area.key === 'expense' ? 'Supplier credit notes' : 'Sales returns / credit notes';
  return kindLabel(kind);
}
export const cardMatches = (query: string, ...values: (string | null | undefined)[]) =>
  !query.trim() || values.some(value => value?.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
export const familyMatches = (family: OperateFamily, query: string) => cardMatches(query, family.title, family.description, ...family.kinds.flatMap(kind => [kindLabel(kind), kindSummary(kind)]));

/** Local, known Operate destinations only; never trust a redirect supplied in a URL. */
export function operateReturn(value: unknown): string | undefined {
  if (typeof value !== 'string' || value.length > 500 || !value.startsWith('/operate/') || /[\\#%]/.test(value)) return undefined;
  const url = new URL(value, 'https://console.invalid');
  if (value !== url.pathname + url.search) return undefined;
  const segments = url.pathname.split('/').slice(2);
  const area = operateArea(segments[0]);
  if (!area || segments.length > 3) return undefined;
  const family = segments[1] ? operateFamily(area, segments[1]) : undefined;
  if (segments.length > 1 && !family) return undefined;
  const kind = segments[2] ? kindFromSlug(segments[2]) : undefined;
  if (segments.length > 2 && (!kind || !family?.kinds.includes(kind))) return undefined;
  const entries = [...url.searchParams.entries()];
  if (entries.length && (segments.length !== 3 || entries.length !== 1 || entries[0][0] !== 'type_id' || !isTypeId(entries[0][1]))) return undefined;
  return url.pathname + url.search;
}
export function withReturn(href: string, returnTo?: string): string {
  const safe = operateReturn(returnTo);
  if (!safe) return href;
  return href + (href.includes('?') ? '&' : '?') + new URLSearchParams({ returnTo: safe });
}
/** The kinds that have their own complete entry screen, at `/vouchers/new/<kind>`. */
export const NATIVE_ENTRY_KINDS = ['SALES', 'PURCHASE'] as const;
const isNativeEntry = (kind?: string): kind is (typeof NATIVE_ENTRY_KINDS)[number] => !!kind && (NATIVE_ENTRY_KINDS as readonly string[]).includes(kind);

/**
 * Where a new voucher of a kind (and optionally one company type) is entered. Sales and Purchase have
 * exactly one screen each, `/vouchers/new/<kind>`, whoever sends you there — the top-bar New menu, a
 * saved draft, or an Operate list; every other kind uses the generic selection route. The Back target
 * is only ever a known Operate destination (`operateReturn`).
 */
export function newVoucherHref(kind?: string, typeId?: string, returnTo?: string): string {
  const params = new URLSearchParams();
  if (!isNativeEntry(kind) && kind) params.set('kind', kind);
  if (typeId) params.set('type_id', typeId);
  const base = isNativeEntry(kind) ? '/vouchers/new/' + kind.toLowerCase() : '/vouchers/entry';
  const query = params.toString();
  return withReturn(base + (query ? '?' + query : ''), returnTo);
}
export const IMPORT_KINDS: Readonly<Record<string, string>> = { PURCHASE: 'Purchase', SALES: 'Sales', CREDIT_NOTE: 'Credit note', DEBIT_NOTE: 'Debit note', PAYMENT: 'Payment', RECEIPT: 'Receipt', CONTRA: 'Contra', JOURNAL: 'Journal' };

export type VoucherSelection = { kind?: string | string[]; type_id?: string | string[]; returnTo?: string | string[] };
export function voucherSelection(query?: VoucherSelection): { kind?: string; typeId?: string; returnTo?: string } | null {
  const kind = query?.kind, typeId = query?.type_id;
  if (kind !== undefined && (typeof kind !== 'string' || kindFromSlug(kind.toLowerCase().replaceAll('_', '-')) !== kind)) return null;
  if (typeId !== undefined && (typeof typeId !== 'string' || !isTypeId(typeId) || !kind)) return null;
  return { kind, typeId, returnTo: operateReturn(query?.returnTo) };
}
