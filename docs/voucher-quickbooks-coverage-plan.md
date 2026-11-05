# QuickBooks-informed voucher coverage review and first backend slice

**Date:** 2026-10-11. **Status:** Focused Sales workflow configuration slice implemented; UI, new posting recipes and activation remain separate.

## What the review found

The shared voucher/type/class policy already covers Tally-style entry modes,
numbering, invoices, tenders and non-posting quotations/orders. QuickBooks Online
adds useful workflow patterns: billable expenses linked to customer invoices,
estimate-based progress invoicing, scheduled/reminder/unscheduled recurring
transactions, and class/location reporting. Its [billable expense guide](https://quickbooks.intuit.com/learn-support/en-us/help-article/manage-customers/enter-billable-expenses/L37dCZU5O_US_en_US),
[progress invoicing guide](https://quickbooks.intuit.com/learn-support/en-us/help-article/invoicing/set-send-progress-invoices-quickbooks-online/L0Ymm6WjR_US_en_US),
[recurring transaction guide](https://quickbooks.intuit.com/learn-support/en-us/help-article/recurring-transactions/create-recurring-transactions-quickbooks-online/L3WoKX2R8_US_en_US),
and [class tracking guide](https://quickbooks.intuit.com/learn-support/en-us/help-article/class-list/get-started-class-tracking-quickbooks-online/L04INPWiy_US_en_US)
are feature references, not claims of product parity.

| Candidate | Current gap and safe owner boundary | Decision |
|---|---|---|
| Sales order evidence and due-date terms | Sales invoices capture an order reference and due date, but configuration cannot require/bound them. Vouchers can enforce these existing fields without changing a posting recipe. | Implement now as sparse schema-v2 Sales workflow controls, enforced at issue/preview as well as entry. |
| Billable expense to Sales invoice | A durable source expense line, customer assignment, remaining billable amount, margin/tax choice and atomic claim are needed. A custom field or loose reference cannot authorize reimbursement. | Plan under future Vouchers/Accounting source-allocation gate. |
| Progress invoice from quote/order | Need immutable source line/quantity/value allocations, concurrency caps, return reversal and tax/date handling. Current generic links are insufficient. | Plan with B28-B33 fulfillment and B25 returns gates. |
| Recurring template | Need versioned template, schedule/timezone, bounded occurrence key, draft-only idempotent generation, review and fiscal/config revalidation. Provider auto-charge is separate. | Keep optional and disabled pending explicit scheduler/owner slice. |
| Segment reporting | Current voucher `class_id` selects a voucher policy; it is not a QuickBooks reporting class. A real segment dimension needs Accounting journal-line facts and report projection. | Design separately; never reinterpret policy class as a reporting dimension. |

## Implementation phases

1. Add `sales_workflow` to policy schema v2 only. Preserve v1 serialization and
   hashes; merge common/type/class controls restrictively; discard the control
   for unrelated kinds. Reject unusable Sales policies at publication.
2. Apply the effective setting to Sales invoice content: require a
   `CUSTOMER_ORDER` reference when selected, and require the invoice due date
   to be within the configured nonnegative day window from document date.
   Drafts may remain incomplete; issue and execution recheck the same validation.
3. Add domain/API regression evidence, regenerate Vouchers OpenAPI and the
   TypeScript client, run affected tests, strict typing and lint, then review
   policy applicability, company isolation and compatibility. No Accounting
   model, new effect or release activation is introduced by this slice.

## Implemented boundary and remaining work

`sales_workflow` is a schema-v2 policy child for standard Sales. Its optional
`max_due_days` is compared with the invoice document date; a configured limit
rejects past-due dates and dates beyond the bound. When
`customer_order_reference_required` is true, issue/execution requires a
nonblank `CUSTOMER_ORDER` reference. This is external evidence only, not a
verified link or source allocation against a Sales Order. Sparse company,
type and class policies inherit and narrow the rule; unrelated kinds discard
a common rule. V1 policy wires and digests remain unchanged.

The next safe implementation slice is a source-allocation owner for progress
invoices and billable expenses: source revision, line, customer, exact remaining
quantity/value, claim identity, return reversal and concurrent cap. Only after
that should configuration expose source-linked invoicing or reimbursement.
Recurring templates and reporting segments remain distinct opt-in workstreams.

Verification: final affected Vouchers tests 78 passed; full Vouchers run 200
passed, 2 skipped. Ruff and strict mypy passed. Vouchers OpenAPI and generated
TypeScript client checks, client transport tests (8 passed) and TypeScript
typecheck passed. Review found and closed the whitespace-only customer order
reference bypass. No native Accounting or statutory Sales activation evidence
was produced by this configuration-only change.

## Decision log

- 2026-10-11: Selected a native Sales terms/reference control because it can
  be enforced on already captured fields. Deferred billable allocation,
  progress invoicing, recurrence and reporting segments until their durable
  owner facts and concurrency/replay gates are designed and verified.
- 2026-10-11: Implemented the bounded schema-v2 Sales workflow setting in
  existing policy storage and issue/execution validation. The order number is
  nonblank evidence, not proof of a fulfilled or billable source. No new
  Accounting effect, batch verification or company activation is claimed.
