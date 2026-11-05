import type {
  Allocation,
  Control,
  Manifest,
  OpeningAccess,
  Readiness,
} from '../app/lib/opening-stock';
export const COMPANY = '01990000-0000-7000-8000-000000000001',
  CONTROL = '01990000-0000-7000-8000-000000000002',
  ITEM = '01990000-0000-7000-8000-000000000003',
  UNIT = '01990000-0000-7000-8000-000000000004',
  REVISION = '01990000-0000-7000-8000-000000000005',
  WAREHOUSE = '01990000-0000-7000-8000-000000000006',
  JOB = '01990000-0000-7000-8000-000000000007';
export const page = { limit: 25, has_more: false, next_cursor: null };
export const access: OpeningAccess = {
  manage: true,
  draft: true,
  importRead: true,
  commit: true,
  zero: true,
  export: true,
};
export const readiness: Readiness = {
  company_id: COMPANY,
  control_id: CONTROL,
  books_begin_date: '2026-04-01',
  status: 'OPEN',
  can_start: false,
  posting_enabled: false,
  expected_generation: 8,
  can_confirm_zero: false,
  blockers: ['STOCK_POSTING_NOT_ENABLED'],
};
export const control: Control = {
  id: CONTROL,
  company_id: COMPANY,
  books_begin_date: '2026-04-01',
  currency: 'INR',
  status: 'OPEN',
  expected_version: 2,
  manifest_hash: 'a'.repeat(64),
  expected_cohorts: 1,
  applied_cohorts: 0,
  expected_value: '12.5000',
  applied_value: '0.0000',
  missing_source_keys: ['opening-a'],
  blockers: ['OPENING_COHORTS_MISSING'],
};
export function allocation(source = 'opening-a'): Allocation {
  return {
    line_id: crypto.randomUUID(),
    item_id: ITEM,
    warehouse_id: WAREHOUSE,
    quantity: '2.0000',
    received_value: '12.5000',
    opening: {
      source_key: source,
      entered_unit_id: UNIT,
      unit_revision_id: REVISION,
      entered_quantity: '2',
      cost_mode: 'VALUE',
      history_known: false,
      cohort_order: 1,
    },
    unit_ids: [],
  };
}
export const manifest: Manifest = {
  currency: 'INR',
  stock_date: '2026-04-01',
  opening_mode: 'COMBINED',
  reason: 'Reviewed opening stock',
  lines: [allocation()],
};
