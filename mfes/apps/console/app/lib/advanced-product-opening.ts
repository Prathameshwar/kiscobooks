import type { components } from '@janso/api-client/catalog';
import type { AdvancedOptions, AdvancedWork, ProductSkuValues } from './advanced-product-draft';
import { businessSku } from './advanced-product-business';
export type OpeningSerial = { key: string; identifiers: components['schemas']['IdentifierInput'][] };
export type OpeningBatch = { key: string; code: string; opening_quantity: string; purchase_price: string; sale_prices: Record<string, string>; manufactured_on: string; expires_on: string; mrp: string; serials: OpeningSerial[] };
export type OpeningSku = { decision: 'SKIP' | 'OPEN'; opening_date: string; warehouse_id: string; opening_quantity: string; purchase_price: string; batches: OpeningBatch[]; serials: OpeningSerial[] };
export const emptyOpening = (): OpeningSku => ({ decision: 'SKIP', opening_date: '', warehouse_id: '', opening_quantity: '', purchase_price: '', batches: [], serials: [] });
export function openingSku(work: AdvancedWork, sku: ProductSkuValues): OpeningSku {
  const rows = work.opening.skus;
  const saved = rows && typeof rows === 'object' && !Array.isArray(rows) ? (rows as Record<string, unknown>)[sku.key] : null;
  const value = saved && typeof saved === 'object' && !Array.isArray(saved) ? saved as Record<string, unknown> : {};
  const string = (part: unknown) => typeof part === 'string' ? part : '';
  const serials = (part: unknown): OpeningSerial[] => Array.isArray(part) ? part.map(row => ({ key: string(row.key) || crypto.randomUUID(), identifiers: Array.isArray(row.identifiers) ? row.identifiers as OpeningSerial['identifiers'] : [] })) : [];
  return { decision: value.decision === 'OPEN' ? 'OPEN' : 'SKIP', opening_date: string(value.opening_date), warehouse_id: string(value.warehouse_id), opening_quantity: string(value.opening_quantity), purchase_price: string(value.purchase_price), batches: Array.isArray(value.batches) ? value.batches.map(row => ({ key: string(row.key) || crypto.randomUUID(), code: string(row.code), opening_quantity: string(row.opening_quantity), purchase_price: string(row.purchase_price), sale_prices: row.sale_prices && typeof row.sale_prices === 'object' && !Array.isArray(row.sale_prices) ? Object.fromEntries(Object.entries(row.sale_prices).map(([key, amount]) => [key, string(amount)])) : {}, manufactured_on: string(row.manufactured_on), expires_on: string(row.expires_on), mrp: string(row.mrp), serials: serials(row.serials) })) : [], serials: serials(value.serials) };
}
export function putOpening(work: AdvancedWork, sku: ProductSkuValues, next: OpeningSku): AdvancedWork {
  const old = work.opening.skus && typeof work.opening.skus === 'object' && !Array.isArray(work.opening.skus) ? work.opening.skus as Record<string, unknown> : {};
  return { ...work, opening: { ...work.opening, skus: { ...old, [sku.key]: next } } };
}
export function openingApplicable(work: AdvancedWork, options: AdvancedOptions): boolean {
  return work.profile.kind === 'GOODS' && !!options.books_begin_date && options.books_begin_date <= options.today && options.inventory_enabled && (options.selected_type?.inventory_modes.includes('STOCK') ?? false);
}
const decimal = /^(?:0|[1-9]\d{0,14})(?:\.\d{1,4})?$/;
const positive = (value: string) => decimal.test(value) && /[1-9]/.test(value);
export function openingErrors(work: AdvancedWork, options: AdvancedOptions): Record<string, string> {
  const errors: Record<string, string> = {};
  work.skus.forEach((sku, index) => {
    const value = openingSku(work, sku);
    const path = `opening.skus.${index}.`;
    if (value.decision === 'SKIP') return;
    if (!openingApplicable(work, options)) errors[path + 'decision'] = 'Opening stock is not available for this product.';
    if (!/^\d{4}-\d\d-\d\d$/.test(value.opening_date) || value.opening_date !== options.books_begin_date) errors[path + 'opening_date'] = 'Use the company books-begin date for opening stock.';
    if (value.batches.length > 64) errors[path + 'batches'] = 'Use at most 64 batches.';
    const batchSelected = options.batch?.available && (businessSku(work, sku).batch_enabled || options.batch?.required);
    if (batchSelected && !value.batches.length) errors[path + 'batches'] = 'Add at least one opening batch.';
    if (!batchSelected && value.batches.length) errors[path + 'batches'] = 'Batch opening is not enabled for this SKU.';
    if (value.batches.length) {
      if (!options.batch?.available) errors[path + 'batches'] = 'Batch opening is not available.';
      if (value.opening_quantity || value.purchase_price || value.serials.length) errors[path + 'batches'] = 'Enter quantity, cost and serials on batch rows.';
      const seen = new Set<string>();
      value.batches.forEach((row, at) => {
        const batchPath = `${path}batches.${at}.`;
        if (!row.code.trim()) errors[batchPath + 'code'] = 'Enter a batch code.';
        if (seen.has(row.code.trim().toLocaleLowerCase())) errors[batchPath + 'code'] = 'Batch codes must be distinct.';
        seen.add(row.code.trim().toLocaleLowerCase());
        if (!positive(row.opening_quantity)) errors[batchPath + 'opening_quantity'] = 'Enter a positive batch quantity.';
        if (!decimal.test(row.purchase_price)) errors[batchPath + 'purchase_price'] = 'Enter an exact purchase cost.';
        if (options.batch?.manufacture_date_required && !row.manufactured_on) errors[batchPath + 'manufactured_on'] = 'Enter the manufacture date.';
        if (options.batch?.expiry_required && !row.expires_on) errors[batchPath + 'expires_on'] = 'Enter the expiry date.';
        if (row.manufactured_on && row.expires_on && row.expires_on < row.manufactured_on) errors[batchPath + 'expires_on'] = 'Expiry must follow manufacture.';
        if (options.serial?.enabled && Number(row.opening_quantity) !== row.serials.length) errors[batchPath + 'serials'] = 'Serial units must equal batch quantity.';
        for (const level of options.sale_price_levels ?? []) {
          const amount = row.sale_prices[level.price_level_id] ?? '';
          if ((level.required && !decimal.test(amount)) || (amount && !decimal.test(amount))) errors[batchPath + 'sale_prices.' + level.price_level_id] = `Enter an exact ${level.name} batch price.`;
        }
        if (options.defaults.configuration.pricing.mrp_mode === 'REQUIRED' && !positive(row.mrp)) errors[batchPath + 'mrp'] = 'Enter a positive physical MRP.';
        if (row.mrp && (!positive(row.mrp) || options.defaults.configuration.pricing.mrp_mode === 'DISABLED')) errors[batchPath + 'mrp'] = 'Enter an allowed positive physical MRP.';
      });
    } else {
      if (!positive(value.opening_quantity)) errors[path + 'opening_quantity'] = 'Enter a positive opening quantity.';
      if (!decimal.test(value.purchase_price)) errors[path + 'purchase_price'] = 'Enter an exact purchase cost.';
      if (options.serial?.enabled && Number(value.opening_quantity) !== value.serials.length) errors[path + 'serials'] = 'Add one physical serial unit for each opening unit.';
    }
    const all = [...value.serials, ...value.batches.flatMap(batch => batch.serials)];
    if (all.length > 200) errors[path + 'serials'] = 'Use at most 200 serial units.';
    const identifiers = new Set<string>();
    all.forEach((serial, at) => {
      for (const requirement of options.serial?.requirements ?? []) {
        const entered = serial.identifiers.filter(item => item.identifier_type === requirement.identifier_type);
        if (entered.length < requirement.min_count || entered.length > requirement.max_count) errors[path + `serials.${at}`] = `Enter the required ${requirement.identifier_type} identifier count.`;
      }
      serial.identifiers.forEach(item => { const key = item.identifier_type + ':' + item.value.normalize('NFKC').toLocaleLowerCase(); if (!item.value.trim() || identifiers.has(key)) errors[path + `serials.${at}`] = 'Identifiers must be present and unique.'; identifiers.add(key); });
    });
  });
  return errors;
}
export function openingCommand(value: OpeningSku): components['schemas']['AdvancedOpeningInput'] {
  if (value.decision === 'SKIP') return { decision: 'SKIP' };
  return { decision: 'OPEN', opening_date: value.opening_date, warehouse_id: value.warehouse_id || null, opening_quantity: value.batches.length ? '0' : value.opening_quantity, purchase_price: value.batches.length ? null : value.purchase_price, batches: value.batches.map(row => ({ code: row.code.trim(), opening_quantity: row.opening_quantity, purchase_price: row.purchase_price, sale_prices: Object.entries(row.sale_prices).filter(([, amount]) => !!amount).map(([price_level_id, amount]) => ({ price_level_id, amount })), manufactured_on: row.manufactured_on || null, expires_on: row.expires_on || null, mrp: row.mrp || null, serials: row.serials.map(serial => ({ identifiers: serial.identifiers })) })), serials: value.serials.map(serial => ({ identifiers: serial.identifiers })) };
}
