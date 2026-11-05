import { expect, it } from 'vitest';
import { declarationError, entryError, previousDate, sum } from '../app/lib/financial-opening';
import { declaration, line } from './financial-opening-fixtures';
it('keeps exact amounts beyond Number safe integers and handles leap-year cutovers', () => {
  expect(sum(['999999999999999.0001', '0.0002'])).toBe('999999999999999.0003');
  expect(previousDate('2024-03-01')).toBe('2024-02-29');
  expect(declarationError(declaration())).toBeNull();
});
it.each(['', '0', '-1', '1e2', '1.00001', '1000000000000000'])('rejects invalid or out-of-range carrying values: %s', amount => {
  expect(entryError({ ...line(), amount }, declaration())).toBeTruthy();
});
it('requires balanced totals, valid references and explicit same-day coverage review', () => {
  const value = declaration(); value.entries[1]!.base_amount = '99'; value.entries[1]!.amount = '99';
  expect(declarationError(value)).toMatch(/must balance/);
  value.entries[1] = { ...value.entries[0]! };
  expect(declarationError(value)).toMatch(/unique source/);
  value.covered_through = value.posting_date;
  expect(declarationError(value)).toMatch(/same-day/);
});
it('preserves unknown-date on-account evidence and requires exact document totals', () => {
  const entry = { ...line(), documents: [{ line_sequence: 1, document_kind: 'ON_ACCOUNT' as const, document_date: null, due_date: null, reference: 'Legacy on account', amount: '100', base_amount: '100' }] };
  expect(entryError(entry, declaration())).toBeNull();
  entry.documents[0]!.amount = '99';
  expect(entryError(entry, declaration())).toMatch(/must equal/);
});
it('rejects outstanding beyond original face and incoherent dated documents', () => {
  const entry = { ...line(), documents: [{ document_kind: 'INVOICE' as const, document_date: '2026-03-01', due_date: '2026-02-01', reference: 'INV-1', amount: '100', original_amount: '90', base_amount: '100' }] };
  expect(entryError(entry, declaration())).toMatch(/original/);
  entry.documents[0]!.original_amount = '110';
  expect(entryError(entry, declaration())).toMatch(/dates/);
});
it('requires explicit YTD origin and continuous source coverage', () => {
  const value = { ...declaration(), coverage_mode: 'YTD_SUMMARY' as const, ytd_summary: [] };
  expect(declarationError(value)).toMatch(/originating/);
  expect(declarationError({ ...value, originating_year_start: '2025-04-01' })).toBeNull();
});

it.each([true, false])('rejects duplicate bill references or source keys across account lines (source=%s)', source => {
  const value = declaration();
  value.entries[1]!.account_id = value.entries[0]!.account_id;
  value.entries.forEach((entry, index) => { entry.documents = [{ document_kind: 'ON_ACCOUNT',
    document_date: null, due_date: null, amount: '100', base_amount: '100',
    reference: source ? 'Bill-' + index : index ? 'old-bill' : 'OLD-BILL',
    source_key: source ? index ? 'same-key' : 'SAME-KEY' : 'source-' + index }]; });
  expect(declarationError(value)).toMatch(/unique.*document|document.*unique/i);
});
