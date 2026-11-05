import type { MasterRow } from './catalog-masters';
import type { ServicePage } from './service-resource';
import { profileId, profileTemperature } from './product-profiles';

export const routeStepFields = [
  'sequence',
  'operation_revision_id',
  'setup_minutes',
  'run_minutes',
  'lead_time_minutes',
  'time_basis',
  'quantity_basis',
] as const;
export const routeStepNumbers = [
  'setup_minutes',
  'run_minutes',
  'lead_time_minutes',
  'quantity_basis',
] as const;
export type RouteStep = {
  id?: string;
  _key?: string;
  sequence: number;
  operation_revision_id: string;
  setup_minutes: string;
  run_minutes: string;
  lead_time_minutes: string;
  time_basis: 'PER_OUTPUT_UNIT' | 'PER_BATCH';
  quantity_basis: string;
};
export type OperationReference = {
  id: string;
  operation_id: string;
  code: string;
  name: string;
  revision: number;
  status: 'DRAFT' | 'PUBLISHED' | 'RETIRED';
  is_active: boolean;
};
const realId = (value: unknown): value is string =>
  typeof value === 'string' &&
  profileId.test(value) &&
  value !== '00000000-0000-0000-0000-000000000000';

export function routeStepBody(rows: readonly RouteStep[]) {
  const errors: Record<string, string> = {};
  if (rows.length > 50) errors.steps = 'Use at most 50 sequential steps.';
  const used = new Set<string>();
  const body = rows.map((row, index) => {
    const result = { ...row, sequence: index + 1 };
    delete result._key;
    if (row.id) {
      if (!realId(row.id) || used.has(row.id))
        errors.steps = 'Reload the complete step set before saving.';
      used.add(row.id);
    }
    if (!realId(row.operation_revision_id))
      errors[`steps.${index}.operation_revision_id`] =
        'Choose a published operation revision.';
    for (const key of routeStepNumbers) {
      const value = profileTemperature(row[key]);
      if (
        value === null ||
        value < 0n ||
        (key === 'quantity_basis' && value === 0n)
      )
        errors[`steps.${index}.${key}`] =
          key === 'quantity_basis'
            ? 'Enter an exact positive quantity basis with up to four decimal places.'
            : 'Enter a nonnegative time with up to four decimal places.';
    }
    if (!['PER_OUTPUT_UNIT', 'PER_BATCH'].includes(row.time_basis))
      errors[`steps.${index}.time_basis`] = 'Choose the time basis.';
    return result;
  });
  return { body, errors };
}

export function verifyRouteSteps(
  page: ServicePage<MasterRow>,
  revision: string,
  count: unknown,
): RouteStep[] {
  const fail = () => {
    throw {
      status: 502,
      message:
        'The complete route step set could not be verified. Reload before changing or publishing it.',
    };
  };
  if (
    !Array.isArray(page.items) ||
    !page.page ||
    page.page.has_more !== false ||
    page.page.next_cursor != null ||
    !Number.isSafeInteger(count) ||
    Number(count) < 0 ||
    Number(count) > 50 ||
    page.items.length !== count
  )
    return fail();
  const rows = page.items.map((row, index) => {
    if (
      !realId(row.id) ||
      row.revision_id !== revision ||
      row.sequence !== index + 1 ||
      routeStepFields.some((key) => !(key in row))
    )
      return fail();
    return Object.fromEntries(
      ['id', ...routeStepFields].map((key) => [key, row[key]]),
    ) as RouteStep;
  });
  if (Object.keys(routeStepBody(rows).errors).length) return fail();
  return rows;
}

export function verifyOperationReference(row: OperationReference, id?: string) {
  if (
    !row ||
    !realId(row.id) ||
    (id && row.id !== id) ||
    !realId(row.operation_id) ||
    typeof row.code !== 'string' ||
    typeof row.name !== 'string' ||
    !Number.isSafeInteger(row.revision) ||
    row.revision < 1 ||
    !['DRAFT', 'PUBLISHED', 'RETIRED'].includes(row.status) ||
    typeof row.is_active !== 'boolean'
  )
    throw {
      status: 502,
      message: 'The operation reference could not be verified.',
    };
  return row;
}
