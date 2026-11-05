import { expect, it } from 'vitest';
import {
  accountCreationContext,
  accountCreationReason,
  accountRelatedActions,
} from '../app/lib/account-related-actions';
import {
  accountingLink,
  accountingResource,
} from '../app/lib/accounting-configuration-resources';
import { form, ID, PARTY, record } from './accounting-configuration-fixtures';

const fields = form('accounts', 'read').fields;
it.each([
  ['account-aliases', 'GENERAL', 'DRAFT', null, undefined],
  ['account-external-keys', 'GENERAL', 'ACTIVE', null, undefined],
  ['account-bank-profiles', 'BANK', 'DRAFT', null, undefined],
  ['account-tax-profiles', 'TAX', 'DRAFT', null, undefined],
  ['account-bank-profiles', 'BANK', 'ACTIVE', null, /unused draft/],
  ['account-tax-profiles', 'TAX', 'DRAFT', undefined, /usage must be readable/],
  ['account-bank-profiles', 'BANK', 'DRAFT', '2030-01-01', /unused draft/],
  ['account-bank-profiles', 'GENERAL', 'DRAFT', null, /bank account/],
  ['account-tax-profiles', 'GENERAL', 'DRAFT', null, /tax account/],
  ['account-tax-defaults', 'GENERAL', 'DRAFT', null, /Activate/],
  ['account-tax-defaults', 'GENERAL', 'ACTIVE', null, undefined],
  ['account-tax-defaults', 'BANK', 'ACTIVE', null, /general account/],
  ['posting-mappings', 'GENERAL', 'ACTIVE', null, undefined],
  ['charge-policies', 'GENERAL', 'ACTIVE', null, /party account/],
  ['charge-policies', 'PARTY', 'ACTIVE', null, undefined],
  ['account-aliases', 'GENERAL', 'INACTIVE', null, /Retired accounts/],
  ['account-aliases', 'GENERAL', null, null, /status must be readable/],
])(
  'checks native eligibility for %s / %s / %s',
  (resource, kind, status, used_at, expected) => {
    const result = accountCreationReason(
      resource,
      {
        ...record('accounts'),
        kind,
        status,
        used_at,
        party_id: PARTY,
        party_role: 'CUSTOMER',
      },
      fields,
      ['parties'],
    );
    if (expected) expect(result).toMatch(expected);
    else expect(result).toBeUndefined();
  },
);
it('withholds reference links and creation hints when their field is protected', () => {
  const protectedFields = fields.map((field) => ({
    ...field,
    readable: false,
  }));
  const row = {
    ...record('accounts'),
    status: 'ACTIVE',
    kind: 'BANK',
    used_at: null,
  };
  const items = accountRelatedActions(
    row,
    protectedFields,
    '/accounting/accounts/' + ID,
    ['account-bank-profiles', 'account-groups'],
    ['account-bank-profiles'],
  );
  expect(
    items.find((item) => item.id === 'open-account-groups'),
  ).toBeUndefined();
  expect(
    items.find((item) => item.id === 'create-account-bank-profiles')
      ?.disabledReason,
  ).toMatch(/kind must be readable/);
});
it('does not infer child read permission from a manage capability', () => {
  expect(
    accountRelatedActions(
      record('accounts'),
      fields,
      '/accounting/accounts/' + ID,
      [],
      ['account-aliases'],
    ),
  ).toEqual([]);
});
it('requires party read access for charge policies and omits malformed references', () => {
  const row = {
    ...record('accounts'),
    status: 'ACTIVE',
    kind: 'PARTY',
    party_id: PARTY,
    party_role: 'SUPPLIER',
    group_id: '/unsafe',
  };
  expect(accountCreationReason('charge-policies', row, fields, [])).toMatch(
    /permission to read its party/,
  );
  expect(
    accountRelatedActions(
      row,
      fields,
      '/accounting/accounts/' + ID,
      ['account-groups'],
      [],
    ).some((item) => item.id === 'open-account-groups'),
  ).toBe(false);
});
it('resolves only a validated account context in a nested return chain', () => {
  const config = accountingResource('account-aliases')!;
  const account = accountingLink(
    '/accounting/accounts/' + ID,
    '/accounting/accounts',
  );
  const back = accountingLink(
    '/accounting/account-aliases?account_id=' + ID,
    account,
  );
  expect(accountCreationContext(config, back)).toEqual({
    accountId: ID,
    href: account,
  });
  expect(
    accountCreationContext(
      config,
      'https://external.invalid/accounting/accounts/' + ID,
    ),
  ).toBeNull();
  expect(
    accountCreationContext(config, '/accounting/accounts/not-an-id'),
  ).toBeNull();
  expect(
    accountCreationContext(accountingResource('parties')!, account),
  ).toBeNull();
});
it.each(['currency', 'currency_mode'])(
  'explains protected %s before offering charge creation',
  (key) => {
    const restricted = fields.map((field) =>
      field.key === key ? { ...field, readable: false } : field,
    );
    const row = {
      ...record('accounts'),
      status: 'ACTIVE',
      kind: 'PARTY',
      party_id: PARTY,
      party_role: 'CUSTOMER',
    };
    expect(
      accountCreationReason('charge-policies', row, restricted, ['parties']),
    ).toMatch(/attributes must be readable/);
  },
);
