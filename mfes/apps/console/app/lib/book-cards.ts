import { reportSections, type ReportSection } from './report-cards';
const definitions = [
  {
    key: 'day-book',
    title: 'Day book',
    code: 'DAY_BOOK',
    group: 'Daily and cash books',
  },
  {
    key: 'cash-book',
    title: 'Cash book',
    code: 'CASH_BOOK',
    group: 'Daily and cash books',
  },
  {
    key: 'bank-book',
    title: 'Bank book',
    code: 'BANK_BOOK',
    group: 'Daily and cash books',
  },
  {
    key: 'sales-book',
    title: 'Sales book',
    code: 'SALES_REGISTER',
    group: 'Transaction registers',
  },
  {
    key: 'purchase-book',
    title: 'Purchase book',
    code: 'PURCHASE_REGISTER',
    group: 'Transaction registers',
  },
  {
    key: 'payment-book',
    title: 'Payment book',
    code: 'PAYMENT_REGISTER',
    group: 'Transaction registers',
  },
  {
    key: 'receipt-book',
    title: 'Receipt book',
    code: 'RECEIPT_REGISTER',
    group: 'Transaction registers',
  },
  {
    key: 'account-ledger',
    title: 'Account ledger',
    code: 'ACCOUNT_LEDGER',
    group: 'Ledgers',
  },
  {
    key: 'party-ledger',
    title: 'Party ledger',
    code: 'PARTY_LEDGER',
    group: 'Ledgers',
  },
  {
    key: 'stock-ledger',
    title: 'Stock ledger',
    code: 'ITEM_LEDGER',
    group: 'Ledgers',
  },
] as const;
export type BookKey = (typeof definitions)[number]['key'];
const reports = reportSections.flatMap((section) => section.reports);
/** Book navigation reuses native definitions; no speculative execution endpoint. */
export const bookEntries = definitions.map((book) => {
  const report = reports.find((report) => report.code === book.code);
  if (!report)
    throw new Error('Book catalogue must reference an existing native report');
  return { ...book, description: report.description };
});
export const isBookKey = (value: string): value is BookKey =>
  bookEntries.some((book) => book.key === value);
export function bookSections(book?: BookKey): ReportSection[] {
  return ['Daily and cash books', 'Transaction registers', 'Ledgers']
    .map((title) => ({
      title,
      description:
        title === 'Daily and cash books'
          ? 'Posted entries and cash or bank movements.'
          : title === 'Transaction registers'
            ? 'Sales, purchases, payments and receipts.'
            : 'Account, party and stock movement history.',
      reports: bookEntries
        .filter(
          (entry) => entry.group === title && (!book || entry.key === book),
        )
        .map((entry) => ({
          code: entry.code,
          title: entry.title,
          description: entry.description,
        })),
    }))
    .filter((section) => section.reports.length);
}
