import type {DisplayConfig} from './format';

/** Authoritative Identity/Reports wire fields; never infer formats from browser locale. */
export type ResolvedDisplay = {
  base_currency: string; amount_precision: number; quantity_precision: number;
  rounding_mode: string; date_format: string; datetime_format: string;
  digit_grouping: string; currency_display: string; currency_symbol_override?: string|null;
  currency_symbol_position: string; decimal_separator: string; thousands_separator: string;
  negative_format: string; timezone: string; locale: string;
};

export function resolvedDisplay(values: ResolvedDisplay): DisplayConfig;
export function resolvedDisplay(values: Partial<ResolvedDisplay>): Partial<DisplayConfig>;
export function resolvedDisplay(values: Partial<ResolvedDisplay>): Partial<DisplayConfig> {
  return {
    currency: values.base_currency, amountPrecision: values.amount_precision,
    quantityPrecision: values.quantity_precision,
    roundingMode: values.rounding_mode as DisplayConfig['roundingMode'],
    dateFormat: values.date_format, datetimeFormat: values.datetime_format,
    digitGrouping: values.digit_grouping as DisplayConfig['digitGrouping'],
    currencyDisplay: values.currency_display as DisplayConfig['currencyDisplay'],
    currencySymbol: values.currency_symbol_override ?? values.base_currency,
    currencySymbolPosition: values.currency_symbol_position as DisplayConfig['currencySymbolPosition'],
    decimalSeparator: values.decimal_separator, groupSeparator: values.thousands_separator,
    negativeFormat: values.negative_format === 'parentheses' ? 'parens' : 'minus',
    timezone: values.timezone, locale: values.locale,
  };
}
