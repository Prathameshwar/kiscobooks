import type { MasterField } from './catalog-masters';

/** Keep tenant labels; replace only absent labels and unchanged native keys. */
export function advancedFieldLabel(field: Pick<MasterField, 'key' | 'label'> | undefined, fallback: string) {
  const label = field?.label?.trim();
  return !label || label === field?.key ? fallback : label;
}

export function advancedNativeLabel(key: string, field?: Pick<MasterField, 'key' | 'label'>, sku = false) {
  const labels: Record<string, string> = { name: 'Profile name', code: 'Profile code', product_type_revision_id: 'Product Type revision', brand_id: 'Brand', series_id: 'Series', model_code: 'Model code', description: 'Description', sku: 'SKU code', base_unit_id: 'Base unit', sellable: 'Sellable', purchasable: 'Purchasable' };
  return advancedFieldLabel(field, sku && key === 'name' ? 'SKU name' : labels[key] ?? key.replaceAll('_', ' '));
}
