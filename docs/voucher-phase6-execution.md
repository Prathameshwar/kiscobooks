# Phase 6 execution contract — job work and manufacturing

Status: **B37 IN_PROGRESS (preparatory definition slices only)**, 2026-10-11. This
contract refines [B37-B41](voucher-batch-note.md) and the authoritative
[tracker](voucher-delivery-tracker.md). It does not mark a batch VERIFIED,
activate C4 or authorize physical stock, WIP, tax or GL effects.
The [focused manufacturing and job-work plan](voucher-manufacturing-job-work-plan.md)
specifies the typed settings, native data and API contracts, execution invariants
and per-batch acceptance without changing these gates.

## Selected D08 baseline

The user selected the baseline first: versioned single-level BOM/process
definitions, multiple outputs including by-products/scrap, WIP, and both
principal/worker job-work directions are required. Multi-level BOM expansion
and substitutions are excluded from the initial release and must be refused,
not silently flattened. Payroll, wages, attendance and HR are excluded.
Actual processing-service invoices remain ordinary Accounting-owned service
invoices linked to the job source; estimated process cost is not an actual
invoice or wage entry. FIFO and moving average both remain required for the
initial stock-cost release under D02.

## Shared implementation rules

- Catalog owns versioned BOM/operation definitions, dated assignments,
  publication and complete consumer release evidence. Vouchers retains the
  common voucher/revision/line aggregate and adds typed shared process/custody
  details; it must not create a header table per job voucher kind. Accounting
  alone owns stock, custody, WIP, value, GL and tax effect receipts. Reports
  projects committed owner facts at a complete barrier.
- Every source relation is tenant/company scoped and refers to immutable
  revision/line IDs, not display numbers. Actual quantity, ownership, custody,
  cost, invoice and statutory claims are separately capped and idempotent.
  No order, preview, challan print or expired job may create an implicit
  effect. Physical and value histories remain immutable; corrections append.
- Keep own inventory, customer/principal property, worker custody and in-house
  WIP distinct. Cross-year openings do not duplicate receipts or reset job age.
  No release flag may claim readiness from a definition-only or SQLite-only test.

## B37 — definition and job preparation

Implement Catalog BOM identity/draft/revision, component and output relations,
exact unit/profile snapshots, process step definitions, dated selection and
protected publication. The baseline permits one primary output plus distinct
co-products/by-products/scrap, variable-per-basis and fixed-per-run inputs,
expected yield/loss, and sequential process steps. Require explicit run count
when fixed inputs apply. Reject cycles, same SKU consumed/produced, unknown
units, unsupported advanced features, stale dependencies and incomplete
consumer acknowledgements. A non-posting BOM-assisted requisition/job template
pins the published revision and exact requirement hash. Acceptance: native
migration/model parity, publish/edit/retire concurrency, two-company scope,
exact quantity examples, stale version and complete-release tests. B30 is the
upstream source-claim prerequisite.

## B38 — job orders and custody

Use JOB_WORK_IN_ORDER/OUT_ORDER and MATERIAL_IN/OUT under the common voucher
aggregate. Record principal, worker, owner, custodian, source dispatch and
typed challan/return references. Accounting commits guarded movement and
custody results for outward, inward, direct, onward and return legs; a
custody transfer cannot change beneficial ownership. Cap returns and
re-dispatches against exact original material slices. Acceptance: partial,
concurrent, damaged/lost, wrong-company, replay, fiscal-crossing and
principal/worker two-direction scenarios. Depends on B37, B23 and B25.

## B39 — manufacturing and actual cost

Vouchers captures run, actual input/output/scrap and process evidence.
Accounting consumes each source slice once, produces immutable quantity,
genealogy and WIP/value legs, and allocates actual cost across distinct
output SKU/units under the selected FIFO or moving-average policy. Preserve
paid processing charge versus capitalizable cost and nonrecoverable tax
separately. Variance is actual versus pinned expected, never a balancing
stock movement. Acceptance: multi-output cost conservation, partial run,
scrap, rework refusal, correction/replay and stock-to-GL/WIP reconciliation.
Depends on B37, B38 and B26.

## B40 — job and statutory working registers

Reports projects material-at-worker, third-party custody, own WIP, job age,
challan age, origin and genealogy at a consistent owner snapshot. Reconcile
owned WIP/control accounts to GL, exclude third-party goods from assets,
and retain cross-year age. Provide ITC-04 working data only for explicitly
supported India GST cases; reject incomplete statutory source coverage.
Permission-safe exports, frozen-run/rebuild equality, no multiplied genealogy
joins and T3/T4 applicability checks are required. Depends on B38, B39 and B18.

For India GST, retain principal-issued challan identity, source dispatch date,
direct-to-worker receipt date when applicable, onward/partial-return challan
chains, material category and owned residual quantity. The review projection
uses an effective-dated Section 143/Rule 45 policy for input versus capital
goods, exempt tools, return/supply outcome and ITC-04 reporting period. The
first release **flags a reviewable deemed-supply case** at a time-limit
exception; it never silently creates or posts an invoice or tax event. An
authorized reviewer must resolve it through the supported invoice/tax owner
path with original-date evidence. The statutory rules and portal format must
be reverified for each effective period before an export is represented as
filing-ready. This follows the user's 2026-10-11 decision and the official
[CGST Act section 143](https://cbic-gst.gov.in/hindi/CGST-bill-e.html),
[CGST Rule 45](https://cbic-gst.gov.in/pdf/amended-01012022-CGST-Rules-2017-Part-A.pdf)
and [GSTN ITC-04 manual](https://tutorial.gst.gov.in/downloads/formgstitc04.pdf).

## B41 — service invoice and completion

Link processing-service invoices, tax/settlement effects and job/material
source slices without creating a second stock movement or duplicate service
charge. Close only after unresolved material, scrap, charges and statutory
exceptions are classified with evidence; later corrections append. Verify
all four job-work kinds, challan/aging exceptions, issuer/recipient GST
direction, partial settlement, two-year continuity and recovery. Depends on
B40 and B19. C4 additionally requires C3 and B45.

## Progress and remaining gates

- 2026-10-11: Added a Vouchers schema-v2 definition-stage configuration slice for
  `STOCK_JOURNAL/MANUFACTURING` and the four job-work kinds. Bounded output roles
  and line limits, BOM requiredness, variance/partial-run permissions, fixed
  principal/worker direction and order requiredness now use sparse restrictive
  inheritance. COMMON controls are ignored for unrelated kinds. Combined
  consumption is rejected until its atomic Accounting owner exists. Capture
  and physical execution are not enabled by these settings; B37 stays
  IN_PROGRESS, B38-B41 remain PLANNED.

- 2026-10-11: Added a Catalog-owned exact, non-posting BOM quantity preview
  (`bom_requirements.py`). The documented 190-good/95%-yield example yields
  200 nominal output, 25 material units after 20% loss, one unit of fixed
  setup input across two runs, and 20 co-product units. It rejects absent
  run count, unrepresentable quantities, duplicate/output-input SKU, bad
  yield/loss and implicit gross-up. Four focused tests, Ruff and mypy pass.
  No model, migration, API, published revision, consumer release or physical
  effect exists; B37 remains IN_PROGRESS only for this preparatory calculation.
- 2026-10-11: Added a Reports-owned, review-only deadline classifier from an
  Accounting-resolved residual and an explicitly supplied effective-policy
  deadline. It distinguishes within-limit, closed, exempt and review-needed
  cases, including direct-to-worker origins. It deliberately does not derive
  statutory due dates, infer missing returns, issue invoices or post tax. Three
  focused tests pass, including late final clearance after residual reaches
  zero. The complete Reports suite passes 85 tests with one native-only skip;
  the Catalog preview/migration slice passes eight with one native-only skip.
  No owner feed, projection, policy table, export or user workflow exists.
  B40 remains PLANNED, not verified.
- 2026-10-11: Added an Accounting-owned, non-posting multi-output actual-cost
  allocation preview. It uses explicit output weights and exact four-place
  conservation, keeps noncapitalizable charges separate, and rejects negative
  costs, excess precision and duplicate output SKUs. Three focused tests,
  Ruff and mypy pass. No stock/WIP owner, cost-origin receipt, valuation layer,
  accounting journal or execution command is implemented by this preview;
  B39 remains PLANNED, not verified.
- B15-B36 prerequisites, including B30 and stock B23/B25/B26, remain open.
  B38-B41 and C4 remain PLANNED. D08's advanced-depth choice is settled,
  but its detailed native schema/publication/claim manifest and D09 supported
  job-work GST cases still require implementation and review. The D09
  time-limit exception decision is review-only, not automatic posting.

## Plan update

- 2026-10-11: Added the focused manufacturing/job-work backend plan, detailing BOM
  publication, typed manufacturing and job-process settings, owner custody/WIP/cost
  effects, four Material In/Out role paths, source claims and B37-B41 acceptance.
  Existing batch, D02/D08/D09/D11/D12 and C4 statuses are unchanged.
