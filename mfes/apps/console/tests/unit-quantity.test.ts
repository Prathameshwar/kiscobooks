import { expect, it } from 'vitest';
import {
  convertedGridStep,
  gridText,
  quantityTicks,
  unitGrid,
} from '../app/lib/unit-quantity';

it.each([
  ['1', '12', '1', '0.25', '0.01'],
  ['1', '1', '3', '3', '1'],
  ['0.001', '1', '1000', '1', '1'],
] as const)(
  'derives exact compatible steps for base %s ratio %s:%s',
  (base, numerator, denominator, expected, entered) => {
    const result = convertedGridStep(
      quantityTicks(entered)!,
      quantityTicks(base)!,
      BigInt(numerator),
      BigInt(denominator),
    );
    expect(result === null ? null : gridText(result)).toBe(expected);
  },
);
it('preserves exact large ratio parts and rejects an unrepresentable entered step', () => {
  const large = 9007199254740993n;
  expect(gridText(convertedGridStep(10000n, 10000n, large, large)!)).toBe('1');
  expect(
    convertedGridStep(10000n, 10000n, 1n, 9223372036854775807n),
  ).toBeNull();
});
it('checks wire decimal bounds and positive grids without floating-point coercion', () => {
  expect(quantityTicks('999999999999999.9999')).toBe(9999999999999999999n);
  expect(quantityTicks('0.0001')).toBe(1n);
  for (const value of [0.1, '1e-4', '1000000000000000', '-1', null])
    expect(quantityTicks(value)).toBeNull();
  expect(unitGrid(2, '0.0100')).toEqual({ precision: 2, step: 100n });
  expect(unitGrid(0, '0.5')).toBeNull();
  expect(unitGrid(null, '1')).toBeNull();
  expect(unitGrid(4, '0')).toBeNull();
});
