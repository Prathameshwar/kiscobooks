# Posted Purchase correction delivery plan

Status 2026-11-06: guarded reversal, linked replacement posting, and Console actions are implemented and deployed. Focused automated tests pass. Live posted correction is not yet verified, and the Console Full edit preflight refuses broader Purchase captures it cannot reopen. Posted revisions and their prints remain immutable.

## Outcome

A user with correction authority opens a Posted Purchase and chooses **Full edit** or **Cancel posted Purchase**. Full edit opens a complete editable copy as a linked replacement draft; after a guarded reversal commits, the replacement follows calculation, approval and posting. Cancel reverses the posted effects without creating a replacement. The original bill, revision, number, print and effects remain in history. A correction carries a reason and exact source revision; neither action rewrites a posted revision or posts the original voucher ID twice.

## Phases

1. **Contract and review.** Define typed Full edit and Cancel posted commands, an exact source-revision link for the replacement draft, reason, idempotency key, expected version and company scope. Decide reversal eligibility and the linked debit/credit adjustment route for settled, filed, consumed-stock and closed-period cases. Publish API/client contracts and state/permission rules. Tests: same-company source, exact revision, duplicate correction, stale version, denied field and tenant access.
2. **Accounting correction effects.** Implement invoice reversal only with original-component, open-item, tax/statutory, allocation, bank, stock-origin and period guards. Preserve immutable original facts. For an ineligible full reversal, use a linked debit/credit note with bounded source allocation rather than rewriting posted totals. Tests: account/service, goods, GST and untaxed, settled and partial settlement, return/credit, consumed lots/serials, period close, retries and races.
3. **Vouchers orchestration.** Add guarded Purchase Full edit and Cancel posted commands and a source link. Full edit preserves all editable Purchase fields in a replacement draft. The replacement may post only after an eligible reversal commits and the original reconciles to REVERSED. Cancel posted stops after that reconciliation. An adjustment draft remains linked to the Posted original when full reversal is ineligible. Capture/submit/post use existing revision, approval, calculation and asynchronous execution checks. Tests: pending/rejected/committed operations, no second primary posting, audit/history and duplicate supplier bill rules.
4. **Console flow.** Replace the Posted Purchase read-only dead end with Full edit and Cancel posted actions for authorized users. Present the exact original revision, reason, effect status and eligible route in confirmation/review. Keep the source print and history accessible. Show pending and failed operations without suggesting a replacement was posted. Full edit uses the complete Purchase editor on the linked draft; the user reviews and submits it. Tests: permissions, confirmation, route choice, full-field editing, validation, recovery, accessibility and mobile layout.
5. **Review and release.** Review security and money invariants, run service and Console tests/build, and update operator/docs contracts. Deploy and live-test only after the user's separate VM instruction.

## Safety gates

- No existing Posted or REVERSED voucher content, revision, number, print or effect is overwritten.
- The original Posted Purchase's PDF preview, download, print and revision history remain available after Full edit or Cancel posted. A replacement has its own separately identified print.
- No replacement Purchase is posted before its full reversal commits.
- Closed periods, filed tax, settled open items and downstream stock usage can refuse reversal. The user gets a concrete reason and a linked adjustment route where supported.
- Every write is company scoped, permission checked, versioned, idempotent and audit recorded. Unknown outcomes retain their operation identity for recovery.

The generic reverse endpoint now supports eligible Account, Product, and Mixed Purchase invoices through Accounting's invoice and stock guards. It refuses reversal when settlement, tax records, downstream stock use, period rules, or other dependent effects make full reversal unsafe. The linked adjustment route for ineligible full reversals remains a separate gap; the Console surfaces the refusal instead of rewriting the posted bill.
