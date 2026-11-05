# Critical/High unit and stock fixes

Authorized by the user's 2026-10-31 request to fix the Critical/High findings in
`unit-stock-review-2026-10-31.md`. No Critical finding was identified. The review's
sequence and this plan implement that request; financial release activation is a
separate checkpoint.

## Phases

1. Restore opening unit selection (B01), preserve exact public ratio transport
   through schemas/OpenAPI/SDK (B03), and stop unusable physical pack scans before
   changing an item (B04). Add fail-first API/component/serialization regressions.
2. Close voucher admission (B02) using versioned, signed, company-scoped Catalog
   unit-revision facts replicated outside write transactions. Validate dated SKU
   membership, master and SKU quantity grids, usage role and serialized rules for
   actual, billed and planned quantities. Missing owner evidence fails closed.
   Keep immutable voucher revisions and revalidate before approval/posting.
3. Extend ordinary stock capture with authoritative fixed and measured entered/base
   evidence (G01/G02), using native Catalog proofs and Accounting enforcement;
   connect the UI only to validated owner contracts. Measured actual quantities
   must never be derived from nominal ratios.
4. Implement native physical count (G05) with separate observations, immutable
   cutoff, later movement reconciliation and exactly-once variance application.
   Use verified owner cost for surplus and require review when cost is missing.
   Keep zero distinct from an omitted observation; prove quantity/value/GL
   reconciliation before exposing execution.
5. Review scope, exact arithmetic, permissions, tenant/company isolation, replay,
   stale evidence, SDK consumers and regression results. Update the findings CSV
   with actual status and evidence, including any incomplete owner work.

## TODO

- [x] B01: opening binding query and dated revision regression.
- [x] B03: exact ratio JSON, OpenAPI, SDK and consumers.
- [x] B04: actionable physical pack scan validation without partial item changes.
- [x] B02: signed dated unit facts and native voucher admission.
- [x] G01: ordinary fixed-unit entered/base capture and execution.
- [x] G02: actual measured dual-quantity capture and execution.
- [x] G05: native physical count and calculated variance execution.
- [x] Regression checks and final manual simplify/security review.

- [x] Live DB/model/migration synchronization: all eight services, 527 tables;
  affected Identity 0095, Catalog 0214, Accounting 0225 and Vouchers 0109.
- [x] Backups, disposable restore/forward rehearsal and retained original row counts.
- [x] Local sign-in deployment: missing tables added, provider discovery/password
  form verified, native platform-operator adoption and one-time recovery link.
- [x] Permanent Identity readiness guard for missing tables or stale migration head.

Approved count policies are recorded in `tenant-admin-stock-entry-plan.md`.
Production database manipulation, silently widening quantity rules, synchronous
owner reads inside voucher/money writes, and invented stock actions are excluded.

## G05 implementation plan agreed through delegated policy choice

The user delegated the remaining cost choice on 2026-10-31. Use unambiguous
verified native cost automatically; differing FIFO costs or unavailable cost
require an authorized explicit review. No latest/oldest layer default is inferred.

1. Add append-only native count snapshots and observations at the existing
   company-owned usable warehouse/bin/batch grain. Record cutoff commit generation
   and timestamp, verify book quantity against committed movement history, retain
   uncounted separately from zero, and version recounts.
2. Add a dedicated PHYSICAL_STOCK/STANDARD count contract, native exactly-once root
   claims, current movement reconciliation, existing FIFO/moving-average costing,
   variance-account GL, expiry/negative-stock/fiscal/Identity guards and reversal.
   This first contract excludes serial counts and damage/disposal workflows.
3. Connect the count controls to the generated owner API; a count is never encoded
   as a receipt/opening. Retain observations and reviewed cost in immutable native
   evidence. Revalidate the latest observation and owner state during execution.
4. Test zero/uncounted, recount conflicts, later movement preservation, surplus
   review, shortage costing, replay, cross-company/tenant scope and stock/GL
   reconciliation; review and document remaining release evidence.
