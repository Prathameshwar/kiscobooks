import type { components } from '@janso/api-client/identity';
import {
  accountingBack,
  accountingUUID,
} from './accounting-configuration-resources';

export const companyBankFields = [
  ['label', 'Bank label', 100, true],
  ['account_name', 'Account holder name', 200, true],
  ['bank_name', 'Bank name', 200, true],
  ['branch', 'Branch', 200, false],
  ['account_number', 'Account number', 60, false],
  ['iban', 'IBAN', 34, false],
  ['ifsc', 'IFSC', 11, false],
  ['swift', 'SWIFT / BIC', 11, false],
] as const;
export type CompanyBankDraft = Record<
  (typeof companyBankFields)[number][0] | 'currency_code',
  string
>;

export function companyBankBody(draft: CompanyBankDraft): {
  body: components['schemas']['BankWrite'];
  errors: Record<string, string>;
} {
  const errors: Record<string, string> = {};
  const values = Object.fromEntries(
    Object.entries(draft).map(([key, value]) => [key, value.trim()]),
  );
  for (const [key, label, max, required] of companyBankFields) {
    const value = values[key] ?? '';
    if (
      (required && !value) ||
      value.length > max ||
      /[\x00-\x1f\x7f]/.test(value)
    )
      errors[key] =
        `${label} must contain ${required ? '1 to ' : 'at most '}${max} printable characters.`;
  }
  if (!values.account_number && !values.iban)
    errors.account_number = 'Enter an account number or an IBAN.';
  if (
    values.account_number &&
    (values.account_number.length < 4 ||
      /[^\x20-\x7e]/.test(values.account_number))
  )
    errors.account_number = 'Use 4 to 60 ASCII characters.';
  if (
    values.iban &&
    (values.iban.length < 15 || /[^\x20-\x7e]/.test(values.iban))
  )
    errors.iban = 'Use 15 to 34 ASCII characters.';
  if (values.ifsc && !/^[A-Z]{4}0[A-Z0-9]{6}$/.test(values.ifsc))
    errors.ifsc = 'Enter a valid 11-character IFSC.';
  if (values.swift && !/^[A-Z0-9]{8}([A-Z0-9]{3})?$/.test(values.swift))
    errors.swift = 'Enter an 8- or 11-character SWIFT / BIC.';
  if (!/^[A-Z]{3}$/.test(values.currency_code ?? ''))
    errors.currency_code = 'Choose a currency.';
  return {
    errors,
    body: {
      label: values.label!,
      account_name: values.account_name!,
      bank_name: values.bank_name!,
      currency_code: values.currency_code!,
      is_primary: false,
      ...Object.fromEntries(
        ['branch', 'account_number', 'iban', 'ifsc', 'swift'].map((key) => [
          key,
          values[key] || null,
        ]),
      ),
    },
  };
}

/** A supporting form may return only to the bank-profile workflow, with a safe read parent. */
export function companyBankReturn(value?: string): string {
  const fallback = '/accounting/account-bank-profiles';
  try {
    if (
      !value?.startsWith('/') ||
      value.length > 4096 ||
      /[\\#\x00-\x1f\x7f]/.test(value) ||
      /%2f|%5c|%2e|\.\./i.test(value.split('?')[0]!)
    )
      return fallback;
    const url = new URL(value, 'https://console.invalid');
    const parts = url.pathname.split('/');
    if (
      url.origin !== 'https://console.invalid' ||
      parts[1] !== 'accounting' ||
      parts[2] !== 'account-bank-profiles' ||
      !(
        (parts.length === 4 && parts[3] === 'new') ||
        (parts.length === 5 &&
          accountingUUID.test(parts[3]!) &&
          parts[4] === 'edit')
      )
    )
      return fallback;
    const query = new URLSearchParams();
    if (
      url.searchParams.getAll('account_id').length === 1 &&
      accountingUUID.test(url.searchParams.get('account_id')!)
    )
      query.set('account_id', url.searchParams.get('account_id')!);
    const back = accountingBack(
      url.searchParams.get('returnTo') ?? undefined,
      '',
    );
    if (back) query.set('returnTo', back);
    return url.pathname + (query.size ? '?' + query : '');
  } catch {
    return fallback;
  }
}
