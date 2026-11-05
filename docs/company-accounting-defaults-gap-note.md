# Company accounting defaults: gaps and candidates

Recorded 2026-11-03 at the user's request. The baseline below describes the state
before implementation. The user subsequently approved Discount Allowed/Received
and the First/High-priority categories; see the
[delivery and review record](company-accounting-defaults-delivery.md).
Next/Medium and conditional candidates remain deferred.

## Verified baseline

Sources: `apis/accounting/src/accounting/seeds/templates.py`,
`tasks/templates.py`, `tasks/stock_policy.py`, `models/masters.py`, and Identity's
`tasks/company_setup.py`.

- A fresh chart gets 28 groups (15 primary, 13 subordinate), five heads and 12 accounts.
- Cash-in-hand is a group under Current Assets; Cash is an account within it.
- Inventory setup adds five accounts, bringing the default total to 17.
- Sales Returns, Office Rent, Utilities Expense, Salaries Expense, Bank Charges,
  Round-off Gain/Loss and Accumulated Profit/Loss already exist as default accounts.
- Duties and Taxes exists as a default group. Tax Recoverables is currently added
  only through the registration-specific GST template.
- The GST template adds six tax accounts per registration: input/output CGST,
  SGST or UTGST, and IGST. Fresh-company initialization does not invoke this template.
- VAT master profiles exist; automatic VAT account provisioning does not. Master
  profile support is not evidence of an operational VAT posting/reporting workflow.
- Cess, reverse charge, pending input credit and TDS/TCS have accounting metadata
  and mapping support, but are not included in the automatic starter accounts.
- Discount calculations exist; Discount Allowed/Received are not starter accounts.

## Candidate additions, ordered by practical priority

| Priority | Accounts to consider | Applicability and implementation boundary |
|---|---|---|
| First | Applicable GST/VAT input, output and settlement/control accounts | Select from dated registrations, jurisdiction and supported tax workflows; do not activate every tax for every company. |
| First | Discount Allowed and Discount Received | Define trade, settlement and rebate treatment first; separate ledgers must not duplicate reductions already included in revenue or inventory cost. |
| First | Cost of Goods Sold | Inventory companies; COST_OF_GOODS mapping exists but its account is absent from starter seeds. Confirm the valuation/posting contract before mapping. |
| First | Purchase Returns / purchase adjustments | Optional separate tracking under purchase/cost classification; preserve source-linked returns and avoid duplicating inventory reversals. |
| First | Freight Inward, Freight Outward and delivery expense | Inward acquisition costs may belong in inventory value; outward delivery costs need separate treatment. Use existing landed-cost rules. |
| First | Payment Gateway/POS Clearing and Merchant Fees | Create for enabled collection channels with reconciliation and actual settlement mappings. Bank Charges already exists; a separate fees ledger is optional. |
| Next | Bad Debts and Allowance for Doubtful Debts | Separate write-offs from allowance/contra-receivable accounting; add only with the appropriate adjustment workflow. |
| Next | Prepaid Expenses and Accrued Expenses | Useful asset/liability accounts for period adjustments; existing Current Assets/Liabilities groups can hold them. |
| Next | Interest Expense and Interest Income | For businesses using borrowing, deposits or other interest-bearing balances. |
| Next | Depreciation Expense and Accumulated Depreciation | For fixed assets; accumulated depreciation is a contra asset, not a new liability. Asset-class detail is optional. |
| Next | Repairs and Maintenance, Insurance, Professional Fees, Office Supplies and Travel | Optional expense pack; reuse Indirect Expenses and avoid an unnecessarily large starter chart. |
| Conditional | Realized and Unrealized Exchange Gain/Loss | Only for enabled foreign-currency workflows with settlement/revaluation support. |
| Conditional | Owner/Partner Capital and Drawings | Depend on legal entity type; do not create proprietor drawings for every company. |
| Conditional | Customer Advances and Supplier Advances | Consider only if needed by the balance-sheet presentation contract; existing party-ledger advance tracking must not be duplicated. |
| Conditional | Inventory Write-down, Damage/Spoilage and recovery accounts | Use only where separate reporting is required; Stock Variance already exists. |

## Groups and provisioning rules

Most candidates fit the existing 28 groups. Consider Tax Recoverables when tax
recovery applies, and optional Prepayments, Accrued Liabilities, Payment Clearing,
Finance Costs and contra-asset subgroups where the reporting hierarchy needs them.
These are optional reporting refinements, not all missing primary groups.

Bank Accounts, Sundry Debtors/Creditors, Capital, Fixed Assets, Loans and Advances,
Deposits and Provisions already exist. Create actual bank, customer, supplier and
owner-specific ledgers from their respective setup flows; do not invent parties,
bank details or opening balances as company defaults.

Provisioning should be idempotent by stable system key, company-scoped, audited,
and feature/registration/entity-aware. Preserve custom charts and resolve code
conflicts explicitly. Account creation must include applicable profiles and dated
posting mappings. Creating a ledger alone does not make a workflow operational.
Existing-company adoption needs a preview and explicit scope; never rewrite posted
transactions or duplicate existing accounts. Payroll remains outside project scope.

## Accounting treatment references

These references inform design distinctions, not a claim that one framework applies
to every company. Final treatment depends on the company's accounting framework.

- [IAS 2, paragraph 11](https://www.ifrs.org/content/dam/ifrs/publications/pdf-standards/english/2021/issued/part-a/ias-2-inventories.pdf):
  acquisition costs and trade discounts affect inventory cost; separate discount
  income/expense ledgers must not double-count those amounts.
- [IFRS 15, paragraph 51](https://www.ifrs.org/content/dam/ifrs/publications/pdf-standards/english/2024/issued/part-a/ifrs-15-revenue-from-contracts-with-customers.pdf):
  discounts and rebates can affect the transaction price, so account selection
  must follow the defined recognition and calculation policy.

Decision log, 2026-11-03: initially saved for discussion; subsequently authorized
the First/High-priority defaults and appropriate missing groups. The delivery
record defines their applicability and verification; this does not authorize the
remaining candidates or new tax/payment execution engines.
