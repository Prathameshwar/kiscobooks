# Batch and serial delivery checklist

Started 2026-10-28. Scope approved by the user: complete the seven phases, maintain
this checklist, and perform two final reviews with fixes. Existing stock design,
owner boundaries and activation gates continue to apply.

Completed implementation and both final reviews on 2026-10-28. Review findings
were fixed and verified; current evidence is summarized below and recorded in
[stock-posting-delivery](stock-posting-delivery.md). Normal installation admission
remains disabled. Activation and complete inventory-report source cuts retain
their separate release gates; the existing report cards remain disabled.

## Business decisions

- Approved 2026-10-28: prepare batch/serial identities before receipt. Preparation
  creates no quantity, carrying value, position or available stock.
- Approved 2026-10-28: block negative stock and expired issues; expiry remains
  usable through the expiry date in company timezone; enforce published remaining
  shelf life; reject backdated changes which would alter subsequent posted stock.
- Approved 2026-10-28: stock quantity and cost are warehouse-specific. Initial
  FIFO/moving-average pools use company/SKU/warehouse scope, not a company-wide pool.
- Approved 2026-10-28: accrue uninvoiced receipts/dispatches through explicitly
  configured company clearing accounts. Missing mappings block their posting.
- Approved 2026-10-28 after scope clarification: include the full native stock
  posting engine in this delivery. This supersedes the earlier wizard-only opening
  stock deferral. Preparation remains distinct from physical posting.
- Catalog owns published product/tracking/identifier definitions. Accounting owns
  physical identities, authoritative holds, positions, movements and values.
  Vouchers owns operational source documents and approval/execution workflows.
- Both FIFO and moving-average costing remain selected in D02. Unresolved stock
  recognition/account mappings and stock-posting contracts must not be guessed or
  bypassed by a master editor. Prepared records never claim operational readiness.

## Phases

- [x] 1. Inspect contracts; record decisions, scope, owner/schema/API manifest and
  permission/field-policy requirements. Identify remaining dependent gates.
- [x] 2. Accounting tracking foundation: batches, controlled revisions, serialized
  units/identifiers, audit/holds/history; strict inputs, isolation, migrations and
  source/profile verification. No duplicate stock authority in Catalog.
- [x] 3. Batch APIs: scoped directory/detail/registration/corrections/hold workflows,
  indexed bounded lists and optimistic concurrency/idempotency.
- [x] 4. Batch screens: company and product-filtered directory/detail/forms, shared
  styles, accessible controls, configuration/permission gating and all error states.
- [x] 5. Serial APIs/screens: scanner/paste, exact namespaces/normalization, configured
  slots/counts, duplicate detection, batch association and historical traceability.
- [x] 6. Native stock/Vouchers integration: source identity, receipt/opening/issue/
  transfer/return/cancel, exact quantities, eligibility, expiry, period/first-use
  guards, costing/GL conservation and duplicate-issue protection. Resolve applicable
  D01/D02/D03/D07 gates before enabling any physical effect.
- [x] 7. Verify integration/browser flows, migrations/models/scripts/SDK, permissions,
  rollout/readiness and end-to-end positive/negative configuration combinations.
- [x] Review 1: security, tenant/company scope, field policies, histories, concurrency,
  exact arithmetic and retry/rollback. Fix findings and rerun affected checks.
- [x] Review 2: end-to-end UI/API/browser, recovery, configuration changes and release
  claims. Fix findings and rerun affected checks.

## Final verification

- Native MySQL: final 51 checks passed, including actual competing last-serial
  writers, FIFO/moving-average warehouse effects, transfers/returns/reversals,
  projection reconstruction, clock skew, closing, zero openings and handoff.
  Migration upgrade/downgrade/re-upgrade and stock/common-intent model parity pass.
- Live owned QA company: native four-owner receipt, duplicate delivery and
  compensating reversal conserve stock and GL; Identity confirmation delivered;
  fully reversed serial is receipt eligible again. Read-only repair preview finds
  no projection changes and writes none. Normal admission remains disabled.
- UI: 122 affected Console checks and 15 posting/workflow checks passed;
  TypeScript passed. Browser preparation and stock-entry previews pass desktop
  and mobile in light/dark/ledger themes, with no exceptions or horizontal overflow.
- Additional checks: 83 inventory consumer/report, 21 shared transport/contract,
  15 Vouchers worker/capture/enrollment and 40 Windows startup checks passed.
  Seventeen pure stock-domain checks exceed the 90% floor in each changed domain.
- All eight native database schemas align with their models and migrations;
  all eight APIs pass readiness. The separate Catalog rollout was left to its owner.
- Review 1 fixed exact serial/FIFO/claim reconciliation, immutable-history recovery,
  receipt ordering across writer clocks and the reversal policy-flag mismatch.
  Review 2 fixed issue-before-stock-post guidance and repair audit wire evidence;
  actual emitted repair payloads pass Audit's strict parser. Both reviews included
  permission/scope, source/first-use fences, retry, rollback and release-claim checks.

The current task is complete. Wait for the user's confirmation before starting
another task, as requested. No stock admission or complete Reports activation was
performed by closing this implementation checklist.

## Verification history

Earlier entries below retain their original stage-specific status; the completed
checklist and final verification above supersede their pending-work notes.

D07 preparation manifest: four Accounting tables, one CREATE/DROP per migration:
`stock_lot` (company/SKU/source namespace/code uniqueness, date bounds, source party
FK and expiry/item indexes), `stock_unit` (scoped batch FK and item/batch indexes),
`stock_unit_identifier` (scoped unit FK, namespace/type/normalized-value uniqueness,
bounded slot/type/version and unique unit/type/slot), `stock_tracking_event`
(bounded immutable registration/correction/hold/lifecycle evidence and target index).
Active/retired are registration states, not quantity/availability states. Preparation
is shown separately from stock posting/availability. Existing
stock design permits normalizing correction/hold evidence into common history.
Posting/position/value tables remain under the separately recorded D01/D02 gates.

Initial inspection: Catalog profiles and identifier requirements exist. Accounting
has an inventory reporting handoff but no `stock_lot`/`stock_unit`/stock posting
models; Vouchers has no goods stock execution. The delivery tracker still marks
stock extensions of D01/D02/D03/D07/D11 open. Existing product menus are honest
disabled placeholders. They will be enabled only for supported native operations.

Foundation progress: preparation/correction/hold/lifecycle APIs and shared-style
directory/editor/detail/history screens are implemented and being verified. The
initial API/source checks exercise tenant/company boundaries, native field denies,
normalization/uniqueness, version conflicts and replay recovery. Parent-scoped
published profile lookup was corrected during contract review. MySQL upgrade,
downgrade and re-upgrade rehearsals passed, and the local Accounting database,
models and readiness head align at 0171. Scoped role seeds were applied and all
eight services are healthy. The first UI/navigation review passes 79 checks.
Preparation menus are enabled behind company/profile/read-permission checks.
Retained retries no longer need Catalog availability; partial date corrections
preserve fields the caller cannot edit. Physical posting remains pending phase 6.

Subsequent native progress: Accounting migrations 0172–0199 and Catalog 0209
passed disposable MySQL upgrade/downgrade/re-upgrade and model parity and were
applied locally. Thirteen native stock-ledger tests pass: FIFO/moving-average
warehouse and bin transfers, serial custody/cost residuals, linked returns,
partial transit receipts, dependent-posting reversal order, exact return reversal
claims, insufficient stock and backdating. Catalog definition leases pass three
isolation/immutability/write-fence tests. The compiler, common posting protocol,
GL/Identity integration and stock UI remain in progress; these tests are not
release activation evidence. Used-stock registration/date guards are implemented.

Live tenant3 preparation evidence is saved privately: batch creation, date/history
correction, hold, serial scanner Enter and duplicate rejection passed; desktop and
mobile layouts in all three themes had no horizontal overflow. Preparation creates
no quantity or value. Final two complete review passes remain outstanding.


Stock execution integration progress: native signed-command/status/cancellation
and valued/zero-value first-use tests pass. Vouchers now captures physical effects
in common revision/line children (0098-0100), builds accepted stock commands with
both date proofs, and reconciles a lost commit response through the dedicated
stock channel. Its delivery test verifies one actual send and automatic discovery
of the company owning the accepted command. Eleven capture/money/delivery tests
and the six expanded stock capture/delivery checks pass on SQLite.

Accounting 0200 retains indexed transfer destinations and passed native reversible
migration/parity and all thirteen ledger tests; it is applied locally. Stock read
APIs now use exact resource response models, bounded cursors and contributing
field policies; two read/scope/filter tests pass. A regression demonstrated direct
manual inventory GL posting could bypass stock, and a native preparation/commit
guard now prevents it; the guard and execution suite pass six checks. Linked GL
opening reversal is guarded until physical opening bridge claims are released.
Explicit currency columns for every carrying-value history/projection (0201-0209)
are undergoing native rehearsal and have not yet been applied locally. Full
posting UI, owner enrollment, warehouse acknowledgements, reporting/rebuild and
final two reviews remain open; engine activation remains disabled.

Latest continuation: currency migrations 0201-0209 are now applied locally and
full database/model parity passes. Identity 0089 adds stock authority to the common
reservation lifecycle and has passed native reversible migration/first-use checks.
All eight APIs and the source/execution/delivery workers are healthy. Warehouse
stock/cost read views and explicit stock accounts have shared-style Console UI;
the stock/Masters regression run passes 36 checks and Console typechecking passes.
FIFO/FEFO physical ordering, original transfer age and unused-mapping corrections
now have regression coverage. The detailed current checklist is maintained in
[stock-posting-delivery](stock-posting-delivery.md). Physical posting activation,
full stock entry, current NoStock coordination, reconciliation/reporting and both
final reviews remain open.
