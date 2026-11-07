import type { AdvancedOptions, AdvancedWork, ProductSkuValues } from './advanced-product-draft';

export type BusinessSku = {
  classification_id: string; rule_id: string; batch_enabled: boolean | null;
  sale_prices: Record<string, string>;
  purchase_amount: string; purchase_source: string;
  mrp_amount: string; mrp_source: string; mrp_jurisdiction: string;
};
export const emptyBusiness = (): BusinessSku => ({ classification_id: '', rule_id: '', batch_enabled: null, sale_prices: {}, purchase_amount: '', purchase_source: '', mrp_amount: '', mrp_source: '', mrp_jurisdiction: '' });
export function businessSku(work: AdvancedWork, sku: ProductSkuValues): BusinessSku {
  const rows = work.business.skus;
  const saved = rows && typeof rows === 'object' && !Array.isArray(rows) ? (rows as Record<string, unknown>)[sku.key] : null;
  const item = saved && typeof saved === 'object' && !Array.isArray(saved) ? saved as Record<string, unknown> : {};
  const string = (value: unknown) => typeof value === 'string' ? value : '';
  const prices = item.sale_prices && typeof item.sale_prices === 'object' && !Array.isArray(item.sale_prices) ? item.sale_prices as Record<string, unknown> : {};
  return { classification_id: string(item.classification_id), rule_id: string(item.rule_id), batch_enabled: typeof item.batch_enabled === 'boolean' ? item.batch_enabled : null, sale_prices: Object.fromEntries(Object.entries(prices).map(([key, value]) => [key, string(value)])), purchase_amount: string(item.purchase_amount), purchase_source: string(item.purchase_source), mrp_amount: string(item.mrp_amount), mrp_source: string(item.mrp_source), mrp_jurisdiction: string(item.mrp_jurisdiction) };
}
export function putBusiness(work: AdvancedWork, sku: ProductSkuValues, next: BusinessSku): AdvancedWork {
  const old = work.business.skus && typeof work.business.skus === 'object' && !Array.isArray(work.business.skus) ? work.business.skus as Record<string, unknown> : {};
  return { ...work, business: { ...work.business, skus: { ...old, [sku.key]: next } } };
}
const decimal = /^(?:0|[1-9]\d{0,14})(?:\.\d{1,4})?$/;
export function unavailableBusinessKeys(work: AdvancedWork, options: AdvancedOptions, index: number): string[] {
  const sku = work.skus[index]!;
  const value = businessSku(work, sku), pricing = options.defaults.configuration.pricing;
  const keys: string[] = [];
  if (value.purchase_amount && (!sku.purchasable || pricing.purchase_reference_mode === 'DISABLED')) keys.push('purchase_amount');
  if (value.mrp_amount && (work.profile.kind !== 'GOODS' || pricing.mrp_mode === 'DISABLED')) keys.push('mrp_amount');
  if (!options.gst_enabled) { if (value.classification_id) keys.push('classification_id'); if (value.rule_id) keys.push('rule_id'); }
  if (value.batch_enabled && !options.batch?.available) keys.push('batch_enabled');
  const plans = new Set((options.sale_price_levels ?? []).map(level => level.plan_id));
  for (const [plan, amount] of Object.entries(value.sale_prices)) if (amount && (!sku.sellable || pricing.sale_price_mode === 'DISABLED' || !options.price_levels_accessible || !plans.has(plan))) keys.push('sale_prices.' + plan);
  return keys;
}

export function clearUnavailableBusiness(work: AdvancedWork, options: AdvancedOptions, index: number): AdvancedWork {
  const sku = work.skus[index]!;
  const value = { ...businessSku(work, sku), sale_prices: { ...businessSku(work, sku).sale_prices } };
  for (const key of unavailableBusinessKeys(work, options, index)) {
    if (key.startsWith('sale_prices.')) delete value.sale_prices[key.slice('sale_prices.'.length)];
    else if (key === 'purchase_amount') { value.purchase_amount = ''; value.purchase_source = ''; }
    else if (key === 'mrp_amount') { value.mrp_amount = ''; value.mrp_source = ''; value.mrp_jurisdiction = ''; }
    else if (key === 'batch_enabled') value.batch_enabled = null;
    else if (key === 'classification_id') value.classification_id = '';
    else if (key === 'rule_id') value.rule_id = '';
  }
  return putBusiness(work, sku, value);
}

export function businessErrors(work: AdvancedWork, options: AdvancedOptions): Record<string, string> {
  const errors: Record<string, string> = {};
  work.skus.forEach((sku, index) => {
    const value = businessSku(work, sku);
    const path = `business.skus.${index}.`;
    if (options.gst_enabled) {
      if (!value.classification_id) errors[path + 'classification_id'] = `Choose ${work.profile.kind === 'GOODS' ? 'HSN' : 'SAC'} for ${sku.sku || `SKU ${index + 1}`}.`;
      if (!value.rule_id) errors[path + 'rule_id'] = `Choose a GST treatment for ${sku.sku || `SKU ${index + 1}`}.`;
    }
    if (sku.sellable && options.defaults.configuration.pricing.sale_price_mode !== 'DISABLED') {
      for (const level of options.sale_price_levels ?? []) if (level.required && !decimal.test(value.sale_prices[level.plan_id] ?? '')) errors[path + 'sale_prices.' + level.plan_id] = `Enter ${level.name} price for ${sku.sku || `SKU ${index + 1}`}.`;
      for (const [planId, amount] of Object.entries(value.sale_prices)) if (amount && !decimal.test(amount)) errors[path + 'sale_prices.' + planId] = 'Enter an exact price with up to four decimals.';
    }
    const pricing = options.defaults.configuration.pricing;
    if (sku.purchasable && pricing.purchase_reference_mode === 'REQUIRED' && !decimal.test(value.purchase_amount)) errors[path + 'purchase_amount'] = 'Enter a purchase reference amount.';
    if (value.purchase_amount && (!decimal.test(value.purchase_amount) || !/[1-9]/.test(value.purchase_amount))) errors[path + 'purchase_amount'] = 'Enter a positive purchase reference amount with up to four decimals.';
    if (value.purchase_amount && !value.purchase_source.trim()) errors[path + 'purchase_source'] = 'Enter the purchase source reference.';
    if (work.profile.kind === 'GOODS' && pricing.mrp_mode === 'REQUIRED' && !decimal.test(value.mrp_amount)) errors[path + 'mrp_amount'] = 'Enter MRP.';
    if (value.mrp_amount && (!decimal.test(value.mrp_amount) || !/[1-9]/.test(value.mrp_amount))) errors[path + 'mrp_amount'] = 'Enter positive MRP with up to four decimals.';
    if (value.mrp_amount && !value.mrp_source.trim()) errors[path + 'mrp_source'] = 'Enter the MRP source reference.';
    if (value.mrp_amount && !/^[A-Z][A-Z0-9_-]{1,19}$/.test(value.mrp_jurisdiction)) errors[path + 'mrp_jurisdiction'] = 'Enter the MRP jurisdiction code, such as IN.';
    if (options.batch?.required && value.batch_enabled === false) errors[path + 'batch_enabled'] = 'Batch tracking is required for this Product Type.';
    if (sku.sellable && pricing.sale_price_mode === 'REQUIRED' && (!options.price_levels_accessible || !(options.sale_price_levels ?? []).length)) errors[path + 'sale_prices'] = 'Required selling prices are unavailable. Review price-level access and company pricing setup.';
    for (const key of unavailableBusinessKeys(work, options, index)) errors[path + key] = 'This saved detail is no longer available. Remove unavailable SKU details before continuing.';
  });
  return errors;
}
