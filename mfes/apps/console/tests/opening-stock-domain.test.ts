import { beforeEach, expect, it, vi } from 'vitest';
import { decimal, sum, validateAllocation } from '../app/lib/opening-stock';
import { openingDraftDocument } from '../app/lib/opening-stock-drafts';
import { productFieldRequest } from '../app/lib/product-fields';
import {
  COMPANY,
  CONTROL,
  ITEM,
  UNIT,
  allocation,
  control,
  manifest,
} from './opening-stock-fixtures';
vi.mock('../app/lib/product-fields', () => ({ productFieldRequest: vi.fn() }));
beforeEach(() => {
  vi.mocked(productFieldRequest)
    .mockReset()
    .mockImplementation(async (_service, _method, path) => {
      if (path.includes('/field-set'))
        return {
          native: { properties: { stock: {}, stock_date: {} } },
          configuration: {
            kind: 'STOCK_JOURNAL',
            profile: 'OPENING',
            type_revision_id: CONTROL,
            policy: { stock: {} },
          },
        } as never;
      return {
        id: ITEM,
        company_id: COMPANY,
        status: 'ACTIVE',
        row_version: 7,
        base_unit_id: UNIT,
      } as never;
    });
});
it.each([
  '',
  '-1',
  '1e3',
  'NaN',
  'Infinity',
  '1.00001',
  '1000000000000000',
  '01',
  ' 1',
])('rejects non-storage decimal %s', (value) =>
  expect(decimal(value)).toBe(false),
);
it('sums decimal values without floating-point drift', () => {
  expect(sum(['0.1', '0.2', '999999999999999.9999'])).toBe(
    '1000000000000000.2999',
  );
  expect(decimal('0', true)).toBe(false);
  expect(decimal('0.0001', true)).toBe(true);
});
it('requires explicit value, zero reason and positive linked GL coverage', () => {
  const row = allocation();
  expect(
    validateAllocation({ ...row, received_value: null }, 'COMBINED'),
  ).toMatch(/explicit/);
  expect(
    validateAllocation({ ...row, received_value: '0' }, 'COMBINED'),
  ).toMatch(/zero/);
  expect(validateAllocation(row, 'LINKED_GL')).toMatch(/posted/);
  expect(
    validateAllocation(
      { ...row, received_value: '0', zero_value_reason: 'Approved free stock' },
      'LINKED_GL',
    ),
  ).toBeNull();
});
it('builds bounded ordered native drafts with current item proofs and company control', async () => {
  const lines = Array.from({ length: 101 }, (_, index) => ({
    ...allocation('opening-' + index),
    opening: { ...allocation().opening!, cohort_order: 101 - index },
  }));
  const result = await openingDraftDocument(
    COMPANY,
    control,
    { ...manifest, lines },
    CONTROL,
  );
  expect(result?.vouchers).toHaveLength(2);
  expect(result?.vouchers[0]?.stock?.lines).toHaveLength(100);
  expect(result?.vouchers[0]?.stock?.opening_control_id).toBe(control.id);
  expect(result?.vouchers[0]?.posting_date).toBe(manifest.stock_date);
  expect(result?.vouchers[0]?.lines?.[0]?.item.item_version).toBe(7);
  expect(result?.vouchers[0]?.stock?.lines[0]?.opening?.cohort_order).toBe(1);
  expect(
    vi
      .mocked(productFieldRequest)
      .mock.calls.filter((call) => call[2].includes('/items/')),
  ).toHaveLength(1);
});
it('refuses another company’s product proof', async () => {
  const original = vi.mocked(productFieldRequest).getMockImplementation()!;
  vi.mocked(productFieldRequest).mockImplementation(async (...args) =>
    args[2].includes('/items/')
      ? ({
          id: ITEM,
          company_id: CONTROL,
          status: 'ACTIVE',
          row_version: 7,
          base_unit_id: UNIT,
        } as never)
      : original(...args),
  );
  await expect(
    openingDraftDocument(COMPANY, control, manifest, CONTROL),
  ).rejects.toThrow(/verified/);
});

it('uses native ASCII cohort ordering across the 100-line chunk boundary', async () => {
  const lines = Array.from({ length: 100 }, (_, index) => allocation('cohort_' + String(index).padStart(3, '0')));
  lines.push(allocation('cohort-last'));
  const result = await openingDraftDocument(COMPANY, control, { ...manifest, lines }, CONTROL);
  expect(result!.vouchers).toHaveLength(2);
  expect(result!.vouchers[0]!.stock!.lines[0]!.opening!.source_key).toBe('cohort-last');
  expect(result!.vouchers[1]!.stock!.lines[0]!.opening!.source_key).toBe('cohort_099');
});

it('orders source keys after the same case normalization as native capture', async () => {
  const keys = ['z', 'A', 'b', 'a_b', 'a-b', 'a.b', 'a/b', 'a:b'];
  const result = await openingDraftDocument(COMPANY, control,
    { ...manifest, lines: keys.map((key) => allocation(key)) }, CONTROL);
  const ordered = result!.vouchers[0]!.stock!.lines.map((line) => line.opening!.source_key.toLowerCase());
  expect(ordered).toEqual(['a', 'a-b', 'a.b', 'a/b', 'a:b', 'a_b', 'b', 'z']);
});
