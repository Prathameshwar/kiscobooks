# Inventory reports final review

Reviewed 2026-10-22, following implementation of the ten reporting consumers. Scope is
API, calculations, database evidence, source integrity, authorization, navigation and exports.
UI changes, load tests and soak tests are excluded.

## Findings and fixes

| Finding | Impact | Fix |
|---|---|---|
| Movement summary retained snapshot opening/turnover for a shorter requested period | Raw rows could show April turnover on an April 20-30 report with no movements | Compute opening from movements before `date_from`, and inward/outward from the requested inclusive period. Expose these columns in both report views. |
| Missing expiry bypassed minimum remaining-life checks | Unknown shelf life could inflate eligible stock, availability and reorder calculations | Exclude positions with a minimum-life requirement and no expiry from eligibility; retain physical quantity/value. Include those positions as unknown-expiry exceptions even when the item is not lot tracked. |
| Inventory drilldowns discarded parent filters or replaced a selected group | Detail could include other locations, inactive items, or sibling/overlapping groups excluded by the parent | Carry the parent's item/location/group/owner/inactive filters into the target. Omit a group link when it would replace a different parent group: the target's single-group filter cannot express their intersection safely. |
| Duplicate origin IDs were accepted within a position | Ageing could present one receipt origin as multiple contradictory cohorts while quantities still reconciled | Reject repeated receipt-origin identities within a position. Origins shared across distinct positions remain supported. |

Each finding was reproduced with a failing regression test before the fix. Shared wire
schemas, database models and migrations do not change in this review.

## Report review matrix

| Report | Checks |
|---|---|
| STOCK_SUMMARY | Opening/closing arithmetic, zero stock, eligibility, reservations, ownership/custody and unknown capabilities |
| ITEM_LEDGER | Requested-period opening, stable movement ordering, per-position running/closing balances and retained history |
| LOCATION_STOCK | Leaf balances, descendant selection and preservation of the parent location in drilldowns |
| STOCK_VALUATION | Owner values, exact unit costs, frozen financial GL verification and filtered reconciliation scope |
| BATCH_SUMMARY | Separate current and movement grains, exited serials, serial replay and history capability gates |
| STOCK_EXPIRY | Expiry-day/window boundaries, minimum-life requirements, unknown dates and retention of physical stock |
| STOCK_REORDER | Eligible unreserved supply, zero-stock items, order capability/scope and no duplicate demand deduction |
| STOCK_AGEING | Residual-origin reconciliation, unique origin identities, receipt/manufacture basis and nonoverlapping buckets |
| STOCK_MOVEMENT | Requested-period turnover, distinct transfers/consumption, nonmoving observation windows and insufficient history |
| STOCK_GROUP_SUMMARY | Ancestor/membership deduplication, incompatible units, filtered scope and inactive-item drilldowns |

All ten are included in API/worker/paging/drilldown checks against legacy and versioned
source fixtures, and CSV/XLSX/HTML/PDF export checks. Security review walks CLAUDE.md
sections 5/6: company/tenant/actor isolation, field denies, permission revocation, signed
navigation/downloads, exact arithmetic and immutable evidence. The named `/simplify` and
`/security-review` commands are unavailable; these checks are performed manually and with
the existing regression suites.

## Verification

- Broad report/registry/navigation/drilldown gate: **330 passed, 1 MySQL-only skip**,
  including all ten reports with legacy and versioned source fixtures and all forty
  report/format combinations. Inventory calculations and serial trace reached **98.22%**
  combined branch/statement coverage (90% required).
- Final gate after the overlapping-group fix and test correction: **92 passed**, with
  **98.22% inventory calculation/trace coverage**. This reruns all ten legacy/versioned
  API cases, inventory calculations and shared drilldowns, plus the filtered-group and
  short-period CSV regressions. The forty unchanged export-matrix cases were deselected
  because they passed in the broad gate.
- Accounting handoff: **4 passed**; Identity report authority: **4 passed**.
- Reports strict mypy: **117 source files** pass. Ruff checks and formatting pass for the
  three changed implementation modules and both changed inventory test modules.
- Reports OpenAPI freshness and generated client checks pass; API-client tests: **8 passed**.
- The final scoped gate initially reported 91 passed and one failure caused by a test
  assertion displaced from the missing-coverage test into the CSV test. Restored the
  assertion to its original test; the three affected API tests then passed. This was a
  test placement error; the CSV balance assertions had already passed.

Native MySQL migrations were reviewed against the implementation checkpoint and are unchanged
by these fixes; native migration tests were not rerun in this review. The broad gate's one
native-only skip is retained above. Earlier native evidence is in
[the implementation checkpoint](inventory-implementation.md#verification-windows-2026-10-22).

## Remaining delivery boundary

These are reporting consumers and a trusted Accounting publication adapter. Operational
B20-B26 stock producers remain unfinished; companies without genuine complete inventory
evidence are blocked. Movement input remains bounded rather than supporting a million-line
streaming ledger. This review does not activate reporting in production or certify those
separate capabilities. No load or soak tests were run.
