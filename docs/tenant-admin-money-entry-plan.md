# Tenant admin #12: Receipt and Payment entry

The generic Voucher drafts screen already contains native `VoucherMoney` capture
and `VoucherWorkflow` approval/posting/recovery. Reuse those implementations for the
offered Receipt/Payment destinations rather than creating another money calculator.

1. Add kind-specific route dispatch and filter active types by the requested kind.
   Verify the loaded field-set belongs to that kind. Preserve generic draft and stock
   opening callers, typed policy/read-only fields and company-scoped permissions.
2. Verify typed capture, draft save/replay/reload/cancel and the existing workflow.
   Add route/kind and failure regressions before changes; run affected Console suites.
3. Configure supported Receipt/Payment types through ordinary QA UI/API where current
   authority permits. Verify input and refusal branches through the UI. Actual posting
   and nonzero allocation/ledger/register reconciliation require appropriately delegated
   actors and the applicable C1 release evidence; do not weaken either boundary.
4. Review, fix findings and record reusable cases/results. Invoice and stock effects
   remain the separate #13/#15 owner work.
