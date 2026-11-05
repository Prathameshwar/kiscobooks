import type { MasterField, MasterRow } from './catalog-masters';
import type { ServicePage } from './service-resource';
import { profileId } from './product-profiles';

export const bomScalars = [
  'specification',
  'change_reason',
  'definition_date',
  'route_revision_id',
  'batch_minimum',
  'batch_maximum',
  'batch_multiple',
] as const;
export const bomComponentFields = [
  'line_key',
  'sequence',
  'item_id',
  'unit_revision_id',
  'quantity',
  'basis',
  'loss_fraction',
  'timing',
  'route_step_id',
] as const;
export const bomOutputFields = [
  'line_key',
  'sequence',
  'item_id',
  'unit_revision_id',
  'nominal_quantity',
  'yield_fraction',
  'role',
] as const;
export type BomLine = Record<string, unknown> & {
  line_key: string;
  sequence: number;
  item_id: string;
  unit_revision_id: string | null;
};
export type BomDraft = Record<string, unknown> & {
  components: BomLine[];
  outputs: BomLine[];
};
export type BomAccess = {
  manage: boolean;
  publish: boolean;
  assign: boolean;
  goods: boolean;
  units: boolean;
  routes: boolean;
  warehouses: boolean;
};
export const bomBase = (company: string, suffix = '') =>
  `/v1/companies/${company}/boms${suffix}`;
export const bomId = (value: unknown): value is string =>
  typeof value === 'string' &&
  profileId.test(value) &&
  !/^0{8}-0{4}-0{4}-0{4}-0{12}$/.test(value);
export function bomNumber(value: unknown, scale = 4, zero = false): boolean {
  if (
    typeof value !== 'string' ||
    !new RegExp(`^\\d{1,15}(?:\\.\\d{1,${scale}})?$`).test(value)
  )
    return false;
  return zero || /[1-9]/.test(value);
}
export function bomFraction(value: unknown, zero: boolean): boolean {
  return (
    typeof value === 'string' &&
    /^(?:0(?:\.\d{1,8})?|1(?:\.0{1,8})?)$/.test(value) &&
    (zero || /[1-9]/.test(value))
  );
}
export function bomWritable(
  fields: readonly MasterField[],
  keys: readonly string[],
) {
  return keys.every((key) =>
    fields.some(
      (field) =>
        field.key === key &&
        field.visible &&
        field.writable &&
        !field.conditional_access &&
        !field.control?.disabled_reason,
    ),
  );
}
export function newBomLine(
  kind: 'components' | 'outputs',
  sequence: number,
): BomLine {
  // Stable business line identity; physical row IDs are assigned by Catalog.
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  let stamp = BigInt(Date.now());
  for (let index = 5; index >= 0; index--) {
    bytes[index] = Number(stamp & 255n);
    stamp >>= 8n;
  }
  bytes[6] = (bytes[6]! & 15) | 112;
  bytes[8] = (bytes[8]! & 63) | 128;
  const hex = Array.from(bytes, (value) =>
    value.toString(16).padStart(2, '0'),
  ).join('');
  const line_key = `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  return {
    line_key,
    sequence,
    item_id: '',
    unit_revision_id: null,
    ...(kind === 'components'
      ? {
          quantity: '1',
          basis: 'GROSS_INPUT',
          loss_fraction: '0',
          timing: 'PER_BASIS',
          route_step_id: null,
        }
      : { nominal_quantity: '1', yield_fraction: '1', role: 'PRIMARY' }),
  };
}
export function bomBody(values: BomDraft) {
  const errors: Record<string, string> = {},
    body: Record<string, unknown> = {};
  for (const key of bomScalars) {
    const value = values[key];
    body[key] = value === '' || value == null ? null : value;
    if (
      ['specification', 'change_reason'].includes(key) &&
      (typeof value !== 'string' || !value.trim())
    )
      errors[key] = 'Enter a reason or specification.';
    if (
      key === 'definition_date' &&
      (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value))
    )
      errors[key] = 'Choose the definition date.';
    if (
      key.startsWith('batch_') &&
      value !== '' &&
      value != null &&
      !bomNumber(value)
    )
      errors[key] =
        'Enter a positive exact quantity with up to four decimal places.';
    if (key === 'route_revision_id' && value && !bomId(value))
      errors[key] = 'Choose a valid published route revision.';
  }
  const seen = new Set<string>();
  for (const kind of ['components', 'outputs'] as const) {
    const fields = kind === 'components' ? bomComponentFields : bomOutputFields;
    if (values[kind].length > (kind === 'components' ? 1000 : 100))
      errors[kind] = 'This recipe exceeds the supported line count.';
    body[kind] = values[kind].map((line, index) => {
      const row = Object.fromEntries(
        fields.map((key) => [
          key,
          key === 'sequence' ? index + 1 : (line[key] ?? null),
        ]),
      );
      if (!bomId(line.line_key) || seen.has(line.line_key))
        errors[kind] = 'Reload the complete line set before saving.';
      seen.add(line.line_key);
      for (const key of [
        'item_id',
        'unit_revision_id',
        ...(kind === 'components' ? ['route_step_id'] : []),
      ])
        if ((key === 'item_id' || line[key]) && !bomId(line[key]))
          errors[`${kind}.${index}.${key}`] = 'Choose a valid reference.';
      const quantity = kind === 'components' ? 'quantity' : 'nominal_quantity';
      if (!bomNumber(line[quantity]))
        errors[`${kind}.${index}.${quantity}`] =
          'Enter a positive exact quantity with up to four decimal places.';
      const fraction =
        kind === 'components' ? 'loss_fraction' : 'yield_fraction';
      if (
        !bomFraction(line[fraction], kind === 'components') ||
        (kind === 'components' && /^1(?:\.0+)?$/.test(String(line[fraction])))
      )
        errors[`${kind}.${index}.${fraction}`] =
          'Enter a valid fraction with up to eight decimal places.';
      if (
        kind === 'components' &&
        line.basis === 'GROSS_INPUT' &&
        /[1-9]/.test(String(line.loss_fraction))
      )
        errors[`${kind}.${index}.loss_fraction`] =
          'Gross input already includes its loss. Use zero here or choose net requirement.';
      if (
        kind === 'components' &&
        line.route_step_id &&
        !values.route_revision_id
      )
        errors[`${kind}.${index}.route_step_id`] =
          'Choose the route revision first.';
      return row;
    });
  }
  const outputs = new Set(values.outputs.map((line) => line.item_id));
  if (
    outputs.size !== values.outputs.length ||
    values.components.some((line) => outputs.has(line.item_id))
  )
    errors.outputs = 'Outputs must be distinct from each other and the inputs.';
  if (values.outputs.filter((line) => line.role === 'PRIMARY').length > 1)
    errors.outputs = 'Use only one primary output.';
  return { body, errors };
}

export function verifyBom(
  row: MasterRow,
  company: string,
  bom: string,
  id?: string,
) {
  if (
    row.company_id !== company ||
    !bomId(row.id) ||
    (id && row.id !== id) ||
    row.bom_id !== bom ||
    !Number.isSafeInteger(row.row_version) ||
    Number(row.row_version) < 1 ||
    !['DRAFT', 'PUBLISHED', 'RETIRED'].includes(String(row.status)) ||
    !Number.isSafeInteger(row.component_count) ||
    !Number.isSafeInteger(row.output_count) ||
    Number(row.component_count) < 0 ||
    Number(row.component_count) > 1000 ||
    Number(row.output_count) < 0 ||
    Number(row.output_count) > 100
  )
    throw {
      status: 502,
      message:
        'The BOM definition could not be verified. Reload before continuing.',
    };
}
export function verifyBomLines(
  pages: readonly ServicePage<MasterRow>[],
  parent: string,
  kind: 'draft_id' | 'revision_id',
  expected: number,
  fields: readonly string[],
): BomLine[] {
  if (
    !pages.length ||
    pages.at(-1)?.page.has_more ||
    pages.at(-1)?.page.next_cursor
  )
    throw { status: 502, message: 'The complete BOM line set is unavailable.' };
  const lines = pages.flatMap((page) => page.items),
    ids = new Set<string>(),
    keys = new Set<string>();
  if (lines.length !== expected)
    throw {
      status: 502,
      message: 'The BOM line count changed. Reload before editing.',
    };
  lines.forEach((line, index) => {
    if (
      !bomId(line.id) ||
      ids.has(line.id) ||
      line[kind] !== parent ||
      line.sequence !== index + 1 ||
      !bomId(line.line_key) ||
      keys.has(line.line_key) ||
      fields.some((key) => !(key in line))
    )
      throw {
        status: 502,
        message:
          'The BOM line set could not be verified. Reload before continuing.',
      };
    ids.add(line.id);
    keys.add(line.line_key);
  });
  return lines.map(
    (line) =>
      Object.fromEntries(fields.map((key) => [key, line[key]])) as BomLine,
  );
}
