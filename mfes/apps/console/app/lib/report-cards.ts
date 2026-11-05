export type ReportCard = { code: string; title: string; description: string };
export type ReportSection = { title: string; description: string; reports: ReportCard[] };
const report = (code: string, title: string, description: string): ReportCard => ({ code, title, description });
/** Native report codes; company-scoped API discovery controls availability. */
export const reportSections: ReportSection[] = [
  { title: 'Financial statements', description: 'Company balances, performance and financial position.', reports: [
    report('TRIAL_BALANCE', 'Trial balance', 'Opening, period movement and closing debit/credit balances.'),
    report('PROFIT_LOSS', 'Profit and loss', 'Income, expenses, gross profit and net profit. P&L statement.'),
    report('BALANCE_SHEET', 'Balance sheet', 'Assets, liabilities, equity and accumulated earnings.'),
    report('INCOME_EXPENSE', 'Income and expenditure', 'Income, expenditure and the net surplus or deficit.'),
  ] },
  { title: 'Books and ledgers', description: 'Account entries, running balances and period summaries.', reports: [
    report('ACCOUNT_LEDGER', 'Account ledger', 'Posted ledger entries with opening and running balances.'),
    report('DAY_BOOK', 'Day book', 'Daily posted journals and voucher entries.'),
    report('PARTY_LEDGER', 'Party ledger', 'Customer and supplier account transaction details.'),
    report('CASH_BOOK', 'Cash book', 'Cash receipts, payments and running balances.'),
    report('BANK_BOOK', 'Bank book', 'Bank account entries and running balances.'),
    report('ACCOUNT_SUMMARY', 'Account summary', 'Daily or monthly account and group movement summaries.'),
  ] },
  { title: 'Receivables and payables', description: 'Outstanding bills, advances and ageing.', reports: [
    report('OUTSTANDING_BILLS', 'Outstanding bills', 'Bills receivable/payable, allocations and remaining balances.'),
    report('ADVANCES', 'Advances', 'Unapplied customer and supplier credits.'),
    report('AGING', 'Receivables and payables ageing', 'Outstanding debt and credits grouped by due-date age. Aging report.'),
  ] },
  { title: 'Banking and payments', description: 'Receipts, payments and bank reconciliation evidence.', reports: [
    report('PAYMENT_REGISTER', 'Payment register', 'Payment vouchers, tender modes and references.'),
    report('RECEIPT_REGISTER', 'Receipt register', 'Receipt vouchers, tender modes and references.'),
    report('BANK_RECONCILIATION', 'Bank balance agreement', 'Compare book and statement balances; manual bank reconciliation.'),
    report('BANK_RECONCILIATION_EVIDENCE', 'Finalised bank reconciliation', 'Finalised bank-session balances and matching evidence.'),
    report('BANK_RECONCILIATION_WORKLIST', 'Unmatched bank transactions', 'Bank and book transactions awaiting reconciliation.'),
  ] },
  { title: 'Sales and purchases', description: 'Invoice registers, components and settlement history.', reports: [
    report('SALES_REGISTER', 'Sales register', 'Sales invoices, parties, reductions and recorded totals.'),
    report('PURCHASE_REGISTER', 'Purchase register', 'Supplier invoices and purchase transaction details.'),
    report('INVOICE_COMPONENT_REGISTER', 'Invoice component register', 'Invoice item, charge and allocation details.'),
    report('INVOICE_SETTLEMENT_REGISTER', 'Invoice settlement register', 'Invoice payment allocations and reversals.'),
  ] },
  { title: 'Tax and credits', description: 'Recorded invoice tax details and credit positions.', reports: [
    report('GSTR3B', 'GSTR-3B', 'GSTIN and monthly/QRMP return preparation, ITC, reconciliation and payment workings.'),
    report('GSTR1', 'GSTR-1', 'Outward supplies by GSTIN and month/QRMP quarter, HSN, documents, amendments and reconciliation.'),
    report('INVOICE_TAX_REGISTER', 'Invoice tax register', 'Recorded taxable values, tax amounts and tax event dates.'),
    report('INVOICE_CREDIT_REGISTER', 'Input tax credit register', 'Tax credit positions, decisions and dated events.'),
  ] },
  { title: 'Inventory and warehouses', description: 'Stock quantities, movements, valuation and availability.', reports: [
    report('STOCK_SUMMARY', 'Stock summary', 'Opening, inward, outward, available stock and carrying values.'),
    report('ITEM_LEDGER', 'Item stock ledger', 'Item movement history and running quantity/value balances.'),
    report('LOCATION_STOCK', 'Warehouse stock', 'Stock by warehouse or location.'),
    report('STOCK_VALUATION', 'Stock valuation', 'Stock carrying values and valuation evidence.'),
    report('BATCH_SUMMARY', 'Batch summary', 'Batch balances, manufacturing and expiry dates, and optional serial history.'),
    report('STOCK_EXPIRY', 'Stock expiry', 'Expired, upcoming and missing-expiry stock exceptions.'),
    report('STOCK_REORDER', 'Stock reorder', 'Company and warehouse stock bands, quantity basis and constrained replenishment suggestions.'),
    report('STOCK_AGEING', 'Stock ageing', 'Remaining stock by original receipt or manufacture age. Inventory aging report.'),
    report('STOCK_MOVEMENT', 'Stock movement', 'Period receipts, sales, returns and transfers, with nonmoving stock analysis.'),
    report('STOCK_GROUP_SUMMARY', 'Stock group summary', 'Stock totals grouped by item classification.'),
  ] },
  { title: 'Business analytics', description: 'Understand sales, profit, customers, costs and working capital.', reports: [
    report('SALES_PERFORMANCE', 'Sales performance', 'Sales trends, customer contribution, products, discounts and returns.'),
    report('PROFIT_MARGIN_ANALYSIS', 'Profit and margin analysis', 'Profit drivers, direct costs, operating expenses and verified product gross margins.'),
    report('BUYER_PROFIT', 'Party (buyer) wise profit', 'Buyer gross profit, actual costs, margins and invoice breakdowns after returns.'),
    report('PRODUCT_PROFIT', 'Product wise profit', 'Product and group gross profit, actual costs and margins, including parent groups.'),
    report('CUSTOMER_INSIGHTS', 'Customer insights', 'Repeat purchasing, first observed purchases, customer value, inactivity and concentration.'),
    report('EXPENSE_PROFIT_LEAKAGE', 'Expense and profit leakage', 'Posted expense drivers, material spending changes and supplier purchase spending.'),
    report('CASH_WORKING_CAPITAL', 'Cash and working capital', 'Cash and bank balances, overdue customer bills, supplier dues and owned stock tied up.'),
  ] },
  { title: 'Controls and reconciliation', description: 'Source completeness, year continuity and ledger bridges.', reports: [
    report('BALANCE_CONTINUITY', 'Balance continuity', 'Reconcile opening balances with prior closing balances.'),
    report('SOURCE_RECONCILIATION', 'Source reconciliation', 'Source counts and ledger debit/credit control totals.'),
    report('INVOICE_GL_BRIDGE', 'Invoice to ledger reconciliation', 'Reconcile invoice effects to general ledger entries.'),
    report('TAX_GL_BRIDGE', 'Tax to ledger reconciliation', 'Reconcile recorded tax effects to general ledger entries.'),
  ] },
];

export const reportCategories = [
  { key: 'inventory', title: 'Inventory reports', description: 'Stock, warehouse, batch, movement and valuation reports.' },
  { key: 'finance', title: 'Finance reports', description: 'Statements, books, ledgers, receivables, payables and banking reports.' },
  { key: 'tax', title: 'Tax reports', description: 'Recorded tax, input credits and tax-to-ledger reconciliation.' },
  { key: 'analytics', title: 'Analytics', description: 'Sales, profit, customers, costs, cash and accounting controls.' },
] as const;
export type ReportCategory = (typeof reportCategories)[number]['key'];
export const isReportCategory = (value: string): value is ReportCategory => reportCategories.some(category => category.key === value);
export function reportCategory(section: ReportSection, report: ReportCard): ReportCategory {
  if (report.code === 'TAX_GL_BRIDGE' || section.title === 'Tax and credits') return 'tax';
  if (section.title === 'Inventory and warehouses') return 'inventory';
  if (section.title === 'Controls and reconciliation' || section.title === 'Business analytics') return 'analytics';
  return 'finance';
}
export function reportSectionsFor(category?: ReportCategory): ReportSection[] {
  if (!category) return reportSections;
  return reportSections.map(section => ({ ...section,
    ...(category === 'tax' && section.title === 'Controls and reconciliation'
      ? { title: 'Tax reconciliation', description: 'Compare recorded tax effects with their ledger entries.' } : {}),
    reports: section.reports.filter(report => reportCategory(section, report) === category),
  })).filter(section => section.reports.length > 0);
}
