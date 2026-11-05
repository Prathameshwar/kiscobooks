'use client';
import type { components } from '@janso/api-client/accounting';
import { base, type Document, type Entry } from './financial-opening';
import { sum } from './opening-stock';
import { trackingId } from './stock-tracking-resources';

export type HeldBalance = components['schemas']['PartyOpeningItem'];
export type HeldPage = { items: HeldBalance[]; page: { has_more: boolean; next_cursor: string | null } };

export const heldPath = (company: string) => base(company) + '/party-balances';
/** Everything the opening worksheet can still take: pending and not yet in its declaration. */
export const pendingQuery = (company: string) => heldPath(company) + '?status=PENDING&limit=200';

const source = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$/;
const amount = /^(?:0|[1-9]\d{0,14})(?:\.\d{1,4})?$/;
const rate = /^(?:0|[1-9]\d{0,10})(?:\.\d{1,8})?$/;
const positive = (value: string) => /[1-9]/.test(value);

/** The proxy answers for any session, so check the shape before any amount reaches a worksheet. */
export function verifyHeld(page: HeldPage): void {
  const bad = { status: 502, message: 'The held party balances could not be verified. Reload and try again.' };
  if (!page || !Array.isArray(page.items) || page.items.length > 200 || !page.page) throw bad;
  for (const item of page.items) {
    if (
      !trackingId.test(item.id) || !trackingId.test(item.party_id) || !trackingId.test(item.account_id) ||
      !source.test(item.source_key) || !['DEBIT', 'CREDIT'].includes(item.side) ||
      !['CUSTOMER', 'SUPPLIER'].includes(item.role) || !['PENDING', 'WITHDRAWN'].includes(item.status) ||
      !/^[A-Z]{3}$/.test(item.currency) || ![item.amount, item.base_amount].every(value => amount.test(value) && positive(value)) ||
      !rate.test(item.exchange_rate) || !positive(item.exchange_rate) ||
      !Number.isSafeInteger(item.row_version) || item.row_version < 1 || typeof item.included !== 'boolean' ||
      !item.document_reference ||
      (item.document_kind === 'ON_ACCOUNT' ? !!item.document_date || !!item.due_date : !item.document_date || !item.due_date)
    ) throw bad;
  }
}

/** Held lines the worksheet does not yet carry, by source key. */
export function addable(items: HeldBalance[], rows: Entry[]): HeldBalance[] {
  const present = new Set(rows.map(row => row.source_key.toLowerCase()));
  return items.filter(item => item.status === 'PENDING' && !item.included && !present.has(item.source_key.toLowerCase()));
}

/** Exactly what the import was given: one entry with its one document, base value explicit. */
export function heldEntry(item: HeldBalance): Entry {
  const document: Document = item.document_kind === 'ON_ACCOUNT'
    ? { line_sequence: 1, document_kind: 'ON_ACCOUNT', reference: item.document_reference, amount: item.amount, base_amount: item.base_amount }
    : {
        line_sequence: 1, reference: item.document_reference, amount: item.amount, base_amount: item.base_amount,
        document_kind: item.document_kind as 'INVOICE' | 'BILL' | null, document_date: item.document_date!, due_date: item.due_date!,
      };
  return {
    source_key: item.source_key, account_id: item.account_id, side: item.side, currency: item.currency,
    amount: item.amount, exchange_rate: item.exchange_rate, base_amount: item.base_amount, documents: [document],
  };
}

/** Exact base-value totals; money is never summed as a float. */
export function heldTotals(items: HeldBalance[]): { debit: string; credit: string } {
  const total = (side: string) => sum(items.filter(item => item.side === side).map(item => item.base_amount));
  return { debit: total('DEBIT'), credit: total('CREDIT') };
}

/** A spoken name for one row's withdraw button: what it is, how much, and which one in the list. */
export function withdrawLabel(item: HeldBalance, ordinal: number): string {
  return `Withdraw held ${item.role === 'SUPPLIER' ? 'supplier' : 'customer'} balance ${ordinal}: ${item.amount} ${item.currency}`;
}
