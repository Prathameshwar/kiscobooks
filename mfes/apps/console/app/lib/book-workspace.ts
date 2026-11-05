import type { BookKey } from './book-cards';

export type NativeBookKey = Exclude<BookKey, 'day-book'>;
export type ReportBookKey = NativeBookKey | 'stock-summary' | 'tax-report';

export type BookDefinition = {
  code: string;
  title: string;
  overline: string;
  lede: string;
  resultNoun: string;
  focus: string;
  empty: string;
  primaryFilters: readonly string[];
};

export const nativeBooks: Record<NativeBookKey, BookDefinition> = {
  'cash-book': {
    code: 'CASH_BOOK', title: 'Cash Book', overline: 'Cash position', resultNoun: 'cash entries',
    lede: 'Cash receipts, payments and running balances from verified postings.',
    focus: 'Opening, movement and running cash balance', empty: 'No cash movement was posted for this selection.',
    primaryFilters: ['date_from', 'date_to', 'account_id'],
  },
  'bank-book': {
    code: 'BANK_BOOK', title: 'Bank Book', overline: 'Bank position', resultNoun: 'bank entries',
    lede: 'Bank receipts, payments and running balances across your bank ledgers.',
    focus: 'Bank movement and running book balance', empty: 'No bank movement was posted for this selection.',
    primaryFilters: ['date_from', 'date_to', 'account_id'],
  },
  'sales-book': {
    code: 'SALES_REGISTER', title: 'Sales Book', overline: 'Sales register', resultNoun: 'sales invoices',
    lede: 'Customer invoices, tax, adjustments and payable totals in one register.',
    focus: 'Commercial, tax and invoice totals', empty: 'No sales invoices match this selection.',
    primaryFilters: ['date_from', 'date_to', 'date_basis', 'party_id'],
  },
  'purchase-book': {
    code: 'PURCHASE_REGISTER', title: 'Purchase Book', overline: 'Purchase register', resultNoun: 'purchase invoices',
    lede: 'Supplier invoices, charged tax, differences and payable totals.',
    focus: 'Supplier, tax and payable detail', empty: 'No purchase invoices match this selection.',
    primaryFilters: ['date_from', 'date_to', 'date_basis', 'party_id'],
  },
  'payment-book': {
    code: 'PAYMENT_REGISTER', title: 'Payment Book', overline: 'Payment register', resultNoun: 'payments',
    lede: 'Posted payments with tender modes, instruments and references.',
    focus: 'Payment mode and instrument traceability', empty: 'No posted payments match this selection.',
    primaryFilters: ['date_from', 'date_to', 'account_id', 'party_id'],
  },
  'receipt-book': {
    code: 'RECEIPT_REGISTER', title: 'Receipt Book', overline: 'Receipt register', resultNoun: 'receipts',
    lede: 'Posted receipts with tender modes, instruments and references.',
    focus: 'Receipt mode and instrument traceability', empty: 'No posted receipts match this selection.',
    primaryFilters: ['date_from', 'date_to', 'account_id', 'party_id'],
  },
  'account-ledger': {
    code: 'ACCOUNT_LEDGER', title: 'Account Ledger', overline: 'General ledger', resultNoun: 'ledger entries',
    lede: 'Posted account movements with debit, credit and running balance.',
    focus: 'Account movement and running balance', empty: 'No account entries match this selection.',
    primaryFilters: ['date_from', 'date_to', 'account_id'],
  },
  'party-ledger': {
    code: 'PARTY_LEDGER', title: 'Party Ledger', overline: 'Customer and supplier ledger', resultNoun: 'party entries',
    lede: 'Customer and supplier movements with running balances and bill drill-down.',
    focus: 'Party movement, balance and outstanding context', empty: 'No party entries match this selection.',
    primaryFilters: ['date_from', 'date_to', 'party_id', 'role'],
  },
  'stock-ledger': {
    code: 'ITEM_LEDGER', title: 'Stock Ledger', overline: 'Inventory movement', resultNoun: 'stock movements',
    lede: 'Item movements with inward, outward, quantity and value balances.',
    focus: 'Quantity, value, warehouse and batch movement', empty: 'No stock movement matches this selection.',
    primaryFilters: ['date_from', 'as_of', 'item_id'],
  },
};

export const bookPreferencesKey = (actor: string, company: string, book: ReportBookKey) =>
  `kiscobooks:native-book:v1:${actor}:${company}:${book}`;

export const stockSummary: BookDefinition = {
  code: 'STOCK_SUMMARY', title: 'Stock Summary', overline: 'Inventory position',
  lede: 'Opening stock, stock movements and closing balances from a verified inventory snapshot.',
  resultNoun: 'stock rows', focus: 'Search the full result by item code or name',
  empty: 'No stock items match the applied filters.', primaryFilters: ['as_of', 'location_id', 'group_id', 'search'],
};

export function isNativeBook(value: BookKey): value is NativeBookKey {
  return value !== 'day-book';
}

const commonLabels: Record<string, string> = {
  date_from: 'From date', date_to: 'To date', as_of: 'To date', comparative_from: 'Compare from', comparative_to: 'Compare to',
  basis: 'Currency basis', currency: 'Currency code', role: 'Party role', date_basis: 'Date basis',
  journal_id: 'Journal reference', invoice_id: 'Invoice reference', owner: 'Stock ownership', include_inactive: 'Include inactive items',
  location_id: 'Warehouse', lot_id: 'Batch or lot', item_id: 'Item', group_id: 'Ledger group', party_id: 'Party', account_id: 'Ledger account',
};

const contextualLabels: Partial<Record<NativeBookKey, Record<string, string>>> = {
  'cash-book': { account_id: 'Cash account', group_id: 'Cash ledger group' },
  'bank-book': { account_id: 'Bank account', group_id: 'Bank ledger group' },
  'sales-book': { account_id: 'Customer ledger account', group_id: 'Sales ledger group', party_id: 'Customer', invoice_id: 'Sales invoice reference' },
  'purchase-book': { account_id: 'Supplier ledger account', group_id: 'Purchase ledger group', party_id: 'Supplier', invoice_id: 'Purchase invoice reference' },
  'payment-book': { account_id: 'Paying cash or bank account', group_id: 'Payment ledger group', party_id: 'Paid party' },
  'receipt-book': { account_id: 'Receiving cash or bank account', group_id: 'Receipt ledger group', party_id: 'Received from party' },
  'account-ledger': { account_id: 'Ledger account', group_id: 'Ledger group' },
  'party-ledger': { account_id: 'Party ledger account', group_id: 'Party ledger group', party_id: 'Customer or supplier' },
  'stock-ledger': { item_id: 'Stock item', group_id: 'Item group', location_id: 'Warehouse or location', lot_id: 'Batch or lot' },
};

/** Product language for discovered schema fields; UUID/storage terminology stays internal. */
export function bookParameterLabel(book: ReportBookKey, key: string, fallback?: string): string {
  if (book === 'tax-report') return commonLabels[key] ?? fallback ?? key.replaceAll('_',' ');
  if (book === 'stock-summary') return ({ as_of: 'As of', item_id: 'Stock item', group_id: 'Item group', search: 'Search items', location_id: 'Warehouse', include_zero: 'Include zero stock', sort: 'Sort by', descending: 'Descending order', custody: 'Stock custody' } as Record<string, string>)[key] ?? commonLabels[key] ?? fallback ?? key.replaceAll('_', ' ');
  return contextualLabels[book]?.[key] ?? commonLabels[key] ?? fallback?.replace(/\bId\b/g, 'reference') ?? key.replaceAll('_', ' ');
}

/** Identifier values in retained rows are audit references, not user-facing master names. */
export function bookColumnLabel(key: string, fallback: string): string {
  const labels: Record<string, string> = {
    account_id: 'Account reference', group_id: 'Group reference', party_id: 'Party reference', item_id: 'Item reference',
    location_id: 'Location reference', lot_id: 'Batch reference', instrument_id: 'Instrument reference', invoice_id: 'Invoice reference',
    journal_id: 'Journal reference', line_id: 'Entry reference', position_id: 'Stock position reference', source_id: 'Source reference',
  };
  return labels[key] ?? fallback.replace(/\bId\b/g, 'reference');
}
