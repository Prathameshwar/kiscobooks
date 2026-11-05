# Product stock and ledger review — 31 October 2026

Review only: no application fixes, commits, publication, or live business-data changes were made for this review. Existing uncommitted changes from earlier work were preserved.

The review identifies **6 bugs and 6 implementation gaps**: four High and eight Medium findings, with no confirmed Critical finding. Two Medium UI bugs are still-open findings from the earlier unit review, not newly introduced duplicates. The CSV records that relationship.

- [Findings and implementation sequence](testing/product-stock-review/findings.csv)
- [26 reusable acceptance/review cases](testing/product-stock-review/cases.csv)
- [Executable diagnostic runner](testing/product-stock-review/run_probes.py)

## What is maintained and working

Accounting owns an append-only stock posting/movement ledger, quantity balances, warehouse cost pools, FIFO layers, value entries, receipt origins and allocations, serial custody, transfers and shipment claims, reversal history, and opening/count application evidence. Product prices are separate from native inventory cost. Stock preparation alone does not receive goods.

Native quantity, receipt-origin, valuation, and inventory-control reconciliation passed for all **12 currently configured companies** in a read-only live check. The live fixture is small: two postings and two movements, one quantity balance, and one cost pool, concentrated in one company. These checks establish consistency of existing data; they do not establish broad live transaction coverage.

Code inspection and the regression suites cover FIFO/moving-average costs, transfers, linked returns, serial claims, reversal safeguards, negative-stock rejection, backdating restrictions, projection repair, count cutoff reconciliation, and tenant/field-policy guards. Internal transit uses its own reserved warehouse; it is not merged into the source warehouse cost pool. Group reports separate different units, and summary/reorder logic explicitly handles zero-stock products. Those investigated concerns are not reported as defects.

## Bugs

| ID | Priority | Finding and practical effect | Complexity |
| --- | --- | --- | --- |
| RSB01 | High | A numbered physical count with no variance is rejected. A valid audit/count application cannot be completed when physical quantity equals book quantity. | Medium |
| RSB02 | High | Native reporting capture drops the serial identities retained by the stock owner. Complete serial reporting cannot validate the movement lineage. | Medium |
| RSB03 | Medium | An existing position with a missing balance projection disappears from the list; its detail returns HTTP 500. This conceals a recovery/reconciliation problem. | Medium |
| RSB04 | Medium | A native dispatch contributes to total outward quantity but no displayed outward-action subtotal. Its consumption/activity classification is also absent. | Medium |
| RSB05 | Medium | Stock `0.0010` displayed at precision two becomes `0.00`, without an exact secondary value. | Low |
| RSB06 | Medium | Stock quantities lack the base-unit identity/label in the read DTOs and table. Quantities for different products are ambiguous. | Medium |

**RSB01:** `stock_reporting.capture()` runs in the common committed-owner transaction and requires at least one stock movement. Native zero-variance COUNT correctly produces no quantity/value movement. Adding an issued count voucher number makes the reporting handoff run and reject the otherwise valid count. The reusable diagnostic isolates the native empty-movement COUNT posting handoff and verifies rejection/transaction rollback with a minimal committed-result fixture. Native count application tests establish the zero-difference behavior separately; this isolated diagnostic does not execute the full approval/broker workflow. Existing count tests generally use legacy commands without a voucher number, which skip the handoff. The repair must retain a successful no-change count and its audit evidence without fabricating a movement or journal.

**RSB02:** `StockMovementUnit` retains the received unit, but the normalized movement report payload has `serials: []`. The reporting trace validator requires the number of serial identities to match the movement quantity for serial-tracked products. The diagnostic uses a genuine disposable owner receipt and invokes the trusted capture function with a minimal committed-result fixture. This is not a full approval/broker test. Origin/allocation details should be included in the same contract review; immutable movement payloads require a deliberate version/backfill approach.

**RSB03:** stock position reads use an inner join to the balance projection. With a missing projection, list and detail behavior disagree with the retained movement and cost pool. Native reconciliation correctly rejects the damaged state. The review deliberately removes only a projection through Core in a disposable fixture to simulate recovery damage. ORM mutation/deletion guards remain enabled and correctly prevent ordinary deletion; no live projection was altered. This is a read/recovery defect, not a proven posting-path corruption bug.

**RSB04:** complete report evidence with a `DISPATCH` of 40 produces total outward 40 but zero for sales, consumption, supplier returns, and transfer-out columns. `DISPATCH` and reversal/adjustment categories do not have complete action outputs. Last-consumption logic ignores dispatch, so the fixture is marked nonmoving despite that recent outward movement. Dispatch must not be silently relabelled as a financial sale: define its operation/consumption semantics and expose every supported action while keeping aggregate totals conserved.

RSB05 and RSB06 correspond to earlier unit-review B07/B08. Current component diagnostics reproduce both. Native DECIMAL precision is retained; the displayed quantity loses information.

## Implementation gaps

| ID | Priority | Missing delivery | Complexity |
| --- | --- | --- | --- |
| RSG01 | High | Complete fenced inventory report snapshots and verified legacy movement backfill. | High |
| RSG02 | High | Goods invoice/note stock recognition and financial execution together. | High |
| RSG03 | Medium | Date-range product stock ledger with opening/running/closing balances and source drill-down. | High |
| RSG04 | Medium | Public on-hand versus operation-eligible/available stock summary. | High |
| RSG05 | Medium | Searchable physical-count register, revision history, and reversal-aware navigation. | Medium |
| RSG06 | Medium | Entered/measured unit and conversion lineage in stock reads/reports. | Medium |

**RSG01:** the ten inventory report engines exist, but the native operational capture publishes MOVEMENT only. No operational producer supplies a complete company COVERAGE cut plus item/location/group/position/origin and required GL/valuation facts. The generic trusted `inventory_reporting.publish()` function supports evidence publication; it is not a complete producer by itself. Movement-only records correctly fail with “coverage is unavailable.” The live legacy fixture has zero inventory feed records. Do not manufacture complete coverage from a receipt or use historic signed bin values as residual bin assets. Warehouse cost pools and physical positions have different valuation grains.

**RSG02:** goods invoice execution explicitly rejects `GOODS` and item-line-linked commands with “goods invoice execution requires the stock phase.” Receipt/dispatch execution does not complete Sales/Purchase invoice stock and financial recognition. This is documented missing delivery; the rejection protects against partial posting.

**RSG03:** the current stock page provides warehouse balances, positions, and raw movement lists. It does not provide the ledger specified in the stock reporting design: pinned cut, business-date range, opening/inward/outward/running/closing quantities and values, unit/currency separation, voucher/action/reason, and source links. A standalone ITEM_LEDGER calculation engine exists, but it depends on RSG01 for native operational delivery.

**RSG04:** native candidate selection already checks physical eligibility, holds, expiry, custody, and operation rules. Public stock views expose on-hand quantity but no comparable eligible summary. Reservation semantics are not universally implemented and must be shown as unavailable until supported, rather than inferred as zero.

**RSG05:** count observations can be started, revised, and read by known ID, but there is no list/register to find previous counts by product/location/date/status. Detail status derives APPLIED from the retained root application claim; it does not explain a subsequent reversal or link it. The retained claim correctly prevents accidental reapplication. Serial counts and wider damage/disposal workflows remain outside the current initial non-serial usable-stock count contract.

**RSG06:** entered and measured quantities are retained in native voucher/source evidence, but stock movement/report read contracts expose base quantity without the entered unit, unit revision, conversion, or measurement explanation. Exports and drill-down must preserve historical evidence when current product configuration changes.

## Recommended implementation order

1. Fix RSB01–RSB03 at the native handoff/read boundaries, with fail-first acceptance cases PS11–PS14. Resolve immutable report serial/origin schema evolution before backfilling.
2. Fix movement-action semantics and exact quantity/unit display (RSB04–RSB06). Add permission-safe unit metadata and precision behavior using shared formatters.
3. **RSG01 quick plan:** specify a company fenced snapshot and valuation grain; produce all complete owner evidence atomically; backfill verified historical movement metadata; reconcile counts/serials/quantity/value/GL; then enable and test every registered report from the frozen source cut. Do not loosen completeness checks to make reports appear to work.
4. **RSG02 quick plan:** specify Sales/Purchase and goods-note recognition triggers and source links; capture approved stock/cost/accounting facts; commit inventory plus GL through the native owner transaction; verify uncertain delivery, replay, partial returns, dependent reversal, GST applicability, and both costing methods.
5. **RSG03 quick plan:** deliver the pinned native product ledger/API over RSG01 evidence, with stable paging and date ranges; expose unit/source lineage; connect voucher/action drill-down and exports. Complete RSG06 with it.
6. **RSG04 quick plan:** define operation-specific on-hand/eligible/reserved semantics and freshness; aggregate verified owner positions without double-counting transit; expose unimplemented reservation capability explicitly; compare the display with actual allocation eligibility.
7. Add the count register and reversal-aware audit navigation (RSG05).

Each High-complexity item requires its short contract/transaction plan before implementation. The remaining scoped fixes can proceed using the recorded cases. This review does not authorize or apply those fixes.

## Verification and limits

Test results and diagnostic reruns are recorded with the review cases and local ignored logs under `.test_artifacts/product-stock-review-*`.

| Verification | Result |
| --- | --- |
| Read-only live owner reconciliation | 12/12 companies pass physical and value/GL checks; small existing fixture. |
| Accounting reads/costing/reconciliation/reporting/counts/repair | 30 pass initially; two fail during unrelated HTTP setup with OperationalError. Both pass on isolated reruns, covering 32 distinct tests. |
| Ledger/storage/control/candidate/selection regressions | 27 pass on SQLite; three serial/partial-transit cases fail at exact residual-layer comparisons. All three pass unchanged in a unique disposable MySQL schema, covering 30 distinct cases across the two environments. |
| Reports inventory engines/API/native handoff | 159 pass. |
| Review diagnostics | Four native storage/handoff probes, two report probes, and one component probe pass, reproducing the documented defects/gap. |
| Stock/tracking/summary/navigation components | 57 pass initially; one batch-directory case times out at its default async wait. That case also fails on an unchanged isolated run and passes with a 10-second wait. Treat as fixture timing evidence, not a confirmed product bug. |

The original full-count reproduction ran successfully once, but later reruns sometimes failed before count execution at accounting setup. The reusable final diagnostic isolates the stock reporting boundary to keep those setup errors separate from RSB01. Early missing-projection probes also encountered the correctly enforced ORM deletion guard; the final probe uses explicitly disposable Core recovery damage. The serial probe required flushing the pending report record before reading it. These fixture corrections did not change application behavior.

The three deeper ledger failures are explained by SQLite's NUMERIC arithmetic at residual-layer subtraction: rounding an aggregate does not make subsequent binary subtraction exact. They pass under MySQL DECIMAL arithmetic, including serial cost splitting and partial shipment receipts under both FIFO and moving average. They are not classified as production stock bugs. Future money/stock regression gates should include native MySQL runs for these cases. The temporary schema was generated with the existing `accounting_test_<uuid>` guard and cleaned up; existing service databases and business records were untouched. This model-initialized test schema is not a migration/release certification.

Diagnostics intentionally assert the observed defects; a green diagnostic means the defect was reproduced. `cases.csv` records desired acceptance behavior for future fixes. The runner copies uniquely named test modules into the existing test harness and removes only its unchanged temporary modules afterward.

```powershell
apis/accounting/.venv/Scripts/python.exe docs/testing/product-stock-review/run_probes.py
# Optional: --only accounting / reports / console
```

The review uses code/contract inspection, disposable SQLAlchemy storage and API/component fixtures, and read-only live MySQL reconciliation. It does not include a full authenticated browser journey, new live stock postings, full native broker delivery, or a new release certification. Component tests have CSS disabled and cannot establish visual alignment. Setup/async-wait failures are distinguished from confirmed product defects; no broad all-tests-passed claim is made.
