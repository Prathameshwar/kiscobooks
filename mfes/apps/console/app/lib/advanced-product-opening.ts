import type { components } from '@janso/api-client/catalog';
import type { AdvancedOptions, AdvancedWork, ProductSkuValues } from './advanced-product-draft';
import { businessSku } from './advanced-product-business';
import { trimSerialIdentifier, validateSerialIdentifiers, normalizedSerialIdentifier } from './serial-identity';
import { validMasterDate } from './catalog-masters';
export type OpeningSerial = { key: string; identifiers: components['schemas']['IdentifierInput'][] };
export type OpeningBatch = { key: string; code: string; opening_quantity: string; purchase_price: string; purchase_reference?: string; sale_prices: Record<string, string>; manufactured_on: string; expires_on: string; mrp: string; serials: OpeningSerial[] };
export type OpeningSku = { decision: 'SKIP' | 'OPEN'; opening_date: string; warehouse_id: string; opening_quantity: string; purchase_price: string; batches: OpeningBatch[]; serials: OpeningSerial[] };
export const emptyOpening = (): OpeningSku => ({ decision: 'SKIP', opening_date: '', warehouse_id: '', opening_quantity: '', purchase_price: '', batches: [], serials: [] });
export function openingSku(work: AdvancedWork, sku: ProductSkuValues): OpeningSku {
  const rows = work.opening.skus;
  const saved = rows && typeof rows === 'object' && !Array.isArray(rows) ? (rows as Record<string, unknown>)[sku.key] : null;
  const value = saved && typeof saved === 'object' && !Array.isArray(saved) ? saved as Record<string, unknown> : {};
  const string = (part: unknown) => typeof part === 'string' ? part : '';
  const serials = (part: unknown): OpeningSerial[] => Array.isArray(part) ? part.map(row => ({ key: string(row.key) || crypto.randomUUID(), identifiers: Array.isArray(row.identifiers) ? (row.identifiers as OpeningSerial['identifiers']).filter(item => item.value && trimSerialIdentifier(item.value)) : [] })) : [];
  return { decision: value.decision === 'OPEN' ? 'OPEN' : 'SKIP', opening_date: string(value.opening_date), warehouse_id: string(value.warehouse_id), opening_quantity: string(value.opening_quantity), purchase_price: string(value.purchase_price), batches: Array.isArray(value.batches) ? value.batches.map(row => ({ key: string(row.key) || crypto.randomUUID(), code: string(row.code), opening_quantity: string(row.opening_quantity), purchase_price: string(row.purchase_price), purchase_reference: string(row.purchase_reference), sale_prices: row.sale_prices && typeof row.sale_prices === 'object' && !Array.isArray(row.sale_prices) ? Object.fromEntries(Object.entries(row.sale_prices).map(([key, amount]) => [key, string(amount)])) : {}, manufactured_on: string(row.manufactured_on), expires_on: string(row.expires_on), mrp: string(row.mrp), serials: serials(row.serials) })) : [], serials: serials(value.serials) };
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
export function unavailableOpeningKeys(work: AdvancedWork, options: AdvancedOptions, index: number) {
  const value = openingSku(work, work.skus[index]!);
  const batch = options.batch?.available && (businessSku(work, work.skus[index]!).batch_enabled || options.batch?.required);
  const keys: string[] = [];
  if (!batch && value.batches.length) keys.push('batches');
  if (batch) {
    if (value.opening_quantity) keys.push('opening_quantity');
    if (value.purchase_price) keys.push('purchase_price');
    if (value.serials.length) keys.push('serials');
  } else if (!options.serial?.enabled && value.serials.length) keys.push('serials');
  const pricing = options.defaults.configuration.pricing;
  const levels = new Set((options.sale_price_levels ?? []).map(level => level.price_level_id));
  value.batches.forEach((row, i) => {
    if (row.purchase_reference && pricing.purchase_reference_mode === 'DISABLED') keys.push(`batches.${i}.purchase_reference`);
    if (row.mrp && pricing.mrp_mode === 'DISABLED') keys.push(`batches.${i}.mrp`);
    if (row.serials.length && !options.serial?.enabled) keys.push(`batches.${i}.serials`);
    for (const [level, amount] of Object.entries(row.sale_prices)) if (amount && (!levels.has(level) || !options.price_levels_accessible || pricing.sale_price_mode === 'DISABLED')) keys.push(`batches.${i}.sale_prices.${level}`);
  });
  return keys;
}

export function clearUnavailableOpening(work: AdvancedWork, options: AdvancedOptions, index: number) {
  const sku = work.skus[index]!;
  const value = openingSku(work, sku);
  const keys = new Set(unavailableOpeningKeys(work, options, index));
  if (keys.has('batches')) value.batches = [];
  if (keys.has('serials')) value.serials = [];
  if (keys.has('opening_quantity')) value.opening_quantity = '';
  if (keys.has('purchase_price')) value.purchase_price = '';
  value.batches = value.batches.map((row, i) => ({ ...row,
    purchase_reference: keys.has(`batches.${i}.purchase_reference`) ? '' : row.purchase_reference,
    mrp: keys.has(`batches.${i}.mrp`) ? '' : row.mrp,
    serials: keys.has(`batches.${i}.serials`) ? [] : row.serials,
    sale_prices: Object.fromEntries(Object.entries(row.sale_prices).filter(([level]) => !keys.has(`batches.${i}.sale_prices.${level}`))),
  }));
  return putOpening(work, sku, value);
}

export function openingErrors(work: AdvancedWork, options: AdvancedOptions): Record<string, string> {
  const errors: Record<string, string> = {};
  const identifiers = new Set<string>();
  work.skus.forEach((sku, index) => {
    const value = openingSku(work, sku);
    const path = `opening.skus.${index}.`;
    if (value.decision === 'SKIP') return;
    for (const key of unavailableOpeningKeys(work, options, index)) errors[path + key] = 'This saved opening detail is no longer available. Remove unavailable opening details before continuing.';
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
        try {
          const code = normalizedSerialIdentifier(row.code);
          if ([...row.code].length > 100 || [...code].length > 100) errors[batchPath + 'code'] = 'Enter a batch code up to 100 characters after normalization.';
          if (seen.has(code)) errors[batchPath + 'code'] = 'Batch codes must be distinct.';
          seen.add(code);
        } catch { errors[batchPath + 'code'] = 'Enter a printable batch code.'; }
        if (!positive(row.opening_quantity)) errors[batchPath + 'opening_quantity'] = 'Enter a positive batch quantity.';
        if (!positive(row.purchase_price)) errors[batchPath + 'opening_unit_cost'] = 'Enter a positive opening unit cost.';
        const referenceMode = options.defaults.configuration.pricing.purchase_reference_mode;
        const reference = row.purchase_reference ?? '';
        if ((referenceMode === 'REQUIRED' && !positive(reference)) || (reference && (referenceMode === 'DISABLED' || !positive(reference)))) errors[batchPath + 'purchase_reference'] = 'Enter an allowed positive purchase reference price.';
        if (options.batch?.manufacture_date_required && !row.manufactured_on) errors[batchPath + 'manufactured_on'] = 'Enter the manufacture date.';
        if (options.batch?.expiry_required && !row.expires_on) errors[batchPath + 'expires_on'] = 'Enter the expiry date.';
        if (row.manufactured_on && !validMasterDate(row.manufactured_on)) errors[batchPath + 'manufactured_on'] = 'Enter a valid manufacture date.';
        if (row.expires_on && !validMasterDate(row.expires_on)) errors[batchPath + 'expires_on'] = 'Enter a valid expiry date.';
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
      if (!positive(value.purchase_price)) errors[path + 'opening_unit_cost'] = 'Enter a positive opening unit cost.';
      if (options.serial?.enabled && Number(value.opening_quantity) !== value.serials.length) errors[path + 'serials'] = 'Add one physical serial unit for each opening unit.';
    }
    const all = [...value.serials.map((serial, at) => ({ serial, prefix: `${path}serials.${at}.identifiers` })), ...value.batches.flatMap((batch, batchIndex) => batch.serials.map((serial, at) => ({ serial, prefix: `${path}batches.${batchIndex}.serials.${at}.identifiers` })))];
    if (all.length > 200) errors[path + 'serials'] = 'Use at most 200 serial units.';
    all.forEach(({ serial, prefix }) => {
      const validated = validateSerialIdentifiers(serial.identifiers, options.serial?.requirements ?? [], { prefix, seen: identifiers, skuKey: sku.key, omitEmpty: true });
      Object.assign(errors, validated.errors);
    });
  });
  return errors;
}
export function openingCommand(value: OpeningSku): components['schemas']['AdvancedOpeningInput'] {
  if (value.decision === 'SKIP') return { decision: 'SKIP' };
  return { decision: 'OPEN', opening_date: value.opening_date, warehouse_id: value.warehouse_id || null, opening_quantity: value.batches.length ? '0' : value.opening_quantity, opening_unit_cost: value.batches.length ? null : value.purchase_price, batches: value.batches.map(row => ({ code: row.code.trim(), opening_quantity: row.opening_quantity, opening_unit_cost: row.purchase_price, purchase_price: row.purchase_reference || null, sale_prices: Object.entries(row.sale_prices).filter(([, amount]) => !!amount).map(([price_level_id, amount]) => ({ price_level_id, amount })), manufactured_on: row.manufactured_on || null, expires_on: row.expires_on || null, mrp: row.mrp || null, serials: row.serials.map(serial => ({ identifiers: serial.identifiers.filter(item => trimSerialIdentifier(item.value)) })) })), serials: value.serials.map(serial => ({ identifiers: serial.identifiers.filter(item => trimSerialIdentifier(item.value)) })) };
}
