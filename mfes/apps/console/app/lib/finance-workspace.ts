import type {BookDefinition} from './book-workspace';

export const financeWorkspaces = {
  INVOICE_SETTLEMENT_REGISTER: {
    "code": "INVOICE_SETTLEMENT_REGISTER",
    "title": "Invoice settlement register",
    "overline": "Settlement history",
    "lede": "Settlement history",
    "resultNoun": "report rows",
    "focus": "Settlement history",
    "empty": "No matching records for the applied filters.",
    "primaryFilters": [
      "date_to",
      "invoice_id"
    ],
    "note": "Settlement history retains allocation and reversal dates. Active status is evaluated at the report as-of date."
  },
  INVOICE_COMPONENT_REGISTER: {
    "code": "INVOICE_COMPONENT_REGISTER",
    "title": "Invoice component register",
    "overline": "Components and allocations",
    "lede": "Components and allocations",
    "resultNoun": "report rows",
    "focus": "Components and allocations",
    "empty": "No matching records for the applied filters.",
    "primaryFilters": [
      "date_from",
      "date_to",
      "invoice_id"
    ],
    "note": "Component and allocation rows have different grains. Their amounts must not be added together as an invoice total."
  },
  PURCHASE_REGISTER: {
    "code": "PURCHASE_REGISTER",
    "title": "Purchase register",
    "overline": "Supplier invoice register",
    "lede": "Supplier invoice register",
    "resultNoun": "report rows",
    "focus": "Supplier invoice register",
    "empty": "No matching records for the applied filters.",
    "primaryFilters": [
      "date_from",
      "date_to",
      "date_basis",
      "party_id"
    ],
    "note": "Supplier charges, tax and differences stay explicit. Original purchases and reductions retain their recorded direction."
  },
  SALES_REGISTER: {
    "code": "SALES_REGISTER",
    "title": "Sales register",
    "overline": "Invoice register",
    "lede": "Invoice register",
    "resultNoun": "report rows",
    "focus": "Invoice register",
    "empty": "No matching records for the applied filters.",
    "primaryFilters": [
      "date_from",
      "date_to",
      "date_basis",
      "party_id"
    ],
    "note": "Original invoices and reductions keep their recorded direction. Totals are separated by document currency."
  },
  BANK_RECONCILIATION_WORKLIST: {
    "code": "BANK_RECONCILIATION_WORKLIST",
    "title": "Unmatched bank transactions",
    "overline": "Unmatched worklist",
    "lede": "Unmatched worklist",
    "resultNoun": "report rows",
    "focus": "Unmatched worklist",
    "empty": "No matching records for the applied filters.",
    "primaryFilters": [
      "date_from",
      "date_to",
      "account_id",
      "currency"
    ],
    "note": "Bank and book rows remain distinct. Review residual amounts and age; this report does not match or post transactions."
  },
  BANK_RECONCILIATION_EVIDENCE: {
    "code": "BANK_RECONCILIATION_EVIDENCE",
    "title": "Finalised bank reconciliation",
    "overline": "Session evidence",
    "lede": "Session evidence",
    "resultNoun": "report rows",
    "focus": "Session evidence",
    "empty": "No matching records for the applied filters.",
    "primaryFilters": [
      "date_from",
      "date_to",
      "account_id",
      "currency",
      "session_id"
    ],
    "note": "Evidence is frozen at the selected finalised session. Matched and outstanding amounts describe that session, not later bank activity."
  },
  BANK_RECONCILIATION: {
    "code": "BANK_RECONCILIATION",
    "title": "Bank balance agreement",
    "overline": "Balance agreement",
    "lede": "Balance agreement",
    "resultNoun": "report rows",
    "focus": "Balance agreement",
    "empty": "No matching records for the applied filters.",
    "primaryFilters": [
      "date_to",
      "account_id",
      "statement_balance"
    ],
    "note": "A balance agreement is a diagnostic. A zero difference does not certify statement coverage or finalise reconciliation."
  },
  RECEIPT_REGISTER: {
    "code": "RECEIPT_REGISTER",
    "title": "Receipt register",
    "overline": "Receipt detail",
    "lede": "Receipt detail",
    "resultNoun": "report rows",
    "focus": "Receipt detail",
    "empty": "No matching records for the applied filters.",
    "primaryFilters": [
      "date_from",
      "date_to",
      "account_id",
      "party_id"
    ],
    "note": "Each row is a receipt tender allocation. Signed amounts preserve reversals; do not count each tender as a separate voucher."
  },
  PAYMENT_REGISTER: {
    "code": "PAYMENT_REGISTER",
    "title": "Payment register",
    "overline": "Payment detail",
    "lede": "Payment detail",
    "resultNoun": "report rows",
    "focus": "Payment detail",
    "empty": "No matching records for the applied filters.",
    "primaryFilters": [
      "date_from",
      "date_to",
      "account_id",
      "party_id"
    ],
    "note": "Each row is a tender allocation. Signed amounts include reversals; a voucher can have several tender rows."
  },
  AGING: {
    "code": "AGING",
    "title": "Receivables and payables ageing",
    "overline": "Ageing matrix",
    "lede": "Ageing matrix",
    "resultNoun": "report rows",
    "focus": "Ageing matrix",
    "empty": "No matching records for the applied filters.",
    "primaryFilters": [
      "date_to",
      "party_id",
      "role"
    ],
    "note": "Age is based on the original due date. Unapplied credits stay separate from debt; unknown due dates have their own bucket."
  },
  ADVANCES: {
    "code": "ADVANCES",
    "title": "Advances",
    "overline": "Unapplied credits",
    "lede": "Unapplied credits",
    "resultNoun": "report rows",
    "focus": "Unapplied credits",
    "empty": "No matching records for the applied filters.",
    "primaryFilters": [
      "date_to",
      "party_id",
      "role"
    ],
    "note": "Unapplied customer and supplier credits are not income. Remaining credits may be allocated against eligible bills."
  },
  OUTSTANDING_BILLS: {
    "code": "OUTSTANDING_BILLS",
    "title": "Outstanding bills",
    "overline": "Bill detail",
    "lede": "Bill detail",
    "resultNoun": "report rows",
    "focus": "Bill detail",
    "empty": "No matching records for the applied filters.",
    "primaryFilters": [
      "date_to",
      "party_id",
      "role"
    ],
    "note": "Outstanding debt and unapplied credits remain separate. Document amounts use their own currency; report amount uses the selected basis."
  },
  ACCOUNT_SUMMARY: {
    "code": "ACCOUNT_SUMMARY",
    "title": "Account summary",
    "overline": "Period movement",
    "lede": "Period movement",
    "resultNoun": "report rows",
    "focus": "Period movement",
    "empty": "No matching records for the applied filters.",
    "primaryFilters": [
      "date_from",
      "date_to",
      "grain",
      "account_id",
      "group_id"
    ],
    "note": "Daily or monthly opening, movement and closing balances. Group totals include descendants; do not add them again to account detail."
  },
  BANK_BOOK: {
    "code": "BANK_BOOK",
    "title": "Bank book",
    "overline": "Bank transactions",
    "lede": "Bank transactions",
    "resultNoun": "report rows",
    "focus": "Bank transactions",
    "empty": "No matching records for the applied filters.",
    "primaryFilters": [
      "date_from",
      "date_to",
      "account_id"
    ],
    "note": "These are posted book balances, not bank statement balances or evidence of reconciliation."
  },
  CASH_BOOK: {
    "code": "CASH_BOOK",
    "title": "Cash book",
    "overline": "Cash transactions",
    "lede": "Cash transactions",
    "resultNoun": "report rows",
    "focus": "Cash transactions",
    "empty": "No matching records for the applied filters.",
    "primaryFilters": [
      "date_from",
      "date_to",
      "account_id"
    ],
    "note": "Debits are cash receipts and credits are payments. Running balances are per cash account."
  },
  PARTY_LEDGER: {
    "code": "PARTY_LEDGER",
    "title": "Party ledger",
    "overline": "Transactions",
    "lede": "Transactions",
    "resultNoun": "report rows",
    "focus": "Transactions",
    "empty": "No matching records for the applied filters.",
    "primaryFilters": [
      "date_from",
      "date_to",
      "party_id",
      "role"
    ],
    "note": "Customer and supplier roles are separate. Use row actions for journal and bill details."
  },
  DAY_BOOK: {
    "code": "DAY_BOOK",
    "title": "Day book",
    "overline": "Posted journal entries",
    "lede": "Posted journal entries",
    "resultNoun": "report rows",
    "focus": "Posted journal entries",
    "empty": "No matching records for the applied filters.",
    "primaryFilters": [
      "date_from",
      "date_to"
    ],
    "note": "Posted accounting entries only. Each journal can contain several account lines; debit and credit are not voucher totals."
  },
  ACCOUNT_LEDGER: {
    "code": "ACCOUNT_LEDGER",
    "title": "Account ledger",
    "overline": "Transactions",
    "lede": "Transactions",
    "resultNoun": "report rows",
    "focus": "Transactions",
    "empty": "No matching records for the applied filters.",
    "primaryFilters": [
      "date_from",
      "date_to",
      "account_id"
    ],
    "note": "Opening and running balances follow posted entries for each account. Debit and credit remain separate."
  },
  INCOME_EXPENSE: {
    code:'INCOME_EXPENSE', title:'Income and expenditure', overline:'Financial performance',
    lede:'Income, expenditure and the net surplus or deficit from verified accounting records.',
    resultNoun:'statement rows', focus:'Account detail and whole-report totals; imported YTD is disclosed separately.',
    empty:'No income or expenditure matches these dates.', primaryFilters:['date_from','date_to'],
    note:'Surplus or deficit is income less expenditure. When eligible imported year-to-date amounts are present, they are already included in account balances.',
  },
} satisfies Record<string, BookDefinition & {note:string}>;
export type FinanceReportCode = keyof typeof financeWorkspaces;
export const isFinanceReport = (code?:string):code is FinanceReportCode => !!code && Object.hasOwn(financeWorkspaces,code);
export const financeLabels:Record<string,string> = {date_to:'As of',show_zero:'Include zero accounts',statement_balance:'Statement closing balance',session_id:'Finalised reconciliation session reference',grain:'Summarise by',row_kind:'Line type',account_name:'Account',group_name:'Account group',NET_SURPLUS_DEFICIT:'Net surplus / deficit',TOTAL_INCOME:'Total income',TOTAL_EXPENSE:'Total expenditure'};
export function financeValue(value:string){return financeLabels[value] ?? value.toLowerCase().replaceAll('_',' ').replace(/^./,first=>first.toUpperCase());}
