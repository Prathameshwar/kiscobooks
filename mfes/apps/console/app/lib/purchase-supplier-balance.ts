import * as D from './fixed-decimal';
import type { ServiceRequest } from './service-call';

/**
 * What a supplier is owed or owes, as the Purchase page shows it beside the supplier. It is read once,
 * when the supplier is chosen, and is advice only: Accounting decides every amount at posting, and
 * nothing here is saved with the bill or sent back to a service.
 *
 * `side` follows the books. A supplier's payable account is credit-normal, so a net credit (`CR`) is
 * money the company has yet to pay and a net debit (`DR`) is money the supplier holds for the company.
 */
export type SupplierBalance =
  | { supplier: string; status: 'loading' | 'unavailable' }
  | { supplier: string; status: 'ready'; side: 'CR' | 'DR' | 'NIL'; amount: string; asOf: string; currency: string };
export type ReadySupplierBalance = Extract<SupplierBalance, { status: 'ready' }>;

type Reader = <T>(request: ServiceRequest) => Promise<T>;
type LedgerBalance = { as_of?: unknown; currency?: unknown; debit?: unknown; credit?: unknown; balance?: unknown };

/** The key Accounting asks for on `GET /ledger/balance`; without it nothing is requested and nothing is shown. */
export const SUPPLIER_BALANCE_PERMISSION = 'ledger.read';
/** A balance that has not come back by now is shown as unavailable; the bill never waits for it. */
export const SUPPLIER_BALANCE_TIMEOUT_MS = 15_000;

const businessDate = /^\d{4}-\d{2}-\d{2}$/;

/** The bill's posting date, which decides its period; today while that is not (yet) a date. */
export const balanceDate = (posting: string, today: string): string => (businessDate.test(posting) ? posting : today);

export function balanceSide(net: D.Fixed): ReadySupplierBalance['side'] {
  return net < 0n ? 'CR' : net > 0n ? 'DR' : 'NIL';
}

/**
 * The supplier's net balance across the payable accounts it was verified with, as of one date, in the
 * company's base currency. One read per account (a supplier almost always has one), each checked
 * before it is added: a figure that cannot be proved is refused, never guessed, so the page shows
 * "unavailable" rather than a wrong number.
 */
export async function readSupplierBalance(read: Reader, input: { base: string; supplier: string; payables: readonly string[]; asOf: string; currency: string; signal: AbortSignal }): Promise<ReadySupplierBalance> {
  const { base, supplier, payables, asOf, currency, signal } = input;
  if (!payables.length || !businessDate.test(asOf)) throw Error('The supplier balance could not be requested.');
  const rows = await Promise.all(payables.map(account => read<LedgerBalance>({
    service: 'accounting', signal,
    path: base + '/ledger/balance?' + new URLSearchParams({ as_of: asOf, basis: 'BASE', currency, party_id: supplier, account_id: account }),
  })));
  let net = D.ZERO;
  for (const row of rows) {
    const debit = typeof row?.debit === 'string' ? D.parse(row.debit) : null, credit = typeof row?.credit === 'string' ? D.parse(row.credit) : null, balance = typeof row?.balance === 'string' ? D.parse(row.balance) : null;
    if (row?.as_of !== asOf || row?.currency !== currency || debit === null || credit === null || balance === null || debit - credit !== balance) throw Error('The supplier balance could not be verified.');
    net += balance;
  }
  return { supplier, status: 'ready', side: balanceSide(net), amount: D.format(net < 0n ? -net : net), asOf, currency };
}
