import { productFieldRequest as request } from './product-fields';
import { trackingId } from './stock-tracking-resources';
import type { PurchaseLine, PurchaseStock } from './purchase-workspace';

export type PurchaseTracking = { itemId: string; companyId: string; profileRevisionId: string; lotTracking: boolean; serialTracking: boolean;
  expiryRequired?: boolean; manufactureDateRequired?: boolean; shelfLifeDays?: number | null; minimumRemainingLifeDays?: number | null };

export async function purchaseTracking(company: string, item: string): Promise<PurchaseTracking> {
  if (!trackingId.test(company) || !trackingId.test(item)) throw Error('Select a valid company and product.');
  const value = await request<{ company_id: string; item_id: string; profile_revision_id: string; lot_tracking: boolean; serial_tracking: boolean;
    expiry_required: boolean; manufacture_date_required: boolean; shelf_life_days: number | null; minimum_remaining_life_days: number | null }>(
    'accounting', 'GET', `/v1/companies/${company}/stock-tracking/context/${item}?resource=stock`);
  if (value.company_id !== company || value.item_id !== item || !trackingId.test(value.profile_revision_id)
    || typeof value.lot_tracking !== 'boolean' || typeof value.serial_tracking !== 'boolean'
    || typeof value.expiry_required !== 'boolean' || typeof value.manufacture_date_required !== 'boolean'
    || value.shelf_life_days !== null && (!Number.isSafeInteger(value.shelf_life_days) || value.shelf_life_days < 1)
    || value.minimum_remaining_life_days !== null && (!Number.isSafeInteger(value.minimum_remaining_life_days) || value.minimum_remaining_life_days < 0)) throw Error('The product tracking requirements could not be verified.');
  return { itemId: item, companyId: company, profileRevisionId: value.profile_revision_id, lotTracking: value.lot_tracking, serialTracking: value.serial_tracking,
    expiryRequired: value.expiry_required, manufactureDateRequired: value.manufacture_date_required, shelfLifeDays: value.shelf_life_days,
    minimumRemainingLifeDays: value.minimum_remaining_life_days };
}

export type PurchaseBatch = { id: string; company_id: string; item_id: string; code: string | null; status: string | null;
  is_held?: boolean | null; manufactured_on: string | null; expires_on: string | null };
export type PurchaseBatchDraft = { code: string; manufacturedOn: string; expiresOn: string; reason: string };
const day = (value: string) => /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;
export function purchaseBatchEligibility(batch: Pick<PurchaseBatch, 'status' | 'is_held' | 'expires_on'>, profile: PurchaseTracking, postingDate: string): string | null {
  if (batch.status !== 'ACTIVE' || batch.is_held !== false) return 'This batch is not active and available for receiving.';
  if (profile.expiryRequired && !batch.expires_on) return 'This product requires an expiry date on the batch.';
  if (batch.expires_on && day(postingDate)) {
    const remaining = (Date.parse(batch.expires_on) - Date.parse(postingDate)) / 86400000;
    if (!Number.isInteger(remaining) || remaining < 0) return 'This batch expires before the purchase posting date.';
    if (remaining < (profile.minimumRemainingLifeDays ?? 0)) return 'This batch does not meet the required remaining shelf life.';
  }
  return null;
}

export function purchaseBatchProblems(draft: PurchaseBatchDraft, profile: PurchaseTracking, postingDate?: string): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!draft.code.trim() || draft.code.trim().length > 100) errors.code = 'Enter a batch code of at most 100 characters.';
  if (profile.manufactureDateRequired && !draft.manufacturedOn) errors.manufacturedOn = 'Manufacture date is required for this product.';
  if (profile.expiryRequired && !draft.expiresOn) errors.expiresOn = 'Expiry date is required for this product.';
  if (draft.manufacturedOn && !day(draft.manufacturedOn)) errors.manufacturedOn = 'Enter a valid manufacture date.';
  if (draft.expiresOn && !day(draft.expiresOn)) errors.expiresOn = 'Enter a valid expiry date.';
  if (draft.manufacturedOn && draft.expiresOn && day(draft.manufacturedOn) && day(draft.expiresOn)) {
    if (draft.expiresOn < draft.manufacturedOn) errors.expiresOn = 'Expiry cannot precede manufacture.';
    else if (profile.shelfLifeDays != null && (Date.parse(draft.expiresOn) - Date.parse(draft.manufacturedOn)) / 86400000 > profile.shelfLifeDays) errors.expiresOn = 'Expiry exceeds the configured shelf life.';
  }
  if (!errors.expiresOn && draft.expiresOn && postingDate && day(postingDate)) {
    const eligibility = purchaseBatchEligibility({ status: 'ACTIVE', is_held: false, expires_on: draft.expiresOn }, profile, postingDate);
    if (eligibility) errors.expiresOn = eligibility;
  }
  if (draft.reason.trim().length < 3 || draft.reason.trim().length > 500) errors.reason = 'Enter a reason of 3 to 500 characters.';
  return errors;
}

export async function purchaseBatch(company: string, item: string, id: string, signal?: AbortSignal): Promise<PurchaseBatch> {
  if (![company, item, id].every(value => trackingId.test(value))) throw Error('Select a valid company, product and batch.');
  const value = await request<PurchaseBatch>('accounting', 'GET', `/v1/companies/${company}/stock-tracking/batches/${id}`, undefined, undefined, signal);
  if (value.id !== id || value.company_id !== company || value.item_id !== item || value.status !== 'ACTIVE' || value.is_held !== false) throw Error('The batch is not available for this product and company.');
  return value;
}

export async function preparePurchaseBatch(company: string, item: string, draft: PurchaseBatchDraft, profile: PurchaseTracking, key: string, postingDate?: string): Promise<PurchaseBatch> {
  if (![company, item].every(value => trackingId.test(value)) || profile.companyId !== company || profile.itemId !== item || !profile.lotTracking) throw Error('The product batch requirements could not be verified.');
  const errors = purchaseBatchProblems(draft, profile, postingDate);
  if (Object.keys(errors).length) throw Error(Object.values(errors)[0]);
  const value = await request<PurchaseBatch>('accounting', 'POST', `/v1/companies/${company}/stock-tracking/batches`, {
    item_id: item, code: draft.code.trim(), manufactured_on: draft.manufacturedOn || null, expires_on: draft.expiresOn || null, reason: draft.reason.trim(),
  }, key);
  if (!trackingId.test(value.id) || value.company_id !== company || value.item_id !== item || value.status !== 'ACTIVE' || value.is_held !== false
    || value.code !== draft.code.trim() || value.expires_on !== (draft.expiresOn || null)
    || value.manufactured_on !== (draft.manufacturedOn || null)) throw Error('The prepared batch could not be verified.');
  return value;
}

export function purchaseStockLine(line: PurchaseLine, fallbackWarehouse: string, profile: PurchaseTracking, seen: Set<string>, ordinal: number): PurchaseStock {
  const prefix = `Purchase line ${ordinal}: `;
  if (line.kind !== 'ITEM' || line.subject !== profile.itemId || !trackingId.test(profile.companyId)) throw Error(prefix + 'verify the selected product.');
  const chosen = line.stock;
  const warehouseId = chosen?.warehouseId || fallbackWarehouse;
  const binId = chosen?.binId ?? '', lotId = chosen?.lotId ?? '', unitIds = chosen?.unitIds ?? [];
  if (!trackingId.test(warehouseId)) throw Error(prefix + 'select a warehouse.');
  if (binId && !trackingId.test(binId)) throw Error(prefix + 'select a valid bin.');
  if (profile.lotTracking ? !trackingId.test(lotId) : !!lotId) throw Error(prefix + (profile.lotTracking ? 'select a prepared batch.' : 'this product does not use batches.'));
  if (!profile.serialTracking && unitIds.length) throw Error(prefix + 'this product does not use serials.');
  if (unitIds.length > 200 || unitIds.some(id => !trackingId.test(id) || seen.has(id)) || new Set(unitIds).size !== unitIds.length) throw Error(prefix + 'select distinct prepared serials, at most 200 per line.');
  if (profile.serialTracking) {
    const quantity = line.billed || line.received;
    if (!/^[1-9]\d*(?:\.0{1,4})?$/.test(quantity) || BigInt(quantity.split('.')[0]!) !== BigInt(unitIds.length)) throw Error(prefix + 'select one prepared serial for each physical unit.');
  }
  unitIds.forEach(id => seen.add(id));
  return { warehouseId, binId, lotId, unitIds: [...unitIds] };
}
