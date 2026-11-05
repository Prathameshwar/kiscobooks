import { describe, expect, it, vi } from 'vitest';
import { balanceDate, balanceSide, readSupplierBalance } from '../app/lib/purchase-supplier-balance';
import * as D from '../app/lib/fixed-decimal';
import type { ServiceRequest } from '../app/lib/service-call';

const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const base = `/v1/companies/${id(1)}`, supplier = id(10), account = id(1010), other = id(1011);
const ledger = (debit: string, credit: string, patch: Record<string, unknown> = {}) => ({ as_of: '2026-11-02', currency: 'INR', debit, credit, balance: D.format(D.parse(debit)! - D.parse(credit)!), ...patch });
const input = (payables: readonly string[] = [account]) => ({ base, supplier, payables, asOf: '2026-11-02', currency: 'INR', signal: new AbortController().signal });

describe('the side of a supplier balance', () => {
  it('is Cr for a net credit, Dr for a net debit and nil at zero', () => {
    expect(balanceSide(-1n)).toBe('CR');
    expect(balanceSide(1n)).toBe('DR');
    expect(balanceSide(0n)).toBe('NIL');
  });
});

describe('the date a balance is read as of', () => {
  it('is the posting date, or today while the posting date is not a date', () => {
    expect(balanceDate('2026-10-31', '2026-11-02')).toBe('2026-10-31');
    expect(balanceDate('', '2026-11-02')).toBe('2026-11-02');
    expect(balanceDate('31/10/2026', '2026-11-02')).toBe('2026-11-02');
  });
});

describe('reading the balance of a supplier', () => {
  it('asks Accounting once per payable account, for the base currency, party and account, as of the date', async () => {
    const read = vi.fn(async (_: ServiceRequest) => ledger('0.0000', '125000.0000'));
    const signal = new AbortController().signal;
    await readSupplierBalance(read as never, { ...input(), signal });
    expect(read).toHaveBeenCalledTimes(1);
    const request = read.mock.calls[0]![0];
    expect(request.service).toBe('accounting');
    expect(request.signal).toBe(signal);
    expect(request.method ?? 'GET').toBe('GET');
    const [path, query] = request.path.split('?');
    expect(path).toBe(base + '/ledger/balance');
    expect(Object.fromEntries(new URLSearchParams(query))).toEqual({ as_of: '2026-11-02', basis: 'BASE', currency: 'INR', party_id: supplier, account_id: account });
  });

  it('turns a net credit into an amount owed, without a sign', async () => {
    const value = await readSupplierBalance((async () => ledger('25000.0000', '150000.0000')) as never, input());
    expect(value).toEqual({ supplier, status: 'ready', side: 'CR', amount: '125000.0000', asOf: '2026-11-02', currency: 'INR' });
  });

  it('turns a net debit into an amount to receive', async () => {
    const value = await readSupplierBalance((async () => ledger('5000.5000', '0.0000')) as never, input());
    expect(value).toMatchObject({ side: 'DR', amount: '5000.5000' });
  });

  it('is nil when the account nets to nothing', async () => {
    const value = await readSupplierBalance((async () => ledger('700.0000', '700.0000')) as never, input());
    expect(value).toMatchObject({ side: 'NIL', amount: '0.0000' });
  });

  it('adds the accounts of a supplier that has more than one, netting a credit against a debit', async () => {
    const read = vi.fn(async (request: ServiceRequest) => request.path.includes(account) ? ledger('0.0000', '1000.2500') : ledger('400.0000', '0.0000'));
    const value = await readSupplierBalance(read as never, input([account, other]));
    expect(read).toHaveBeenCalledTimes(2);
    expect(value).toMatchObject({ side: 'CR', amount: '600.2500' });
  });

  it('refuses a supplier with no payable account, and a date that is not one, before asking anything', async () => {
    const read = vi.fn();
    await expect(readSupplierBalance(read as never, input([]))).rejects.toThrow('could not be requested');
    await expect(readSupplierBalance(read as never, { ...input(), asOf: '02/11/2026' })).rejects.toThrow('could not be requested');
    expect(read).not.toHaveBeenCalled();
  });

  it.each([
    ['another date', ledger('0.0000', '10.0000', { as_of: '2026-11-01' })],
    ['another currency', ledger('0.0000', '10.0000', { currency: 'USD' })],
    ['a balance that is not debit minus credit', ledger('0.0000', '10.0000', { balance: '-9.0000' })],
    ['a figure that is not a decimal', ledger('0.0000', '10.0000', { balance: 'ten' })],
    ['a numeric figure instead of text', ledger('0.0000', '10.0000', { debit: 0 })],
    ['a missing figure', { as_of: '2026-11-02', currency: 'INR', debit: '0.0000', credit: '10.0000' }],
    ['an empty body', {}],
  ])('refuses an answer that cannot be proved: %s', async (_name, answer) => {
    await expect(readSupplierBalance((async () => answer) as never, input())).rejects.toThrow('could not be verified');
  });

  it('refuses the whole supplier when any one account cannot be proved', async () => {
    const read = async (request: ServiceRequest) => request.path.includes(account) ? ledger('0.0000', '10.0000') : ledger('0.0000', '10.0000', { currency: 'USD' });
    await expect(readSupplierBalance(read as never, input([account, other]))).rejects.toThrow('could not be verified');
  });

  it('lets a failed read through, so the page can say the balance is unavailable', async () => {
    await expect(readSupplierBalance((async () => { throw { status: 403, message: 'denied' }; }) as never, input())).rejects.toMatchObject({ status: 403 });
  });
});
