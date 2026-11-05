# FMCG backend implementation checklist

**As of 2026-10-12:** The [FMCG plan](fmcg-business-implementation-plan.md) governs scope. This checklist tracks its additional FMCG acceptance only; the [voucher delivery tracker](voucher-delivery-tracker.md) remains authoritative for B-batch and C-checkpoint status. An unchecked item is not implemented or not verified. No FMCG goods profile is active.

## FM0 — Contracts and prerequisites

- [ ] Reconcile current B15-B36, CI and PH work against source/migrations/tests; preserve in-progress edits.
- [x] Record the five ownership/effect profile matrix without enabling goods posting.
- [ ] Freeze operation/ownership/tax/price/licence matrix for retail, wholesale, food, manufacturing and C&F profiles.
- [ ] Close D02 costing scope and worked FIFO/moving-average receipt/transfer/return examples.
- [ ] Record B31 stock and credit reservation selections separately.
- [ ] Review B20 stock schema and source-claim/lock-order manifest before owner migrations.

## FM1 — Sources and commercial definitions

- [x] Repair Catalog price-series channel authoring, exact-channel resolution and generic fallback in source/API/SQLite tests; migration 0172 and generated contract exist locally.
- [x] Verify migration 0172 upgrade/downgrade, model/index/FK parity and multi-channel price resolution on native MySQL.
- [x] Correct Catalog barcode FK and price-level index model drift found by native parity review; preserve referenced sales channels.
- [x] Regenerate Catalog audit-event contract and pass full strict mypy after focused source/BOM/promotion test fixes.
- [ ] Run the complete 1,201-test Catalog suite after the audit artifact correction.
- [ ] Verify downstream voucher pricing consumers and review policy permissions before issue-time price activation.
- [ ] Complete protected SKU/pack/barcode/group/unit/HSN/handling source readiness and item-specific food classification.
- [x] Add reviewed, dated FOOD/category source history and signed Vouchers projection; focused tests and static checks pass.
- [x] Verify food revisions 0173-0175 and 0057-0059 on native MySQL, including the signed source workflow.
- [ ] Bind a reviewed canonical food-category taxonomy and premises/operation evidence before food execution.
- [ ] Resolve applicable company/premises FSSAI evidence and food operation from signed source facts; retain non-food path.
- [ ] Bind party/outlet/ship-to, price level/channel, credit and supplier/customer agreement evidence at issuance.

## FM2 — Accounting stock owner

- [ ] B20 canonical positions, lot and receipt/MRP cohorts, immutable movement/origin/hold records.
- [ ] B21 stock/date/period/count/hold/expiry/negative-stock guards with shared lock order.
- [ ] B22 FIFO and moving-average immutable value/GL/clearing effects; native replay and two-tenant concurrency.

## FM3 — Procurement and physical movement

- [ ] B23 purchase receipt, partial receipt, shortage/rejection, transit/transfer and controlled opening.
- [ ] Pin actual printed pack declarations, manufacturer/batch/dates and exact purchase-unit revisions per cohort.
- [ ] Reference prior receipt on supplier invoice and allocate landed cost/discount/tax without duplicate movement.

## FM4 — Goods sale execution

- [ ] B24 direct and challan-referenced goods sale with one stock/COGS effect, accepted price/tax/calculation hash and original source claims.
- [ ] Enforce allocated-cohort pack MRP, price/channel/party controls and supported GST/statutory issue evidence.
- [ ] Complete retail mixed-tender/cash-session and wholesale ship-to/credit/transport backend cases.

## FM5 — Distribution demand

- [ ] B28-B30 order acceptance, schedules/conversion, partial dispatch and independent ordered/moved/billed/returned/closed quantities.
- [ ] B31 guarded stock/credit reservation if selected; test competing promises, holds and expiry.
- [ ] B32 supply/demand, replenishment and outstanding views with explicit UNKNOWN for absent producers.

## FM6 — Commercial recovery

- [ ] Publish and acknowledge same-item 10+1; atomically consume reward entitlement and move/cost all actual units.
- [ ] Separate paid bundles, manual bonus and independent gift/sample tax purposes; extend schemes only with verified stock/tax contracts.
- [ ] B25/B26 original-source-capped customer/supplier returns, damaged/expiry claims, tax/component reversals and correction history.

## FM7 — Food safety

- [ ] Enforce selected food/premises licence, batch/date/minimum-life and FEFO under owner locks.
- [ ] Hold/quarantine/recall/disposal and downstream customer trace with protected correction/export history.
- [ ] Enable cold-chain variant only after measured excursion-to-hold evidence and acceptance.

## FM8 — Reports and activation

- [ ] B27a-e, B32 and FMCG outlet/channel/cohort/claim/stock/expiry/value/GL registers at frozen checkpoints.
- [ ] Native MySQL, two-tenant, concurrent, cross-year and failed/unknown-outcome replay/rebuild rehearsals.
- [ ] Review permissions, field denies, source freshness, Audit/outbox, generated contracts, migration restore and statutory artifacts.
- [ ] C3 per-company/premises/profile activation after all applicable B15-B36 and FMCG cases pass.

## FM9 — Separate manufacturer and principal-owned profiles

- [ ] B37-B41 BOM/packing/raw/finished/by-product genealogy, valuation and contract manufacturing under C4.
- [ ] Principal-owned C&F agreement, custody, invoice issuer, tax and commission/settlement controls under a separate activation gate.

## Review and correction

- [ ] First end-to-end review and fixes after all selected phases pass.
- [ ] Second end-to-end review and fixes, native rehearsal and evidence update before any capability is advertised as ready.
