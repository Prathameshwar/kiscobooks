import { describe, expect, it, vi } from 'vitest';
import { readPurchaseSelectionBalance } from '../app/lib/purchase-selection-balance';
import type { ServiceRequest } from '../app/lib/service-call';

const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const company = id(1), subject = id(2), warehouse = id(3);
const common = { company, subject, asOf: '2026-11-05', currency: 'INR', signal: new AbortController().signal };

describe('purchase selection balances', () => {
  it('reads an account at the posting date in base currency and verifies the ledger arithmetic', async () => {
    const read = vi.fn(async (_request: ServiceRequest) => ({ as_of: common.asOf, currency: 'INR', debit: '10.0000', credit: '30.0000', balance: '-20.0000' }));
    expect(await readPurchaseSelectionBalance(read as never, { ...common, kind: 'ACCOUNT' })).toEqual({ kind: 'ACCOUNT', amount: '20.0000', side: 'CR', asOf: common.asOf });
    expect(read).toHaveBeenCalledTimes(1);
    const request = read.mock.calls[0]![0];
    expect(request.service).toBe('accounting');
    expect(request.signal).toBe(common.signal);
    expect(Object.fromEntries(new URL(request.path, 'https://example.invalid').searchParams)).toEqual({ as_of: common.asOf, basis: 'BASE', currency: 'INR', account_id: subject });
    await expect(readPurchaseSelectionBalance((async () => ({ as_of: common.asOf, currency: 'INR', debit: '10.0000', credit: '30.0000', balance: '20.0000' })) as never, { ...common, kind: 'ACCOUNT' })).rejects.toThrow('could not be verified');
  });

  it('reads one indexed aggregate for the selected product and warehouse', async () => {
    const read = vi.fn(async (_request: ServiceRequest) => ({ item_id: subject, warehouse_id: warehouse, quantity: '3.3750' }));
    expect(await readPurchaseSelectionBalance(read as never, { ...common, kind: 'ITEM', warehouse })).toEqual({ kind: 'ITEM', quantity: '3.3750', warehouse: true });
    expect(read).toHaveBeenCalledTimes(1);
    expect(new URL(read.mock.calls[0]![0].path, 'https://example.invalid').pathname).toBe(`/v1/companies/${company}/stock/positions/balance`);
    expect(Object.fromEntries(new URL(read.mock.calls[0]![0].path, 'https://example.invalid').searchParams)).toEqual({ item_id: subject, warehouse_id: warehouse });
  });

  it('refuses mismatched or negative stock rather than showing an incorrect total', async () => {
    const input = { ...common, kind: 'ITEM' as const };
    await expect(readPurchaseSelectionBalance((async () => ({ item_id: id(9), warehouse_id: null, quantity: '1.0000' })) as never, input)).rejects.toThrow('could not be verified');
    await expect(readPurchaseSelectionBalance((async () => ({ item_id: subject, warehouse_id: null, quantity: '-1.0000' })) as never, input)).rejects.toThrow('could not be verified');
  });
});
