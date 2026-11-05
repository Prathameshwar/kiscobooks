import type { components } from '@janso/api-client/accounting';
import { accountingUUID } from './accounting-configuration-resources';
import { validMasterDate } from './catalog-masters';
export type ExchangeContext = components['schemas']['RateContext'];
export type ExchangeQuote = components['schemas']['RateView'];
export type ExchangeQuoteItem = components['schemas']['RateListItem'];
export type ExchangeCandidate = components['schemas']['RateCandidate'];
export const exchangePurposes = [
  'ACCOUNTING',
  'GST_GOODS',
  'GST_SERVICES',
  'REVALUATION',
  'SETTLEMENT',
] as const;
export const exactExchangeRate = (value: unknown) =>
  typeof value === 'string' &&
  /^\d{1,15}(?:\.\d{1,12})?$/.test(value) &&
  /[1-9]/.test(value);
export function verifyExchangeContext(value: ExchangeContext, company: string) {
  if (
    !value ||
    value.company_id !== company ||
    !/^[A-Z]{3}$/.test(value.base_currency) ||
    !Array.isArray(value.allowed_currencies) ||
    value.allowed_currencies.some((code) => !/^[A-Z]{3}$/.test(code)) ||
    typeof value.multi_currency !== 'boolean'
  )
    throw {
      status: 502,
      message: 'Currency settings could not be verified for this company.',
    };
}
export function verifyExchangeItem(value: ExchangeQuoteItem) {
  if (
    !value ||
    !accountingUUID.test(value.id) ||
    !exactExchangeRate(value.rate) ||
    !['CANDIDATE', 'APPROVED', 'WITHDRAWN'].includes(value.status) ||
    !exchangePurposes.includes(value.purpose) ||
    !validMasterDate(value.effective_date) ||
    !/^[A-Z]{3}$/.test(value.from_currency) ||
    !/^[A-Z]{3}$/.test(value.to_currency)
  )
    throw { status: 502, message: 'The exchange quote could not be verified.' };
}
export function verifyExchangeQuote(
  value: ExchangeQuote,
  company: string,
  id?: string,
) {
  verifyExchangeItem(value);
  if (
    value.company_id !== company ||
    (id && value.id !== id) ||
    !Number.isSafeInteger(value.row_version) ||
    value.row_version < 1
  )
    throw {
      status: 502,
      message: 'The exchange quote could not be verified for this company.',
    };
}
export function exchangeCandidate(
  values: Record<string, string>,
  context: ExchangeContext,
) {
  const errors: Record<string, string> = {},
    body = {
      ...values,
      to_currency: context.base_currency,
      source_kind: values.purpose === 'GST_GOODS' ? 'CUSTOMS' : 'MANUAL',
      source_reference: values.source_reference.trim(),
    };
  if (
    !context.multi_currency ||
    !context.allowed_currencies.includes(values.from_currency) ||
    values.from_currency === context.base_currency
  )
    errors.from_currency = 'Choose an enabled foreign currency.';
  if (
    !exchangePurposes.includes(
      values.purpose as (typeof exchangePurposes)[number],
    )
  )
    errors.purpose = 'Choose a quote purpose.';
  if (!validMasterDate(values.effective_date))
    errors.effective_date = 'Enter a valid effective date.';
  if (!exactExchangeRate(values.rate))
    errors.rate = 'Enter a positive exact rate with up to 12 decimal places.';
  if (
    body.source_reference.length < 3 ||
    body.source_reference.length > 500 ||
    /[\x00-\x1f\x7f]/.test(body.source_reference)
  )
    errors.source_reference =
      'Enter a source reference between 3 and 500 printable characters.';
  return { body, errors };
}
