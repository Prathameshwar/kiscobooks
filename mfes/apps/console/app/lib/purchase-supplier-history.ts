import * as D from './fixed-decimal';
import { trackingId } from './stock-tracking-resources';
import type { ServiceRequest } from './service-call';

type Reader = <T>(request: ServiceRequest) => Promise<T>;
export type SupplierPurchaseRow = { id: string; invoice: string | null; date: string | null; amount: string | null; currency: string | null; status: string };
export type SupplierPurchaseLine = { key: string; description: string; quantity: string | null; price: string | null; priceFor: string | null; includesTax: boolean; amount: string | null; kind: 'ITEM' | 'ACCOUNT' };
export type SupplierPurchaseDetail = { lines: SupplierPurchaseLine[] };
const date = /^\d{4}-\d{2}-\d{2}$/;
const amount = (value: unknown): value is string => typeof value === 'string' && D.parse(value) !== null;

/** Vouchers orders the list; product history pages by 10, supplier history by 25. */
export async function readSupplierPurchases(read: Reader, company: string, supplier: string | null, signal: AbortSignal, cursor?: string, item?: string): Promise<{ items: SupplierPurchaseRow[]; next: string | null }> {
  if (!trackingId.test(company) || supplier !== null && !trackingId.test(supplier) || supplier === null && !item || item && !trackingId.test(item) || cursor && cursor.length > 4096) throw Error('Invalid supplier history request.');
  const limit = item ? 10 : 25;
  const query = new URLSearchParams({ kind: 'PURCHASE', ...(supplier ? { party_id: supplier } : {}), sort: '-document_date', limit: String(limit), ...(item ? { item_id: item } : {}), ...(cursor ? { cursor } : {}) });
  const page = await read<{ items?: unknown; page?: { next_cursor?: unknown } }>({ service: 'vouchers', path: `/v1/companies/${company}/vouchers?${query}`, signal });
  if (!Array.isArray(page?.items) || page.items.length > limit || !page.page || page.page.next_cursor != null && (typeof page.page.next_cursor !== 'string' || page.page.next_cursor.length > 4096 || page.page.next_cursor === cursor)) throw Error('Supplier purchase history could not be verified.');
  const items = page.items.map(raw => {
    const row = raw as Record<string, unknown>;
    if (row.company_id !== company || row.kind !== 'PURCHASE' || typeof row.id !== 'string' || !trackingId.test(row.id)
      || !['DRAFT', 'SUBMITTED', 'APPROVED', 'REJECTED', 'CANCELLED', 'POSTED', 'REVERSED'].includes(String(row.status)) || row.document_date != null && (typeof row.document_date !== 'string' || !date.test(row.document_date))
      || row.ref_number != null && (typeof row.ref_number !== 'string' || row.ref_number.length > 120)
      || row.amount != null && !amount(row.amount) || row.currency != null && (typeof row.currency !== 'string' || !/^[A-Z]{3}$/.test(row.currency))) throw Error('Supplier purchase history could not be verified.');
    return { id: row.id, invoice: row.ref_number as string | null ?? null, date: row.document_date as string | null ?? null,
      amount: row.amount as string | null ?? null, currency: row.currency as string | null ?? null, status: row.status as string };
  });
  if (new Set(items.map(row => row.id)).size !== items.length) throw Error('Supplier purchase history contains duplicate invoices.');
  return { items, next: page.page.next_cursor as string | null ?? null };
}

/** Read the one voucher the person opened; never fetch product details for every list row. */
export async function readSupplierPurchaseDetail(read: Reader, company: string, supplier: string, id: string, signal: AbortSignal): Promise<SupplierPurchaseDetail> {
  if (![company, supplier, id].every(value => trackingId.test(value))) throw Error('Invalid purchase reference.');
  const voucher = await read<Record<string, unknown>>({ service: 'vouchers', path: `/v1/companies/${company}/vouchers/${id}`, signal });
  if (!voucher || voucher.id !== id || voucher.company_id !== company || voucher.kind !== 'PURCHASE' || !Array.isArray(voucher.parties)
    || !voucher.parties.some(raw => { const party = raw as Record<string, unknown>; return party.role === 'SUPPLIER' && party.party_id === supplier; })) throw Error('Purchase detail does not belong to this supplier.');
  const invoice = voucher.invoice as { supplies?: unknown } | null;
  if (!invoice || !Array.isArray(invoice.supplies)) throw Error('Purchase line details are not readable.');
  const common = new Map((Array.isArray(voucher.lines) ? voucher.lines : []).map(raw => { const line = raw as Record<string, unknown>; return [line.line_key, line]; }));
  const lines = invoice.supplies.map(raw => {
    const supply = raw as Record<string, unknown>, kind = supply.supply_kind === 'GOODS' ? 'ITEM' : 'ACCOUNT';
    if (typeof supply.line_key !== 'string' || !trackingId.test(supply.line_key) || typeof supply.description !== 'string'
      || supply.amount != null && !amount(supply.amount) || supply.unit_price != null && !amount(supply.unit_price)) throw Error('Purchase line details could not be verified.');
    const item = kind === 'ITEM' ? common.get(supply.item_line_key ?? supply.line_key)?.item as Record<string, unknown> | undefined : undefined;
    const billed = item?.billed_quantity;
    const denominator = supply.price_denominator == null ? '1' : String(supply.price_denominator);
    if (!amount(denominator) || D.parse(denominator)! <= 0n || supply.price_basis != null && !['NET_EXCL_TAX', 'GROSS_INCL_TAX'].includes(String(supply.price_basis))) throw Error('Product price details could not be verified.');
    if (kind === 'ITEM' && (!item || typeof item.item_id !== 'string' || !trackingId.test(item.item_id) || !amount(billed))) throw Error('Product quantity could not be verified.');
    return { key: supply.line_key, description: supply.description.trim() || (kind === 'ITEM' ? 'Product' : 'Account / service'),
      quantity: kind === 'ITEM' ? billed as string : null, price: kind === 'ITEM' && amount(supply.unit_price) ? supply.unit_price : null,
      priceFor: kind === 'ITEM' && D.parse(denominator)! !== D.ONE ? denominator : null, includesTax: supply.price_basis === 'GROSS_INCL_TAX',
      amount: amount(supply.amount) ? supply.amount : null, kind } satisfies SupplierPurchaseLine;
  });
  if (new Set(lines.map(line => line.key)).size !== lines.length) throw Error('Purchase line details contain duplicates.');
  return { lines };
}
