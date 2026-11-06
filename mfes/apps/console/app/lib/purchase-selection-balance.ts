import * as D from './fixed-decimal';
import type { ServiceRequest } from './service-call';
import { trackingId } from './stock-tracking-resources';

type Reader = <T>(request: ServiceRequest) => Promise<T>;
export type SelectionBalance =
  | { kind: 'ACCOUNT'; amount: string; side: 'DR' | 'CR' | 'NIL'; asOf: string }
  | { kind: 'ITEM'; quantity: string; warehouse: boolean };

/** Advisory values only. A product's stock position is current, whereas a ledger balance is historical. */
export async function readPurchaseSelectionBalance(read: Reader, input: {
  company: string; kind: 'ACCOUNT' | 'ITEM'; subject: string; asOf: string; currency: string;
  warehouse?: string; signal: AbortSignal;
}): Promise<SelectionBalance> {
  const { company, kind, subject, asOf, currency, warehouse, signal } = input;
  if (!trackingId.test(company) || !trackingId.test(subject) || (warehouse && !trackingId.test(warehouse))) throw Error('Invalid balance selection.');
  const base = `/v1/companies/${company}`;
  if (kind === 'ACCOUNT') {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(asOf) || !/^[A-Z]{3}$/.test(currency)) throw Error('Invalid balance date or currency.');
    const row = await read<{ as_of?: unknown; currency?: unknown; debit?: unknown; credit?: unknown; balance?: unknown }>({
      service: 'accounting', signal, path: base + '/ledger/balance?' + new URLSearchParams({ as_of: asOf, basis: 'BASE', currency, account_id: subject }),
    });
    const debit = typeof row?.debit === 'string' ? D.parse(row.debit) : null;
    const credit = typeof row?.credit === 'string' ? D.parse(row.credit) : null;
    const balance = typeof row?.balance === 'string' ? D.parse(row.balance) : null;
    if (row?.as_of !== asOf || row?.currency !== currency || debit === null || credit === null || balance === null || debit - credit !== balance) throw Error('Account balance could not be verified.');
    return { kind, amount: D.format(balance < 0n ? -balance : balance), side: balance < 0n ? 'CR' : balance > 0n ? 'DR' : 'NIL', asOf };
  }
  const query = new URLSearchParams({ item_id: subject, ...(warehouse ? { warehouse_id: warehouse } : {}) });
  const row = await read<{ item_id?: unknown; warehouse_id?: unknown; quantity?: unknown }>({ service: 'accounting', signal, path: base + '/stock/positions/balance?' + query });
  const quantity = typeof row?.quantity === 'string' ? D.parse(row.quantity) : null;
  if (row?.item_id !== subject || (row.warehouse_id ?? null) !== (warehouse ?? null) || quantity === null || quantity < 0n) throw Error('Product stock balance could not be verified.');
  return { kind, quantity: D.format(quantity), warehouse: !!warehouse };
}
