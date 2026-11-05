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
    if (value.purchase_amount && (!decimal.test(value.purchase_amount) || !/[1-9]/.test(value.purchase_amount) || !value.purchase_source.trim())) errors[path + 'purchase_amount'] = 'Enter a positive amount and its source reference.';
    if (work.profile.kind === 'GOODS' && pricing.mrp_mode === 'REQUIRED' && !decimal.test(value.mrp_amount)) errors[path + 'mrp_amount'] = 'Enter MRP.';
    if (value.mrp_amount && (!decimal.test(value.mrp_amount) || !/[1-9]/.test(value.mrp_amount) || !value.mrp_source.trim() || !/^[A-Z][A-Z0-9_-]{1,19}$/.test(value.mrp_jurisdiction))) errors[path + 'mrp_amount'] = 'Enter positive MRP, jurisdiction and source reference.';
    if (options.batch?.required && value.batch_enabled === false) errors[path + 'batch_enabled'] = 'Batch tracking is required for this Product Type.';
  });
  return errors;
}
