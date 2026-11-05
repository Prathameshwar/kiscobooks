import type { components } from '@janso/api-client/catalog';
import type { AdvancedOptions, AdvancedWork } from './advanced-product-draft';
import { businessSku } from './advanced-product-business';
import { openingCommand, openingSku } from './advanced-product-opening';

type Definition = components['schemas']['AdvancedDefinitionCreate'];
type Setup = components['schemas']['AdvancedSkuSetup'];
type Opening = components['schemas']['AdvancedOpeningInput'];
export type AdvancedIntent = {
  company: string; key: string; definition: Definition; work: AdvancedWork;
  creation_id?: string; commands: Record<string, { path: string; body: unknown; key: string }>;
};
const uuid = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
export const intentStorage = (company: string) => 'advanced-product-intent:' + company;
export function readIntent(company: string): AdvancedIntent | null {
  try {
    const text = sessionStorage.getItem(intentStorage(company));
    if (!text || text.length > 300000) return null;
    const value = JSON.parse(text) as AdvancedIntent;
    return value.company === company && uuid.test(value.key) && value.definition?.profile?.kind && value.definition?.mode_version && Array.isArray(value.definition?.skus) && value.definition.skus.length > 0 && value.definition.skus.length <= 64 && (!value.creation_id || uuid.test(value.creation_id)) && value.commands && typeof value.commands === 'object' ? value : null;
  } catch { return null; }
}
export function keepIntent(intent: AdvancedIntent) { sessionStorage.setItem(intentStorage(intent.company), JSON.stringify(intent)); }
export function clearIntent(company: string) { sessionStorage.removeItem(intentStorage(company)); }
export function definitionBody(work: AdvancedWork, options: AdvancedOptions): Definition {
  const p = work.profile;
  return {
    mode_version: options.mode.row_version,
    policy_generation: options.mode.policy_generation,
    source_version: options.defaults.configuration.source_version,
    as_of: options.today,
    group_id: p.group_id || null,
    profile: { kind: p.kind, name: p.name.trim(), code: p.code.trim(), product_type_revision_id: p.product_type_revision_id, ...(p.brand_id ? { brand_id: p.brand_id } : {}), ...(p.series_id ? { series_id: p.series_id } : {}), ...(p.model_code.trim() ? { model_code: p.model_code.trim() } : {}), ...(p.description.trim() ? { description: p.description.trim() } : {}), custom_fields: p.custom_fields },
    attributes: work.axes.map((axis, index) => ({ definition_id: axis.definition_id, is_axis: true, is_required: true, position: index, options: [...new Set(work.skus.map(sku => sku.attributes.find(entry => entry.definition_id === axis.definition_id)?.option_id).filter((value): value is string => !!value))] })),
    skus: work.skus.map(sku => ({ item: { sku: sku.sku.trim(), name: sku.name.trim(), base_unit_id: sku.base_unit_id, sellable: sku.sellable, purchasable: sku.purchasable, ...(sku.min_sale_quantity ? { min_sale_quantity: sku.min_sale_quantity } : {}), custom_fields: sku.custom_fields }, attributes: sku.attributes })),
  };
}
export function setupBody(work: AdvancedWork, options: AdvancedOptions, skuIndex: number, creationVersion: number, familyVersion: number, itemVersion: number): Setup {
  const sku = work.skus[skuIndex]!;
  const business = businessSku(work, sku);
  const price = options.defaults.price;
  const quantity = price?.price_basis_quantity ?? '1';
  const precision = price?.price_decimal_places ?? 2;
  const categories = skuIndex === 0 ? work.profile.categories.filter(row => row.scheme_id && row.category_id).map(row => ({ scheme_id: row.scheme_id, category_id: row.category_id, is_primary: row.is_primary })) : [];
  const prices = (options.sale_price_levels ?? []).filter(level => business.sale_prices[level.plan_id]).map(level => ({ plan_id: level.plan_id, amount: business.sale_prices[level.plan_id]!, price_basis_quantity: quantity, price_decimal_places: precision }));
  const tax = options.gst_enabled && (business.classification_id || business.rule_id) ? { classification_id: business.classification_id || null, rule_id: business.rule_id || null, directions: [ ...(sku.sellable ? ['SALE' as const] : []), ...(sku.purchasable ? ['PURCHASE' as const] : []) ] } : null;
  const reference = business.purchase_amount ? { amount: business.purchase_amount, price_basis_quantity: quantity, currency: options.currency, price_decimal_places: precision, estimate_kind: work.profile.kind === 'SERVICE' ? 'SERVICE_ESTIMATE' as const : 'STANDARD_ESTIMATE' as const, source_reference: business.purchase_source.trim() } : null;
  const mrp = business.mrp_amount ? { amount: business.mrp_amount, price_basis_quantity: quantity, currency: options.currency, price_decimal_places: precision, jurisdiction: business.mrp_jurisdiction, source_reference: business.mrp_source.trim() } : null;
  return {
    expected_creation_version: creationVersion,
    expected_family_version: familyVersion,
    expected_item_version: itemVersion,
    setup: {
      effective_from: options.today,
      ...(skuIndex === 0 ? { group_id: work.profile.group_id, categories, ...(work.profile.manufacturer_id ? { manufacturer: { expected_version: 1, manufacturer_id: work.profile.manufacturer_id, site_id: work.profile.manufacturer_site_id || null, role: 'MANUFACTURER' as const, valid_from: options.today } } : {}) } : {}),
      units: sku.units.map(row => ({ expected_version: 1, code: row.code, unit_id: row.unit_id, role: row.role, ...(row.pack_type_id ? { pack_type_id: row.pack_type_id } : {}), conversion_mode: 'FIXED' as const, numerator: Number(row.numerator), denominator: Number(row.denominator), quantity_decimal_places: Number(row.quantity_decimal_places), quantity_increment: row.quantity_increment, fractional_entry: Number(row.quantity_decimal_places) > 0, valid_from: options.today })),
      ...(business.batch_enabled !== null || options.batch?.required ? { batch_enabled: business.batch_enabled ?? true } : {}),
      ...(tax ? { tax } : {}),
      prices,
      expected_generation: options.mode.policy_generation,
      expected_source_version: options.defaults.configuration.source_version,
    },
    purchase_reference: reference,
    mrp,
  };
}
export function openingBody(work: AdvancedWork, index: number): Opening {
  return openingCommand(openingSku(work, work.skus[index]!));
}
