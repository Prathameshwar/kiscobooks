/**
 * The customer's receivable on the sales bill (PL-D06): a customer has exactly one receivable, so
 * choosing the customer chooses it. `resolveCustomer` asks Accounting for the CUSTOMER-role party
 * account only, counts only rows that really are in that role, and takes the account only when
 * exactly one remains. None, several, or a payable never become a guess.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../app/lib/sales-entry-api', async (original) => ({
  ...(await original<typeof import('../app/lib/sales-entry-api')>()),
  salesCall: vi.fn(),
}));

import { salesCall } from '../app/lib/sales-entry-api';
import { resolveCustomer } from '../app/lib/sales-entry-lookups';
import { allowedSalesEntryRequest } from '../app/lib/sales-entry-request-policy';
import type { SalesBinding } from '../app/lib/sales-entry-connection';

const COMPANY = '01990000-0000-7000-8000-000000000001';
const PARTY = '01990000-0000-7000-8000-0000000000c1';
const base = `/v1/companies/${COMPANY}`;

type Row = { id: string; row_version?: number; party_role?: string | null; status?: string };
const customerRow = (id: string, version = 3): Row => ({ id, row_version: version, party_role: 'CUSTOMER' });
const supplierRow = (id: string, version = 2): Row => ({ id, row_version: version, party_role: 'SUPPLIER' });

const binding = (partyAccountIds: readonly string[] | null = null): SalesBinding => ({
  typeId: 'type-1',
  typeName: 'Sales',
  typeRevisionId: 'rev-1',
  classId: null,
  digest: 'f'.repeat(64),
  taxProfiles: ['INDIA_DOMESTIC_SERVICE'],
  supplyAccountIds: null,
  partyAccountIds,
});
const context = (partyAccountIds: readonly string[] | null = null) => ({
  binding: binding(partyAccountIds),
  currency: 'INR',
  date: '2026-11-02',
});

type Call = { service: string; method: string; path: string; body?: unknown };
const calls: Call[] = [];
let accountRows: Row[] = [];
let creditFails = false;

const page = (items: unknown[]) => ({ items, page: { next_cursor: null, has_more: false, limit: 50 } });

beforeEach(() => {
  calls.length = 0;
  accountRows = [];
  creditFails = false;
  vi.mocked(salesCall).mockReset();
  vi.mocked(salesCall).mockImplementation((async (service: string, request: { path: string; method?: string; body?: unknown }) => {
    const call = { service, method: request.method ?? 'GET', path: request.path, body: request.body };
    calls.push(call);
    const route = request.path.split('?')[0]!.replace(base, '');
    if (route === `/parties/${PARTY}`) return { id: PARTY, row_version: 4 };
    // Whatever Accounting is asked for, the rows below come back: the code under test must not trust the filter alone.
    if (route === '/accounts') return page(accountRows);
    if (route === '/party-addresses') return page([{ id: 'addr-1', label: 'Head office', state_code: 'IN-KA' }]);
    if (route === '/party-address-uses') return page([{ address_id: 'addr-1', purpose: 'REGISTERED', is_default: true }]);
    if (route === '/credit/check') {
      if (creditFails) throw { status: 503, message: 'busy' };
      return { exposure: '10', limit: '100', overdue: '0' };
    }
    throw { status: 404, message: `unexpected ${service} ${call.method} ${route}` };
  }) as never);
});

const resolve = (partyAccountIds: readonly string[] | null = null) =>
  resolveCustomer(COMPANY, PARTY, context(partyAccountIds), new Map());
const accountLookup = () => calls.find((call) => call.path.split('?')[0]!.endsWith('/accounts'))!;

describe('what resolveCustomer asks Accounting for', () => {
  it('requests the active customer-role party account of the chosen party, and nothing wider', async () => {
    accountRows = [customerRow('receivable')];
    await resolve();
    const lookup = accountLookup();
    expect(lookup).toMatchObject({ service: 'accounting', method: 'GET' });
    expect(Object.fromEntries(new URLSearchParams(lookup.path.split('?')[1]))).toEqual({
      party_id: PARTY,
      kind: 'PARTY',
      role: 'CUSTOMER',
      status: 'ACTIVE',
      limit: '50',
    });
  });

  it('only makes calls the sales page’s proxy allows, including the role query', async () => {
    accountRows = [customerRow('receivable')];
    await resolve();
    expect(calls.length).toBeGreaterThanOrEqual(5);
    for (const call of calls) expect(allowedSalesEntryRequest(call.service, call.method, call.path)).toBe(true);
  });
});

describe('the receivable is taken only when exactly one customer account remains', () => {
  it('takes the single customer-role account, with its version', async () => {
    accountRows = [customerRow('receivable', 7)];
    const facts = await resolve();
    expect(facts.ref).toEqual({ partyId: PARTY, partyVersion: 4, account: { id: 'receivable', version: 7 } });
  });

  it('carries the state and the credit position of that account', async () => {
    accountRows = [customerRow('receivable')];
    const facts = await resolve();
    expect(facts.state).toBe('IN-KA');
    expect(facts.credit).toEqual({ limit: '100', outstanding: '10', overdue: '0' });
    expect(calls.find((call) => call.path.endsWith('/credit/check'))!.body).toMatchObject({ account_id: 'receivable' });
  });

  it('keeps the account when the credit check cannot be read', async () => {
    accountRows = [customerRow('receivable')];
    creditFails = true;
    const facts = await resolve();
    expect(facts.ref.account).toEqual({ id: 'receivable', version: 3 });
    expect(facts.credit).toBeNull();
  });

  it('gives no account when the party has none', async () => {
    accountRows = [];
    const facts = await resolve();
    expect(facts.ref.account).toBeNull();
    expect(facts.ref.partyId).toBe(PARTY);
    // The customer is still identified, so the page can say what is wrong with it.
    expect(facts.state).toBe('IN-KA');
  });

  it('gives no account when the party has two customer accounts: it never guesses the first', async () => {
    accountRows = [customerRow('first'), customerRow('second')];
    expect((await resolve()).ref.account).toBeNull();
  });

  it('gives no account for a row in the supplier role: a party that is also a supplier is never billed to its payable', async () => {
    accountRows = [supplierRow('payable')];
    expect((await resolve()).ref.account).toBeNull();
  });

  it.each([
    ['OTHER', 'OTHER'],
    ['no role at all', null],
    ['an absent role', undefined],
  ])('gives no account for a row in %s', async (_why, role) => {
    accountRows = [{ id: 'other', row_version: 1, party_role: role }];
    expect((await resolve()).ref.account).toBeNull();
  });

  it('takes the customer account when a supplier-role payable is returned beside it', async () => {
    accountRows = [supplierRow('payable'), customerRow('receivable', 5)];
    expect((await resolve()).ref.account).toEqual({ id: 'receivable', version: 5 });
  });

  it('gives no account when two customer accounts come back beside a payable', async () => {
    accountRows = [customerRow('first'), supplierRow('payable'), customerRow('second')];
    expect((await resolve()).ref.account).toBeNull();
  });

  it('does not ask the credit check about a customer with no receivable', async () => {
    accountRows = [customerRow('first'), customerRow('second')];
    const facts = await resolve();
    expect(facts.credit).toBeNull();
    expect(calls.some((call) => call.path.endsWith('/credit/check'))).toBe(false);
  });
});

describe('the policy’s party-account allowlist', () => {
  it('counts only allowlisted customer accounts: one of two allowlisted is exactly one', async () => {
    accountRows = [customerRow('first'), customerRow('second')];
    expect((await resolve(['second'])).ref.account).toEqual({ id: 'second', version: 3 });
  });

  it('gives no account when the allowlist names none of the customer accounts', async () => {
    accountRows = [customerRow('first')];
    expect((await resolve(['elsewhere'])).ref.account).toBeNull();
  });

  it('gives no account when the allowlist names both of two customer accounts', async () => {
    accountRows = [customerRow('first'), customerRow('second')];
    expect((await resolve(['first', 'second'])).ref.account).toBeNull();
  });

  it('gives no account when the allowlist names only a payable', async () => {
    accountRows = [supplierRow('payable'), customerRow('receivable')];
    expect((await resolve(['payable'])).ref.account).toBeNull();
  });

  it('gives no account when an empty allowlist names nothing', async () => {
    accountRows = [customerRow('receivable')];
    expect((await resolve([])).ref.account).toBeNull();
  });

  it('applies no allowlist when the policy names none', async () => {
    accountRows = [customerRow('receivable')];
    expect((await resolve(null)).ref.account).toEqual({ id: 'receivable', version: 3 });
  });
});
