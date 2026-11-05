import { beforeEach, expect, it, vi } from 'vitest';
import { buildPurchase, purchaseAvailability, purchaseLookup, purchaseSource } from '../app/lib/purchase-entry';
import { productFieldRequest } from '../app/lib/product-fields';
vi.mock('../app/lib/product-fields', () => ({ productFieldRequest: vi.fn() }));
import { company, draft, metadata } from './purchase-entry-fixtures';
const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
beforeEach(() => { vi.mocked(productFieldRequest).mockReset(); });
it('identifies incompatible required sections instead of allowing a bill that cannot submit', () => {
  const value = structuredClone(metadata);
  value.configuration.policy.required_sections = ['ITEMS', 'CHARGES'];
  value.configuration.policy.invoice!.charges_allowed = false;
  value.configuration.policy.invoice!.manual_discounts_allowed = false;
  const message = purchaseAvailability(value);
  expect(message).toContain('Item lines are required');
  expect(message).toContain('Charges are required');
  expect(message).toContain('Required sections');
});
it('sends exact native invoice, supplier and external reference facts without calculating', () => {
  const body = buildPurchase(company, draft, '2026-10-30', metadata);
  expect(body).toMatchObject({ mode: 'ACCOUNTS', invoice: { party_account_version: 3, tax: { profile: 'UNTAXED_ACCOUNT' }, supplier_declared_total: '42.1234', supplies: [{ amount: '42.1234', account_version: 4, supply_kind: 'ACCOUNT' }] }, parties: [{ party_id: id(3), source_version: 2, role: 'SUPPLIER' }], references: [{ purpose: 'SUPPLIER_INVOICE', reference: 'SUP-42', reference_date: '2026-10-30' }] });
  expect(body.invoice).not.toHaveProperty('accepted_calculation_hash');
});
it.each(['0', '-1', '1e2', '42.12345', '1000000000000000', 'NaN'])('refuses invalid line amount %s before a write', amount => {
  expect(() => buildPurchase(company, { ...draft, supplies: [{ ...draft.supplies[0]!, amount }] }, '2026-10-30', metadata)).toThrow(/positive amount/);
});
it.each([
  { ...draft, party: { ...draft.party!, company: id(9) } },
  { ...draft, payable: { ...draft.payable!, partyId: id(9) } },
  { ...draft, supplies: [{ ...draft.supplies[0]!, account: { ...draft.supplies[0]!.account!, version: 0 } }] },
  { ...draft, dueDate: '2026-10-29' }, { ...draft, dueDate: '2026-02-30' },
  { ...draft, reference: '\u0000wrong' }, { ...draft, supplies: [] },
  { ...draft, supplies: [draft.supplies[0]!, draft.supplies[0]!] },
])('refuses stale/foreign/incomplete purchase facts', value => {
  expect(() => buildPurchase(company, value, '2026-10-30', metadata)).toThrow();
});
it('fails closed when invoice authority or the supported profile is absent', () => {
  expect(purchaseAvailability({ ...metadata, native: { properties: { ...metadata.native.properties, invoice: { readOnly: true } } } })).toMatch(/write access/);
  expect(purchaseAvailability({ ...metadata, configuration: { ...metadata.configuration, profile: 'OTHER' } })).toMatch(/Standard Purchase.*OTHER/);
});
it('binds supplier account lookup and its signed cursor to the selected company and supplier', async () => {
  vi.mocked(productFieldRequest).mockResolvedValue({ items: [{ id: id(4), company_id: company, name: 'Payable' }], page: { next_cursor: 'signed-cursor' } });
  const result = await purchaseLookup(company, 'payables', id(3))({ q: 'QA', cursor: 'prior-cursor', signal: new AbortController().signal });
  const path = vi.mocked(productFieldRequest).mock.calls[0]?.[2] ?? '';
  expect(path).toContain(`/companies/${company}/accounts?`); expect(path).toContain('party_id=' + id(3)); expect(path).not.toContain('party_role='); expect(path).toContain('cursor=prior-cursor');
  expect(result.nextCursor).toBe('signed-cursor');
  vi.mocked(productFieldRequest).mockResolvedValue({ items: [{ id: id(4), company_id: id(9), name: 'Foreign' }], page: { next_cursor: null } });
  await expect(purchaseLookup(company, 'suppliers')({ q: '', cursor: null, signal: new AbortController().signal })).rejects.toThrow(/could not be verified/);
});
it('verifies an active supplier payable and rejects another supplier or company', async () => {
  const row = { id: id(4), company_id: company, row_version: 3, name: 'Payable', status: 'ACTIVE', kind: 'PARTY', party_id: id(3), party_role: 'SUPPLIER' };
  vi.mocked(productFieldRequest).mockResolvedValue(row);
  await expect(purchaseSource(company, 'payables', id(4), id(3))).resolves.toMatchObject({ version: 3, partyId: id(3) });
  await expect(purchaseSource(company, 'payables', id(4), id(9))).rejects.toThrow(/as appropriate/);
  vi.mocked(productFieldRequest).mockResolvedValue({ ...row, company_id: id(9) });
  await expect(purchaseSource(company, 'payables', id(4), id(3))).rejects.toThrow(/unavailable/);
});
it('uses the native supplier role relation instead of expecting role on PartyDetail', async () => {
  vi.mocked(productFieldRequest).mockResolvedValueOnce({ id: id(3), company_id: company, row_version: 2, name: 'Supplier', status: 'ACTIVE' }).mockResolvedValueOnce({ items: [{ id: id(12), company_id: company, party_id: id(3), role: 'SUPPLIER' }], page: { next_cursor: null } });
  await expect(purchaseSource(company, 'suppliers', id(3))).resolves.toMatchObject({ id: id(3), version: 2 });
});
it('verifies expense head ownership and rejects an income account before capture', async () => {
  const api = vi.mocked(productFieldRequest), account = { id: id(7), company_id: company, row_version: 4, name: 'Expense', status: 'ACTIVE', kind: 'GENERAL', group_id: id(8), inventory_affected: false, posting_policy: 'MANUAL_ALLOWED' };
  api.mockResolvedValueOnce(account).mockResolvedValueOnce({ id: id(8), company_id: company, head_id: id(9) }).mockResolvedValueOnce({ id: id(9), company_id: company, nature: 'EXPENSE' });
  await expect(purchaseSource(company, 'expenses', id(7))).resolves.toMatchObject({ version: 4 });
  api.mockResolvedValueOnce(account).mockResolvedValueOnce({ id: id(8), company_id: company, head_id: id(9) }).mockResolvedValueOnce({ id: id(9), company_id: company, nature: 'INCOME' });
  await expect(purchaseSource(company, 'expenses', id(7))).rejects.toThrow(/expense head/);
});
