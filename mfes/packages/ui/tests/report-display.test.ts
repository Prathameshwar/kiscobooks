import { expect, it } from 'vitest';
import fixture from '../../../../libs/platform/tests/fixtures/report-display.json';
import { DEFAULT_DISPLAY_CONFIG, formatMoney, formatQuantity, formatDate, formatDateTime,
  type DisplayConfig } from '../src/lib/format';

it.each(fixture.cases)('agrees with the server for $kind $value', (sample) => {
  const config = { ...fixture.config, ...sample.config };
  const display: DisplayConfig = {
    ...DEFAULT_DISPLAY_CONFIG,
    currency: config.base_currency, amountPrecision: config.amount_precision,
    quantityPrecision: config.quantity_precision,
    roundingMode: config.rounding_mode as DisplayConfig['roundingMode'],
    dateFormat: config.date_format, datetimeFormat: config.datetime_format,
    digitGrouping: config.digit_grouping as DisplayConfig['digitGrouping'],
    decimalSeparator: config.decimal_separator, groupSeparator: config.thousands_separator,
    negativeFormat: config.negative_format === 'parentheses' ? 'parens' : 'minus',
    currencyDisplay: 'none', timezone: config.timezone, locale: config.locale,
  };
  const render = sample.kind === 'number' ? formatMoney : sample.kind === 'quantity'
    ? formatQuantity : sample.kind === 'date' ? formatDate : formatDateTime;
  expect(render(sample.value, display)).toBe(sample.expected);
});
