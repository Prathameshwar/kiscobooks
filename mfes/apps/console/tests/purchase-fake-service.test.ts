import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ACCOUNT_LIST_KEYS, COMPANY, SUPPLIERS, TYPE_REVISION, id, installFakeServices, payableOf, receivableOf, secondPayableOf, type FakeServices } from './purchase-fake-service';

/**
 * The stand-in services are only worth having if they refuse what the real ones refuse. These
 * tests hold the stand-ins to the rules the wire-flow test relies on, so a page that sends a stale
 * hash, an old type revision or a reused key fails there instead of passing against a lenient fake.
 */
const base = `/v1/companies/${COMPANY}`;
let services: FakeServices;
beforeEach(() => { services = installFakeServices(); });
afterEach(() => vi.unstubAllGlobals());

async function call(method: string, path: string, body?: unknown, key?: string) {
  const response = await fetch('/api/product-fields', { method: 'POST', body: JSON.stringify({ service: 'vouchers', method, path: base + path, body, key }) });
  return { status: response.status, body: await response.json() };
}
const bill = (amount: string, typeRevision = TYPE_REVISION) => ({
  type_revision_id: typeRevision, mode: 'ACCOUNTS', currency: 'INR', document_date: '2026-10-31',
  parties: [{ role: 'SUPPLIER', party_id: SUPPLIERS[0]!.id, source_version: 2 }],
  invoice: { party_account_id: payableOf(SUPPLIERS[0]!.id), party_account_version: 3, bill_reference: 'SOS/1', tax: { profile: 'UNTAXED_ACCOUNT' },
    supplies: [{ line_key: id(7), account_id: id(20), account_version: 4, amount, supply_kind: 'ACCOUNT', price_basis: 'NET_EXCL_TAX' }] },
});

describe('the Purchase stand-in services', () => {
  it('accepts only the calculation hash of the saved bill, and a different bill hashes differently', async () => {
    const one = (await call('POST', '/vouchers', bill('100'), 'create-one')).body;
    const two = (await call('POST', '/vouchers', bill('200'), 'create-two')).body;
    const hashOne = (await call('POST', `/vouchers/${one.id}/invoice-preview`, {})).body.calculation_hash;
    const hashTwo = (await call('POST', `/vouchers/${two.id}/invoice-preview`, {})).body.calculation_hash;
    expect(hashOne).toMatch(/^[0-9a-f]{64}$/);
    expect(hashOne).not.toBe(hashTwo);
    const wrong = await call('POST', `/vouchers/${one.id}/invoice-acceptance`, { expected_version: one.row_version, calculation_hash: hashTwo }, 'accept-wrong');
    expect(wrong.status).toBe(409);
    const right = await call('POST', `/vouchers/${one.id}/invoice-acceptance`, { expected_version: one.row_version, calculation_hash: hashOne }, 'accept-right');
    expect(right.status).toBe(200);
    expect(right.body.invoice.accepted_calculation_hash).toBe(hashOne);
  });

  it('refuses a write under a type revision that has been superseded', async () => {
    services.reviseType(id(77));
    const created = await call('POST', '/vouchers', bill('100'), 'create-old');
    expect(created.status).toBe(409);
    expect(created.body.error.message).toMatch(/retired or superseded/);
    expect((await call('POST', '/vouchers', bill('100', id(77)), 'create-new')).status).toBe(201);
  });

  it('refuses a key reused for a different request, and replays an identical one without a second effect', async () => {
    const first = await call('POST', '/vouchers', bill('100'), 'same-key');
    const replay = await call('POST', '/vouchers', bill('100'), 'same-key');
    expect(replay.body.id).toBe(first.body.id);
    expect(services.vouchers.size).toBe(1);
    const reused = await call('POST', '/vouchers', bill('999'), 'same-key');
    expect(reused.status).toBe(422);
    expect(reused.body.error.code).toBe('idempotency_key_reused');
    expect(services.vouchers.size).toBe(1);
  });
});

/**
 * The account list the Purchase page reads a supplier's payable from. The real service answers `role` as the account's own party role
 * (apis/accounting tasks/reads.py `listing`) and returns the lean `AccountListItem` (schemas/lists.py), so these hold the stand-in to the same,
 * and a page that asked for `party_role`, or took a receivable for a payable, would fail here rather than pass against a lenient fake.
 */
describe('the stand-in account and party lists', () => {
  async function read(path: string) {
    const response = await fetch('/api/product-fields', { method: 'POST', body: JSON.stringify({ service: 'accounting', method: 'GET', path: base + path }) });
    return { status: response.status, body: await response.json() };
  }
  const accountsOf = (party: string, role = '') => `/accounts?kind=PARTY&party_id=${party}${role ? '&role=' + role : ''}&status=ACTIVE&limit=200`;

  it('lists a supplier’s one payable by role, as the lean list item with the account’s party role', async () => {
    const { status, body } = await read(accountsOf(SUPPLIERS[0]!.id, 'SUPPLIER'));
    expect(status).toBe(200);
    expect(body.page.next_cursor).toBeNull();
    expect(body.items).toHaveLength(1);
    expect(body.items[0]).toMatchObject({ id: payableOf(SUPPLIERS[0]!.id), company_id: COMPANY, kind: 'PARTY', party_id: SUPPLIERS[0]!.id, party_role: 'SUPPLIER', status: 'ACTIVE' });
    for (const item of body.items) expect(Object.keys(item).filter(key => !ACCOUNT_LIST_KEYS.includes(key))).toEqual([]);
  });

  it('keeps a party that is also a customer’s receivable out of its payables, and its payable out of its receivables', async () => {
    const both = services.seedSupplier({ name: 'Mehta Trading', code: 'SUP-0040', alsoCustomer: true });
    expect(both.payables).toEqual([payableOf(both.id)]); expect(both.receivable).toBe(receivableOf(both.id));
    expect((await read(accountsOf(both.id, 'SUPPLIER'))).body.items.map((item: { id: string; party_role: string }) => [item.id, item.party_role])).toEqual([[payableOf(both.id), 'SUPPLIER']]);
    expect((await read(accountsOf(both.id, 'CUSTOMER'))).body.items.map((item: { id: string; party_role: string }) => [item.id, item.party_role])).toEqual([[receivableOf(both.id), 'CUSTOMER']]);
    // With no role both come back, which is exactly why a bill must ask for one.
    expect((await read(accountsOf(both.id))).body.items.map((item: { party_role: string }) => item.party_role).sort()).toEqual(['CUSTOMER', 'SUPPLIER']);
    // Its detail names the same role, which is what a reader checks before using the account.
    expect((await read(`/accounts/${receivableOf(both.id)}`)).body).toMatchObject({ party_id: both.id, party_role: 'CUSTOMER', kind: 'PARTY' });
  });

  it('lists no payable for a supplier that has none, and both for one that has two (older data a repair is for)', async () => {
    const none = services.seedSupplier({ name: 'No Ledger Traders', code: 'SUP-0041', payables: 0 });
    const two = services.seedSupplier({ name: 'Twin Ledger Traders', code: 'SUP-0042', payables: 2 });
    expect(none.payables).toEqual([]);
    expect((await read(accountsOf(none.id, 'SUPPLIER'))).body.items).toEqual([]);
    expect(two.payables).toEqual([payableOf(two.id), secondPayableOf(two.id)]);
    expect((await read(accountsOf(two.id, 'SUPPLIER'))).body.items.map((item: { id: string }) => item.id)).toEqual(two.payables);
  });

  it('answers BROKER as the OTHER account role, which a supplier has no account in', async () => {
    expect((await read(accountsOf(SUPPLIERS[0]!.id, 'BROKER'))).body.items).toEqual([]);
    expect((await read(accountsOf(SUPPLIERS[0]!.id, 'OTHER'))).body.items).toEqual([]);
  });

  it.each([
    ['an unknown role', accountsOf(SUPPLIERS[0]!.id, 'VENDOR')],
    ['a limit above 200', `/accounts?kind=PARTY&party_id=${SUPPLIERS[0]!.id}&role=SUPPLIER&limit=201`],
    ['a status outside DRAFT, ACTIVE and INACTIVE', `/accounts?kind=PARTY&party_id=${SUPPLIERS[0]!.id}&status=OPEN`],
    ['party_role, which is a field of the account and not a query parameter', `/accounts?kind=PARTY&party_id=${SUPPLIERS[0]!.id}&party_role=SUPPLIER&status=ACTIVE&limit=200`],
  ])('refuses %s, as the service does', async (_name, path) => {
    expect((await read(path)).status).toBe(422);
  });

  it('lists a party’s roles as the roles it really has, and a supplier list as the parties with an active supplier role', async () => {
    const both = services.seedSupplier({ name: 'Mehta Trading', code: 'SUP-0040', alsoCustomer: true });
    expect((await read(`/party-roles?party_id=${both.id}&limit=50`)).body.items.map((item: { role: string }) => item.role)).toEqual(['SUPPLIER', 'CUSTOMER']);
    expect((await read(`/party-roles?party_id=${SUPPLIERS[0]!.id}&role=CUSTOMER&limit=50`)).body.items).toEqual([]);
    expect((await read('/parties?role=SUPPLIER&status=ACTIVE&limit=50')).body.items.map((item: { id: string }) => item.id)).toEqual([...SUPPLIERS.map(row => row.id), both.id]);
  });
});
