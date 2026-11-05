import { expect, it } from 'vitest';
import { accountFilters, changeAccountOpening, editedOpeningError, automaticSource, withOpeningOffset, OFFSET_SOURCE } from '../app/lib/financial-opening-worksheet';
import { ACCOUNT, COMPANY, declaration, metadata } from './financial-opening-fixtures';

const account = { id: ACCOUNT, company_id: COMPANY, name: 'Buyer A', kind: 'PARTY', party_role: 'CUSTOMER', status: 'ACTIVE', currency_mode: 'BASE' };
it('requests alphabetical, scoped buyer/supplier/group lists and bounded search', () => {
  expect(new URLSearchParams(accountFilters('BUYER', null, 'Al')).get('sort')).toBe('name');
  expect(new URLSearchParams(accountFilters('BUYER', null, 'Al')).get('role')).toBe('CUSTOMER');
  expect(new URLSearchParams(accountFilters('SUPPLIER', null, '')).get('role')).toBe('SUPPLIER');
  expect(new URLSearchParams(accountFilters('OTHER', ACCOUNT, '')).get('group_id')).toBe(ACCOUNT);
  expect(new URLSearchParams(accountFilters('BUYER', null, 'A')).has('q')).toBe(false);
});
it('keeps exact amounts and explicitly marks a new party balance as on account', () => {
  const value = { ...declaration(), entries: [] };
  const rows = changeAccountOpening(value, account, { amount: '900719925474.1234' });
  expect(rows[0]).toMatchObject({ amount: '900719925474.1234', base_amount: '900719925474.1234', side: 'DEBIT', documents: [{ document_kind: 'ON_ACCOUNT', document_date: null, due_date: null, amount: '900719925474.1234' }] });
  expect(editedOpeningError({ ...value, entries: rows }, metadata)).toBeNull();
});
it('keeps historical bills intact and rejects a changed total until bills match', () => {
  const value = declaration();
  value.entries[0].documents = [{ document_kind: 'INVOICE', reference: 'Old invoice', document_date: '2026-03-01', due_date: '2026-03-31', amount: '100', base_amount: '100' }];
  const rows = changeAccountOpening(value, account, { amount: '125' });
  expect(rows[0].documents).toEqual(value.entries[0].documents);
  expect(editedOpeningError({ ...value, entries: rows }, metadata)).toMatch(/must equal/);
});
it('rejects malformed edited values before the source step, without requiring a balanced total yet', () => {
  const value = { ...declaration(), entries: [] };
  expect(editedOpeningError({ ...value, entries: changeAccountOpening(value, account, { amount: '-5' }) }, metadata)).toMatch(/positive/);
  expect(editedOpeningError({ ...value, entries: changeAccountOpening(value, account, { amount: '50' }) }, metadata)).toBeNull();
});
it('removes an opening explicitly set to zero and preserves unrelated account lines', () => {
  const value = declaration();
  expect(changeAccountOpening(value, account, { amount: '0.0000' })).toEqual([value.entries[1]]);
});
it('defaults only missing source evidence and never invents a clearing or offset account', () => {
  const value = { ...declaration(), reason: '' };
  const defaults = automaticSource(value);
  expect(defaults.reason).toBeTruthy();
  expect(defaults.source_id).toBe(value.source_id);
  expect(defaults.source_system).toBe(value.source_system);
  expect(defaults.clearing_account_id).toBeUndefined();
});
it('adds and recalculates a disclosed exact offset without accumulating duplicate offset entries', () => {
  const value = declaration();
  value.entries = [{ ...value.entries[0], amount: '900719925474.1234', base_amount: '900719925474.1234' }];
  const result = withOpeningOffset(value, '01990000-0000-7000-8000-000000000099');
  expect(result.entries[1]).toMatchObject({ source_key: OFFSET_SOURCE, side: 'CREDIT', amount: '900719925474.1234' });
  expect(withOpeningOffset(result, result.entries[1].account_id).entries).toEqual(result.entries);
  expect(withOpeningOffset({ ...value, entries: [{ ...value.entries[0], side: 'CREDIT' }] }, result.entries[1].account_id).entries[1].side).toBe('DEBIT');
  expect(() => withOpeningOffset(value, ACCOUNT)).toThrow(/cannot also/);
});
