# Master search and filter alignment review

The requested Items alignment defect and the shared filter-layout defects are
fixed. Current case evidence is in the [alignment CSV](master-filter-alignment-results-2026-10-30.csv).

| Finding | Cause | Fix |
|---|---|---|
| Simple-products search starts above Status/Sort | Label-free search mixed with stacked controls in a form grid | Use the shared FilterBar |
| Dropdown hints sit beside controls | Inline field flex layout treats the hint as another row item | Shared CSS keeps label/control in one grid row and hints/errors below |
| Lookup/date controls have different heights | Lookup inner padding and native calendar chrome increase the outer box | Shared height token, compact lookup padding and scoped date height |
| Mobile Refresh squeezes lookups | Query group can shrink beside the action until the lookup wraps internally | Query group preferred width makes the action wrap; single-select input/caret stay on one line |
| Narrow query controls can exceed their container | Search minimum/maximum sizing ignores available width | Bound search and query children to their container |

Styles live in `mfes/packages/ui/src/styles/table.css` and use shared tokens.
No per-master stylesheet overrides were added. Shared UI is version 0.1.37;
workspace-linked consumer resolutions are unchanged.

Verification includes all 45 available product/classification, warehouse,
accounting and tax master destinations at desktop width. Ten representative
destinations cover tablet/mobile widths, including lookup-heavy unit conversions,
attribute options, bins, accounts, tax dates and inventory/physical tracking.
Two development-server 500 responses had Webpack module-cache errors in the
logs; their destinations passed rechecks, retained separately from the original
attempts. These were not treated as alignment passes until rechecked.

The real-browser component suite verifies top edges, 36px control height, hints,
viewport bounds and focus at 1440/768/390px, with long lookup labels and Refresh.
It also verifies ordinary forms and explicitly stacked dropdowns retain their
layout. All four geometry cases and all 27 affected simple-product component
cases pass. The shared primitive suites passed their functional assertions;
the initial geometry failures were corrected and rerun separately.

The existing UI/API authority, query semantics and native dropdown behavior are
preserved. Manual simplification/security review found no remaining issue in
the changed styling scope. Named review commands are unavailable in this
environment; equivalent manual review was performed. Geometry and focus checks
do not claim execution of every dropdown option or the full business lifecycle.

Reuse the [live directory runner](testing/tenant-admin/verify-master-filter-layout.cjs)
and [three-company Items runner](testing/tenant-admin/verify-item-filter-layout.cjs).
Their protected runtime artifacts remain ignored; the CSV can be rebuilt with
`docs/testing/tenant-admin/collect_pending_results.py`.
