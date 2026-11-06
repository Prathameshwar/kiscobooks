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
  reviewed_source_version?: number; reviewed_policy_generation?: number; reviewed_mode_version?: number;
};
type CreationStatus = components['schemas']['AdvancedDefinitionStatus'];
const uuid = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
export const intentStorage = (company: string) => 'advanced-product-intent:' + company;
export function readIntent(company: string): AdvancedIntent | null {
  try {
    const text = sessionStorage.getItem(intentStorage(company));
    if (!text || text.length > 300000) return null;
    const value = JSON.parse(text) as AdvancedIntent;
    if (value.company !== company || !uuid.test(value.key) || !value.definition?.profile?.kind || !value.definition?.mode_version || !Array.isArray(value.definition?.skus) || !value.definition.skus.length || value.definition.skus.length > 64 || (value.creation_id && !uuid.test(value.creation_id)) || !Array.isArray(value.work?.skus) || value.work.skus.length !== value.definition.skus.length || !value.work.skus.every(sku => sku && typeof sku.sku === 'string' && typeof sku.base_unit_id === 'string') || value.work.profile?.kind !== value.definition.profile.kind || !value.commands || typeof value.commands !== 'object' || Array.isArray(value.commands)) return null;
    const allowed = value.creation_id ? new RegExp(`^/v1/companies/${company}/advanced-product-creations/definitions/${value.creation_id}/skus/([0-9a-f-]{36})/(setup|publish-prices|activate|opening)$`, 'i') : null;
    if (Object.entries(value.commands).some(([name, raw]) => {
      const command = raw as AdvancedIntent['commands'][string];
      const match = typeof command?.path === 'string' ? allowed?.exec(command.path) : null;
      return !match || !uuid.test(match[1]!) || !value.work.skus.some((_, index) => value.creation_id && value.definition.skus[index] && name === `${match[2] === 'publish-prices' ? 'publish' : match[2]}:${match[1]}`) || !uuid.test(command.key);
    })) return null;
    value.work.skus = value.work.skus.map(sku => ({ ...sku, barcode: typeof sku.barcode === 'string' ? sku.barcode : '', barcode_symbology: ['GTIN', 'CODE128', 'QR'].includes(sku.barcode_symbology) ? sku.barcode_symbology : 'CODE128' }));
    return value;
  } catch { return null; }
}
export function keepIntent(intent: AdvancedIntent) { sessionStorage.setItem(intentStorage(intent.company), JSON.stringify(intent)); }
export function clearIntent(company: string) { sessionStorage.removeItem(intentStorage(company)); }
/** Never turn a submitted creation back into a new definition after session recovery fails. */
export function checkRecoveryIntent(pending: AdvancedIntent | null, editingId: string | null): void {
  if (editingId && (!pending?.creation_id || pending.creation_id !== editingId)) throw { status: 409, message: 'The saved creation receipt is missing or changed. Reload this product before continuing.' };
  if (!editingId && pending?.creation_id) throw { status: 409, message: 'An existing product creation needs review before another can be started.' };
}
/** A submitted definition and every completed owner step are immutable. */
export function reviseIntent(previous: AdvancedIntent, work: AdvancedWork, options: AdvancedOptions, status: CreationStatus): AdvancedIntent {
  if (!previous.creation_id || status.id !== previous.creation_id || status.company_id !== previous.company || status.sku_ids.length !== work.skus.length) throw { status: 409, message: 'Product progress changed. Reload its saved receipt before editing.' };
  const now = definitionBody(work, options);
  const before = previous.definition;
  if (JSON.stringify([now.group_id, now.profile, now.attributes, now.skus]) !== JSON.stringify([before.group_id, before.profile, before.attributes, before.skus])) throw { status: 409, message: 'The submitted Profile and SKU definitions cannot be changed during recovery.' };
  const commands = { ...previous.commands };
  const policyChanged = options.defaults.configuration.source_version !== (previous.reviewed_source_version ?? previous.definition.source_version) || options.mode.policy_generation !== (previous.reviewed_policy_generation ?? previous.definition.policy_generation);
  const profileSetupChanged = JSON.stringify([work.profile.categories, work.profile.manufacturer_id, work.profile.manufacturer_site_id]) !== JSON.stringify([previous.work.profile.categories, previous.work.profile.manufacturer_id, previous.work.profile.manufacturer_site_id]);
  for (let index = 0; index < work.skus.length; index++) {
    const sku = work.skus[index]!;
    const prior = previous.work.skus[index]!;
    const progress = status.sku_progress?.[index];
    if (!progress || progress.item_id !== status.sku_ids[index]) throw { status: 409, message: 'SKU receipts changed. Reload this creation.' };
    const businessChanged = JSON.stringify(businessSku(work, sku)) !== JSON.stringify(businessSku(previous.work, prior));
    const openingChanged = JSON.stringify(openingSku(work, sku)) !== JSON.stringify(openingSku(previous.work, prior));
    const skuSetupChanged = JSON.stringify([sku.units, sku.barcode, sku.barcode_symbology]) !== JSON.stringify([prior.units, prior.barcode, prior.barcode_symbology]);
    if (progress.setup_done && (businessChanged || skuSetupChanged || (index === 0 && profileSetupChanged))) throw { status: 409, message: `Setup for ${sku.sku} is already saved and cannot be edited.` };
    if (progress.setup_done && (openingSku(work, sku).decision !== openingSku(previous.work, prior).decision || openingSku(work, sku).opening_date !== openingSku(previous.work, prior).opening_date)) throw { status: 409, message: `The opening choice and books-begin date for ${sku.sku} were fixed when its unit setup was saved.` };
    if ((progress.opening_state ?? 'NOT_REQUESTED') !== 'NOT_REQUESTED' && openingChanged) throw { status: 409, message: `The opening decision for ${sku.sku} is already saved and cannot be edited.` };
    if (!progress.setup_done && (policyChanged || businessChanged || openingChanged || skuSetupChanged || (index === 0 && profileSetupChanged))) delete commands[`setup:${progress.item_id}`];
    if (!progress.activated && policyChanged) delete commands[`activate:${progress.item_id}`];
    if (progress.opening_state === 'NOT_REQUESTED' && openingChanged) delete commands[`opening:${progress.item_id}`];
  }
  return { ...previous, work: structuredClone(work), commands, reviewed_source_version: options.defaults.configuration.source_version, reviewed_policy_generation: options.mode.policy_generation, reviewed_mode_version: options.mode.row_version };
}
export function definitionBody(work: AdvancedWork, options: AdvancedOptions): Definition {
  const p = work.profile;
  const members = options.attribute_members ?? [];
  const axisIds = new Set(work.axes.map(axis => axis.definition_id));
  const optionsFor = (definitionId: string) => [...new Set(work.skus.map(sku => sku.attributes.find(entry => entry.definition_id === definitionId)?.option_id).filter((value): value is string => !!value))];
  const attributes: Definition['attributes'] = [
    ...work.axes.map((axis, index) => ({ definition_id: axis.definition_id, is_axis: true, is_required: true, position: members.find(member => member.definition_id === axis.definition_id)?.position ?? index, options: optionsFor(axis.definition_id) })),
    ...members.filter(member => !axisIds.has(member.definition_id) && (member.is_required || work.skus.some(sku => sku.attributes.some(value => value.definition_id === member.definition_id)))).map(member => ({ definition_id: member.definition_id, is_axis: false, is_required: member.is_required, position: member.position, options: optionsFor(member.definition_id) })),
  ].sort((left, right) => left.position - right.position);
  return {
    mode_version: options.mode.row_version,
    policy_generation: options.mode.policy_generation,
    source_version: options.defaults.configuration.source_version,
    as_of: options.today,
    group_id: p.group_id || null,
    profile: { kind: p.kind, name: p.name.trim(), code: p.code.trim(), product_type_revision_id: p.product_type_revision_id, ...(p.brand_id ? { brand_id: p.brand_id } : {}), ...(p.series_id ? { series_id: p.series_id } : {}), ...(p.model_code.trim() ? { model_code: p.model_code.trim() } : {}), ...(p.description.trim() ? { description: p.description.trim() } : {}), custom_fields: p.custom_fields },
    attributes,
    skus: work.skus.map(sku => ({ item: { sku: sku.sku.trim(), name: sku.name.trim(), base_unit_id: sku.base_unit_id, sellable: sku.sellable, purchasable: sku.purchasable, ...(sku.min_sale_quantity ? { min_sale_quantity: sku.min_sale_quantity } : {}), custom_fields: sku.custom_fields }, attributes: sku.attributes })),
  };
}
export function setupBody(work: AdvancedWork, options: AdvancedOptions, skuIndex: number, creationVersion: number, familyVersion: number, itemVersion: number): Setup {
  const sku = work.skus[skuIndex]!;
  const business = businessSku(work, sku);
  const price = options.defaults.price;
  const quantity = price?.price_basis_quantity ?? '1';
  const precision = price?.price_decimal_places ?? 2;
  const quantityRule = options.defaults.quantity;
  if (!quantityRule || quantityRule.unit_id !== sku.base_unit_id) throw { status: 409, message: `The base-unit quantity rule for ${sku.sku || `SKU ${skuIndex + 1}`} changed. Review this SKU before continuing.` };
  const opening = openingSku(work, sku);
  const unitFrom = opening.decision === 'OPEN' && opening.opening_date < options.today ? opening.opening_date : options.today;
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
      units: [
        { expected_version: 1, code: 'BASE', unit_id: sku.base_unit_id, role: 'BASE' as const, conversion_mode: 'FIXED' as const, numerator: '1', denominator: '1', quantity_decimal_places: quantityRule.quantity_decimal_places, quantity_increment: quantityRule.quantity_increment, fractional_entry: quantityRule.fractional_entry, valid_from: unitFrom },
        ...sku.units.map(row => ({ expected_version: 1, code: row.code, unit_id: row.unit_id, role: row.role, ...(row.pack_type_id ? { pack_type_id: row.pack_type_id } : {}), conversion_mode: 'FIXED' as const, numerator: row.numerator, denominator: row.denominator, quantity_decimal_places: Number(row.quantity_decimal_places), quantity_increment: row.quantity_increment, fractional_entry: Number(row.quantity_decimal_places) > 0, valid_from: unitFrom })),
      ],
      barcodes: sku.barcode.trim() ? [{ expected_version: 1, value: sku.barcode.trim(), symbology: sku.barcode_symbology }] : [],
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
