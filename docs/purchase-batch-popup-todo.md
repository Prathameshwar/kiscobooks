# Purchase batch chooser — local delivery checklist

Scope: a tracked Purchase product prompts for one existing or new batch after the product is verified. The selected batch belongs to its line and may be changed later. No VM deployment is part of this checklist.

- [x] Keep the existing quantity and product autofill behavior intact.
- [x] Show one batch chooser after a newly selected batch-tracked product on mobile and desktop; do not prompt for untracked products or reopened lines with a selected batch.
- [x] Search only active, unheld batches for the selected company and product; show manufacture and expiry dates, and verify a choice before applying it.
- [x] Create a batch in the chooser with an idempotent Accounting write. Required dates follow the published product profile; optional dates remain optional. Keep validation and write errors in the chooser.
- [x] Put the chosen batch on the correct Purchase line, clear serial selections when it changes, and clear the batch when the product changes. Cancellation leaves the line incomplete.
- [x] Let the user reopen the same chooser from the line. Show the selected batch and expiry on mobile and desktop, including read-only review.
- [x] Test tracked/untracked, select/create/cancel/change, wrong product, invalid/held/expired batch, permissions, stale asynchronous responses, dates, and mobile keyboard/focus behavior.
- [x] Run affected unit tests, Console typecheck and production build. Review permission, tenant, idempotency, quantity, and stock invariants; fix findings.

Release and live VM checks await a separate user request.

Review: Batch reads and writes are company and product scoped. A selected batch is re-read before application; prepared responses must match code and dates. Batch display requests are permission gated. Existing SearchSelect and Modal tests cover stale search responses, keyboard navigation, focus and dismissal. The Purchase list action now follows the API's editable statuses; saving a submitted or approved bill opens a draft revision.
