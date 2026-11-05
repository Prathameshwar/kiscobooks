import { expect, it } from 'vitest';
import { accountingBody } from '../app/lib/accounting-configuration';
import { form, record } from './accounting-configuration-fixtures';
it.each([
  ['withholding-rates', 'rate_percent', '-0.0001'],
  ['withholding-rates', 'no_pan_rate_percent', '100.0001'],
  ['payment-term-lines', 'percentage', '0'],
  ['payment-term-lines', 'percentage', '100.0001'],
] as const)(
  'checks native decimal bounds for %s %s %s',
  (resource, key, value) => {
    const values = record(resource);
    values[key] = value;
    expect(
      accountingBody(form(resource).fields, values).errors[key],
    ).toBeTruthy();
  },
);
