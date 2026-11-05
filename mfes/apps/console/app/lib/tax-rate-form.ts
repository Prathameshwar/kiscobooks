import { taxUuid, type TaxField } from './tax-masters';

export type TaxComponent = Record<string, unknown> & { component_key: string; component: string; kind: string; rounding_mode: string; position: number };
export const taxContexts = { INTRA_STATE: ['CGST', 'SGST'], INTRA_UT: ['CGST', 'UTGST'], INTER_STATE: ['IGST'] } as const;
export function initialTaxComponents(context: string, nil = false): TaxComponent[] {
  return (taxContexts[context as keyof typeof taxContexts] ?? []).map((component, position) => ({ component_key: component, component, kind: 'PERCENT', percentage: nil ? '0' : '', amount: null, currency: null, unit_id: null, basis_quantity: null, rounding_mode: 'HALF_UP', position }));
}
function exact(value: unknown): bigint | null {
  if (typeof value !== 'string' || !/^\d{1,15}(?:\.\d{1,4})?$/.test(value)) return null;
  const [whole, decimal = ''] = value.split('.'); return BigInt(whole!) * 10000n + BigInt(decimal.padEnd(4, '0'));
}
export function taxComponentsBody(rows: TaxComponent[], fields: TaxField[], context: string, treatment: string) {
  const errors: Record<string, string> = {}, components: Record<string, unknown>[] = [], names = taxContexts[context as keyof typeof taxContexts] ?? [];
  if (!names.length || !['TAXABLE', 'NIL_RATED'].includes(treatment)) errors.components = 'Choose a taxable or nil-rated rule and an available supply context.';
  if (!rows.length || rows.length > 16) errors.components = 'A rate needs one to sixteen components.';
  const used = new Set<string>();
  rows.forEach((row, index) => {
    const prefix = 'components.' + index + '.', item: Record<string, unknown> = {};
    for (const key of ['component_key', 'component', 'kind', 'rounding_mode', 'position']) {
      const field = fields.find(field => field.key === key && field.visible && field.writable && !field.conditional_access);
      if (!field) errors.components = 'Your field access does not allow publication of complete rate components.';
      else item[key] = key === 'position' ? index : row[key];
    }
    if (!/^[A-Z][A-Z0-9_]{0,29}$/.test(row.component_key) || used.has(row.component_key)) errors[prefix + 'component_key'] = 'Use a distinct uppercase component key.';
    used.add(row.component_key);
    if (![...names as readonly string[], 'CESS'].includes(row.component)) errors[prefix + 'component'] = 'This component does not match the supply context.';
    if (!['HALF_UP', 'UP', 'DOWN'].includes(row.rounding_mode)) errors[prefix + 'rounding_mode'] = 'Choose a rounding mode.';
    if (row.kind === 'PERCENT') {
      const decimal = exact(row.percentage);
      if (decimal === null || row.component !== 'CESS' && decimal > (row.component === 'IGST' ? 40n : 20n) * 10000n) errors[prefix + 'percentage'] = 'Enter an exact non-negative percentage within the statutory ceiling (up to 4 decimal places).';
      item.percentage = row.percentage;
    } else if (row.kind === 'FIXED_PER_UNIT' && row.component === 'CESS') {
      for (const key of ['amount', 'basis_quantity']) { const decimal = exact(row[key]); if (decimal === null || decimal <= 0n) errors[prefix + key] = 'Enter an exact positive decimal with up to 4 places.'; item[key] = row[key]; }
      item.currency = 'INR'; item.unit_id = row.unit_id;
      if (!taxUuid.test(String(row.unit_id ?? ''))) errors[prefix + 'unit_id'] = 'Choose a unit for fixed cess.';
    } else errors[prefix + 'kind'] = 'Only cess can use a fixed amount per unit.';
    for (const key of Object.keys(item)) if (!fields.some(field => field.key === key && field.visible && field.writable && !field.conditional_access)) errors[prefix + key] = 'This required component field is protected.';
    components.push(item);
  });
  const gst = rows.filter(row => row.component !== 'CESS');
  if (gst.length !== names.length || names.some(name => gst.filter(row => row.component === name).length !== 1)) errors.components = 'Include exactly the GST components required by the supply context.';
  if (gst.length === 2 && (exact(gst[0]?.percentage) !== exact(gst[1]?.percentage) || gst[0]?.rounding_mode !== gst[1]?.rounding_mode)) errors.components = 'Central and state/territory percentages and rounding must match.';
  if (treatment === 'NIL_RATED' && (rows.some(row => row.component === 'CESS') || gst.some(row => exact(row.percentage) !== 0n))) errors.components = 'Nil-rated rules require explicit zero GST percentages and no cess.';
  if (treatment === 'TAXABLE' && !gst.some(row => (exact(row.percentage) ?? 0n) > 0n)) errors.components = 'Taxable rules require a positive GST percentage.';
  return { components, errors };
}
