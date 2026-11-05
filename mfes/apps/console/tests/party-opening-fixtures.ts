import type { HeldBalance, HeldPage } from '../app/lib/party-opening';
import { ACCOUNT } from './financial-opening-fixtures';

const uuid = (n: number) => `01990000-0000-7000-8000-${String(n).padStart(12, '0')}`;

export const held = (n = 1, over: Partial<HeldBalance> = {}): HeldBalance => ({
  id: uuid(100 + n), row_version: 1, party_id: uuid(200 + n), role: 'SUPPLIER', account_id: ACCOUNT,
  source_key: 'pob-' + String(n).padStart(32, '0'), status: 'PENDING', side: 'CREDIT', currency: 'INR',
  amount: '100.2500', exchange_rate: '1.00000000', base_amount: '100.2500', document_kind: 'ON_ACCOUNT',
  document_reference: 'Opening balance', document_date: null, due_date: null, included: false, ...over,
});

/** A dated invoice owed by a customer. */
export const heldInvoice = (n = 2, over: Partial<HeldBalance> = {}): HeldBalance =>
  held(n, {
    role: 'CUSTOMER', side: 'DEBIT', amount: '900.0000', base_amount: '900.0000', document_kind: 'INVOICE',
    document_reference: 'INV-77', document_date: '2026-02-10', due_date: '2026-03-12', ...over,
  });

export const heldPage = (items: HeldBalance[], has_more = false): HeldPage => ({
  items, page: { has_more, next_cursor: has_more ? 'next' : null },
});
