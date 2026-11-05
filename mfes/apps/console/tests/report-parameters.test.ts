import { expect, it } from 'vitest';
import { parameterText, reportParameters } from '../app/lib/report-parameters';
it('preserves exact decimal text while typing counts, flags and age bucket lists', () => {
  expect(reportParameters({ amount: { type: 'string' }, days: { type: 'integer' }, inactive: { type: 'boolean' }, buckets: { type: 'array', items: { type: 'integer' } } }, { amount: '999999999999999.1234', days: '90', inactive: 'false', buckets: '30, 90, 180' })).toEqual({ amount: '999999999999999.1234', days: 90, inactive: false, buckets: [30, 90, 180] });
  expect(parameterText([30, 90, 180])).toBe('30, 90, 180');
});
it.each(['1.5', '1e2', 'NaN', '9007199254740992', '30, ,90'])('refuses invalid integer-list value %s before creating a report', value => {
  expect(() => reportParameters({ buckets: { type: 'array', items: { type: 'integer' } } }, { buckets: value })).toThrow(/whole number/);
});
it('keeps incompatible currency filters out of base-currency totals', () => {
  expect(reportParameters({ basis: { type: 'string' }, currency: { type: 'string' } }, { basis: 'BASE', currency: 'INR' })).toEqual({ basis: 'BASE' });
});
it('rejects ambiguous boolean values instead of silently including records', () => {
  expect(() => reportParameters({ include_inactive: { type: 'boolean' } }, { include_inactive: 'yes' })).toThrow(/Choose whether/);
});
