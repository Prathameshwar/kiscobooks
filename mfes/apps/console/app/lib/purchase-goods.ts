import { roundDecimalString, type RoundingMode, type SearchSelectLoader } from '@janso/ui';
import { productFieldRequest as request } from './product-fields';
import { trackingId } from './stock-tracking-resources';
import * as D from './fixed-decimal';
import type { PurchaseLine } from './purchase-workspace';

/**
 * Goods on a Purchase bill (B24): the bill itself brings them into stock. Accounting values each
 * line at its landed cost from the accepted calculation; nothing here prices stock or reads a rate.
 */
export type PurchaseItem = { id: string; company: string; version: number; baseUnitId: string; label: string; unit: string; sku?: string };
/** Where goods post and land: the stock accounts' inventory account on the posting date, and the purchase warehouse. */
export type PurchaseGoodsContext = { inventory: { id: string; version: number }; warehouse: string };
/** The company's amount rounding, which Accounting prices a quantity × rate line with. */
export type PurchaseRounding = { places: number; mode: RoundingMode };
/** A bill's stock movement carries at most this many goods lines. */
export const PURCHASE_GOODS_LINE_LIMIT = 100;

const fail = (message: string): never => { throw new Error(message); };
const version = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= 1;
type Page<T> = { items: T[]; page: { next_cursor: string | null } };
type ItemRow = { id: string; company_id?: string; name?: string | null; sku?: string | null; base_unit_id?: string; row_version?: number; status?: string; purchasable?: boolean };

/** Active purchasable products of this company, by name or code. */
export function purchaseItemLookup(company: string): SearchSelectLoader {
  return async ({ q, cursor, signal }) => {
    const params = new URLSearchParams({ status: 'ACTIVE', purchasable: 'true', limit: '25', ...(q.trim() ? { q: q.trim().slice(0, 200) } : {}), ...(cursor ? { cursor } : {}) });
    const page = await request<Page<ItemRow>>('catalog', 'GET', `/v1/companies/${company}/items?${params}`, undefined, undefined, signal);
    if (!Array.isArray(page.items) || page.items.length > 25 || !page.page || page.page.next_cursor !== null && typeof page.page.next_cursor !== 'string' || page.items.some(row => !trackingId.test(row.id) || row.company_id && row.company_id !== company)) fail('The product list could not be verified.');
    return { items: page.items.map(row => ({ id: row.id, label: row.name ?? row.sku ?? 'Product', ...(row.sku ? { meta: row.sku } : {}) })), nextCursor: page.page.next_cursor };
  };
}

/** A chosen product, verified: active, purchasable, in this company, with its base unit. */
export async function purchaseItem(company: string, id: string): Promise<PurchaseItem> {
  if (!trackingId.test(id)) fail('Select a valid product.');
  const row = await request<ItemRow>('catalog', 'GET', `/v1/companies/${company}/items/${id}`);
  if (row.id !== id || row.company_id !== company || !version(row.row_version) || !trackingId.test(row.base_unit_id ?? '')) fail('The selected product is unavailable for this company.');
  if (row.status !== 'ACTIVE') fail('Activate this product before buying it: open the product and choose Review and activate.');
  if (row.purchasable === false) fail('This product is not set up to be purchased.');
  // The unit's symbol is a label only; a bill whose unit name cannot be read still records the unit's identity.
  let unit = '';
  try {
    const value = await request<{ id: string; symbol?: string | null; code?: string | null }>('catalog', 'GET', `/v1/companies/${company}/units/${row.base_unit_id}`);
    if (value.id === row.base_unit_id) unit = value.symbol ?? value.code ?? '';
  } catch { /* Shown without its unit name. */ }
  return { id, company, version: row.row_version!, baseUnitId: row.base_unit_id!, label: row.name ?? row.sku ?? id, unit, ...(row.sku ? { sku: row.sku } : {}) };
}

/** The company's inventory account on the posting date and its purchase warehouse. */
export async function purchaseGoodsContext(company: string, postingDate: string): Promise<PurchaseGoodsContext> {
  const policies = await request<Page<{ id: string; valid_from: string; valid_to?: string | null }>>('accounting', 'GET', `/v1/companies/${company}/stock/account-policies?limit=50&sort=-id`);
  const current = (policies.items ?? []).filter(row => row.valid_from <= postingDate && (!row.valid_to || row.valid_to >= postingDate));
  if (current.length !== 1 || !trackingId.test(current[0]!.id)) fail('Set up the company’s stock accounts (Inventory → Stock accounts) before billing goods.');
  const policy = await request<{ id: string; company_id: string; inventory_account_id: string }>('accounting', 'GET', `/v1/companies/${company}/stock/account-policies/${current[0]!.id}`);
  if (policy.company_id !== company || !trackingId.test(policy.inventory_account_id)) fail('The stock accounts could not be verified.');
  const account = await request<{ id: string; company_id: string; row_version: number; status?: string }>('accounting', 'GET', `/v1/companies/${company}/accounts/${policy.inventory_account_id}`);
  if (account.id !== policy.inventory_account_id || account.company_id !== company || !version(account.row_version) || account.status !== 'ACTIVE') fail('The inventory account is unavailable.');
  const configuration = await request<{ company_id: string; main_warehouse_id?: string | null; default_purchase_warehouse_id?: string | null }>('catalog', 'GET', `/v1/companies/${company}/warehouse-configuration`);
  const warehouse = configuration.default_purchase_warehouse_id ?? configuration.main_warehouse_id ?? '';
  if (configuration.company_id !== company || !trackingId.test(warehouse)) fail('Set up the company’s warehouses before billing goods.');
  return { inventory: { id: account.id, version: account.row_version }, warehouse };
}

const quantity = /^(?:0|[1-9]\d{0,14})(?:\.\d{1,4})?$/;

/** `quantity × rate`, rounded once to the company's amount places, exactly as Accounting prices the line. */
export function pricedAmount(quantity: D.Fixed, rate: D.Fixed, rounding: PurchaseRounding): D.Fixed {
  const product = quantity * rate, scale = 10n ** 8n;
  const exact = (product / scale).toString() + '.' + (product % scale).toString().padStart(8, '0');
  return D.parse(roundDecimalString(exact, rounding.places, rounding.mode))!;
}

/** A goods line's checked inputs: what it receives and bills (one quantity, in the base unit) and its price. */
export function goodsLine(line: PurchaseLine, item: PurchaseItem | undefined, rounding: PurchaseRounding, index: number): { quantity: string; rate: string; amount: string } {
  const prefix = 'Purchase line ' + (index + 1) + ': ';
  if (!item) fail(prefix + 'select a verified active product.');
  const received = line.billed || line.received;
  if (!quantity.test(received) || D.parse(received) === 0n) fail(prefix + 'enter a quantity greater than zero, with at most four decimal places.');
  if (line.received && line.billed && D.parse(line.received) !== D.parse(line.billed)) fail(prefix + 'a bill that brings goods in bills what it receives; record a shortage on a Receipt Note instead.');
  if (!quantity.test(line.rate)) fail(prefix + 'enter a rate with at most four decimal places.');
  const amount = pricedAmount(D.parse(received)!, D.parse(line.rate)!, rounding);
  if (amount <= 0n) fail(prefix + 'the line amount must be greater than zero.');
  return { quantity: D.format(D.parse(received)!), rate: D.format(D.parse(line.rate)!), amount: D.format(amount) };
}
