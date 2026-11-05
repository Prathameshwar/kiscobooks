# Inventory reports implementation

The subsequent [final review and fixes](inventory-final-review.md) records the review of
all ten reports after this implementation checkpoint.
The [2026-10-23 contract fixes](inventory-review-fixes.md) add period value balances,
expiry exposure, lot selection and typed owner valuation audit detail.

Authorized 2026-10-22: implement ten inventory reports in priority order through the existing
Reports API. API/database only; retain existing UI. No load or soak tests and no production
activation or publishing are included.

## Delivery sequence

1. Typed Accounting inventory reporting evidence, versioned feed compatibility, immutable
   source ingestion, indexed stock predicates and coverage/authority checks.
2. In order: STOCK_SUMMARY, ITEM_LEDGER, LOCATION_STOCK, STOCK_VALUATION, BATCH_SUMMARY,
   STOCK_EXPIRY, STOCK_REORDER, STOCK_AGEING, STOCK_MOVEMENT, STOCK_GROUP_SUMMARY.
3. Per report: exact calculation, supported filters, deterministic rows, signed drilldowns,
   ordinary worker publication/paging and all four existing export formats.
4. Synchronize schemas/clients; functional/native migration checks, then two review/fix passes.

## Boundaries and decisions

Accounting remains the source owner. Inventory report evidence is a typed publication
interface for a trusted Accounting stock adapter; it is not an operational balance store or
a public stock-import/posting endpoint. Existing signed Accounting snapshot/change transport
publishes committed evidence. Missing coverage blocks reports; no zero stock is inferred.
The operational B20-B26 stock posting/costing producers remain separate unfinished work.
This delivery must not mark those batches or stock activation complete.

Initial reports require complete company/item/location authority and all contributing fields.
Item/warehouse read grants are checked at admission, work, paging and download; cost output
also retains complete financial-read authority. Partial-location and quantity-only authority
are not silently represented as complete-company output.

Balance reports use an explicit frozen as-of date and classification date from the owner.
Historical dates require the matching retained snapshot. Movement reports additionally require
complete movement history. FIFO/moving-average values are owner evidence, never recomputed
from sales prices. Expiry and age are distinct; expired stock remains physical stock.
Reservation/order/valuation/age provenance capabilities must be explicit. Unsupported facts
produce null/unavailable or a blocked dependent report rather than invented zero values.
Groups never sum incompatible units, transfers never count as sales, and source identity
and receipt-age provenance survive location changes.

## Progress

All ten definitions are registered (37 total definitions). Each uses the existing v2 run,
result-query, signed drilldown, row paging and CSV/XLSX/HTML/PDF export paths.

| Order | Code | Implemented scope |
|---:|---|---|
| 1 | STOCK_SUMMARY | Opening/turnover/closing, owned versus third-party and local/transit/external; eligible, reserved and available are separate. |
| 2 | ITEM_LEDGER | Period opening and exact per-position running movement balances, dates, source vouchers, lot/location and value deltas. |
| 3 | LOCATION_STOCK | Item balances by leaf location; parent-location filters include descendants once. |
| 4 | STOCK_VALUATION | Owner FIFO/moving-average carrying values, derived unit cost and mapped stock-to-GL differences; GL evidence independently checked against the frozen financial ledger. |
| 5 | BATCH_SUMMARY | Current lot/position quantities, dates and receipt origins; optional source movement trace and individual-unit history, including exited serials. Balance and movement quantities use distinct fields. |
| 6 | STOCK_EXPIRY | Expired, near-expiry and unknown-expiry exceptions; explicit expiry-day/minimum-life rules. |
| 7 | STOCK_REORDER | Eligible unreserved balances, reorder/target/minimum quantities, shortages and suggestions; zero-stock items included; orders opt in only with complete evidence. |
| 8 | STOCK_AGEING | Residual origin cohorts, receipt/manufacture basis, configurable half-open slabs, assumed/unknown provenance. |
| 9 | STOCK_MOVEMENT | Receipts/sales/consumption/returns and transfers separated; last genuine consumption, nonmoving window and insufficient-history status. |
| 10 | STOCK_GROUP_SUMMARY | Pinned hierarchy membership, deduplicated ancestor/leaf membership and separate unit/ownership/custody totals. |

This is an implemented reporting consumer and Accounting publication adapter. It does not
complete the operational B20-B26 stock writer. A company without genuine Accounting stock
evidence cannot run these reports. Individual-unit history requires complete owner-provided
serial movement identities. Manufacturing genealogy remains separate from unit movement trace.

## API and adapter use

Discover definitions through `GET /v2/companies/{company_id}/report-definitions`. Run:

```json
{
  "code": "STOCK_SUMMARY",
  "generation_id": "<verified-generation-uuid>",
  "parameters": {"as_of": "2026-04-30"}
}
```

Send to `POST /v2/companies/{company_id}/report-runs` with the ordinary signed actor/company
context and idempotency key. All reports accept optional item/location/group/owner filters
and `include_inactive` (default true). `as_of` must equal the retained stock snapshot date.
ITEM_LEDGER also requires item_id/date_from and accepts lot_id. STOCK_MOVEMENT requires
date_from, with nonmoving_days/only_nonmoving. STOCK_EXPIRY accepts days_ahead/include_expired;
STOCK_AGEING accepts age_basis/buckets. STOCK_REORDER accepts only_shortages/include_orders.
Pending demand must exclude quantities already represented by reservations; supply/demand
must be deduplicated source evidence. Location-filtered order projection is refused until
location-specific order evidence is available. BATCH_SUMMARY accepts include_history and an
optional serial filter; a serial filter requires include_history and complete serial history.
An individual-unit trace reports +1/-1 separately from the source movement's full quantity.
Unknown inputs fail validation. Each definition exposes its closed JSON parameter schema.

The trusted Accounting adapter calls `accounting.tasks.inventory_reporting.publish` with
stable UUIDs and typed `reporting_contract.inventory.InventoryRecord` payloads, at most 200
records per call in the owner's transaction. Commit every changed page and the single coverage
record atomically. Preserve movement identities; remove obsolete current position/master
handoff rows in that same transaction. Coverage must describe the entire company snapshot,
including zero, closed/zero-quantity positions needed by retained movements, supported origins,
and control mappings. Never publish a partial import with `complete_company=true`.
The existing signed Accounting snapshot/change protocol exports this committed table.
There is no public stock authoring/import endpoint or Reports-to-Accounting write credential.
Movement sequence is a company-wide stable leg order within its effective date; transfers
retain their outbound/inbound order. Committed movement evidence cannot be rewritten or
deleted. Complete serial history is replayed against current held-unit positions before
trace output is published. Default export views show business columns; the `audit` view
retains source identifiers and source-position/source-movement quantities.

Deploy Accounting migrations **0155–0156**, Reports **0037-0038**, and reporting-contract **0.6.0**
with updated consuming locks. Start a fresh source epoch after adopting the extended stock
schema/scope. Legacy financial schema manifests remain readable; no old frozen evidence is
rewritten. Existing native query projection version stays 4: prior epochs have no stock facts.

Accounting 0156 aligns the inventory evidence table's collation and row format with its
owner model; it preserves retained rows. See [local schema synchronization](../local-schema-sync.md)
for the native upgrade/downgrade evidence and current seven-service revision inventory.

## Performance and declared bounds

Versioned balance reports read only indexed COVERAGE/ITEM/LOCATION/GROUP/POSITION/GL_CONTROL
grains. They do not load unrelated financial facts or historical movement rows. Admission
budgets the grains actually read, so a large financial/movement history alone does not reject
a small current-stock summary. Inventory arithmetic and grouping use Decimal with precision 48;
movement validation uses one accumulated balance/value map rather than a query per position.

The current inventory plans materialize bounded results. The source reader enforces the
configured native result limit (default 100,000 records) and 16 MiB source component bound;
movement reports require retained movement records within those bounds. Exceeding a bound
blocks the report; it never truncates. This delivery does not claim million-line inventory
ledger paging or measured large-inventory throughput. A streaming/pinned inventory ledger
and native movement aggregation are future performance extensions. No load/soak tests ran.

## Two review/fix passes

1. Reproduced missing zero-stock reorder rows and duplicate-position inflation with failing
   tests. Added proven-zero rows only after complete source coverage, duplicate position-grain
   checks, isolated hierarchy-cycle checks and linear movement-value validation.
2. Reproduced overly broad source admission with a small configured-budget test. Current-stock
   admission now excludes unread movements. Added independent frozen-financial GL checks,
   filtered-scope reconciliation guards, catalog read/field authority and immutable movement
   identity checks. Wrong company/tenant/actor, revocation, malformed sources and exports are
   covered by functional tests. Manual simplification/security reviews follow CLAUDE.md
   sections 5/6; named `/simplify` and `/security-review` tools are unavailable here.

## Verification (Windows, 2026-10-22)

- All ten report API/worker/paging/authority cases passed through legacy and versioned sources,
  with all four export formats. Initial focused inventory API/export gate: **61 passed**.
- Broader affected registry/API/navigation regression after the GL fix: **322 passed,
  1 MySQL-only skip**. Subsequent inventory/trace/source edge-case gate: **65 passed**.
- A fresh, separate coverage run over 280 domain/registry/navigation/source/API checks passed:
  **91.74% domain branch/statement coverage**, with inventory calculations approximately **98%**
  and serial trace **100%**. This is a fresh measurement, separate from the accumulated
  regression measurement (95.07%). Final current-unit/audit-view checks passed separately.
- Native MySQL: **108 passed** with Reports migration/model/index parity and full
  base -> 0038 -> base -> 0038. Follow-up independent GL/source-budget gate: **10 passed**;
  final batch-history/four-format gate: **7 passed**. Disposable schemas were removed.
- Accounting: **22 passed, 3 infrastructure skips** on SQLite; **25 passed** on native MySQL,
  full model/schema parity and migration round trip through 0155. Final immutable-movement
  adapter checks: **4 passed** on SQLite and **4 passed** on MySQL, with another round trip.
- Identity authority: **4 passed**, including item/warehouse field denies for stock proofs
  while unrelated catalog denies do not block ordinary financial proofs.
- Reports strict mypy (117 source files), Ruff, Accounting adapter strict checks, generated
  Reports/Accounting clients and TypeScript pass. API client: **8 passed**.
- Fresh reporting-contract 0.6.0 and Reports wheels built and installed outside source imports;
  isolated imports verify 37 definitions, all ten calculations, batch trace and packaged assets.

The initial broad service run had **611 passed, 7 failed, 7 skipped**: failures were the
valuation API/export/navigation cases fixed by using the journal's posting date in the legacy
GL read and a properly balanced, distinct-account fixture. All affected cases were rerun green
in the later gates; that original broad run is not represented as a fully passing command.
Its initial coverage failure was addressed with source-integrity, zero-stock, serial, expiry,
order-scope and provenance edge cases. No coverage exclusion or lower threshold was introduced.
Native validation initially encountered pytest's Windows temporary-directory permission issue;
workspace-local temporary directories were used for the successful reruns.
