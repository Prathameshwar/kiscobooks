# Product import UI delivery

Current Simple creation imports are described in
[simple-product-import-plan.md](simple-product-import-plan.md). Since 2026-11-04
they create active products and post optional opening stock automatically. The
original draft lifecycle and advanced controls described below remain applicable
to the legacy/advanced `products` definition only.

## Scope and phases

Implement the requested product import page using the existing Catalog-owned
shared master import APIs and the existing shared Console design system.

1. Add a narrowly scoped Console import proxy, its bounded upload transport and
   private file downloads. Consume existing generated Catalog contracts. Preserve
   current company scope, step-up proof, origin checks and command idempotency.
2. Add the product import page: configured template download, CSV/TSV/XLSX upload,
   stage/validate/review/commit, row messages, correction/revalidation, explicit
   cancellation and resumable history. Enable the Products directory import link
   according to current import-read authority. Party/supplier imports were initially
   disabled and are now delivered in [party-import-ui-delivery.md](party-import-ui-delivery.md).
3. Verify scoped routes, strict proxy policy, file limits, UI lifecycle branches,
   exact retries, stale reviews, loading/empty/error messages, keyboard access and
   responsive themes. Exercise the native API and tenant3 browser flow; review
   twice, fix findings, and record evidence.

The native API remains authoritative for fields, configuration, matching, required
references and writes. Templates come from current authorized native snapshots.
Legacy/advanced imports do not auto-activate products or post financial documents.
No owner model, migration or public API changes are planned. Existing resource
and bulk permissions are reused. No credentials or private source files are tracked.

## Design decisions

- Use a dedicated `/masters/items/import` page with New import and Import history
  views. A selected job is addressable in its URL for later review.
- Default to create-only mode. Updates are an explicit selection and remain
  subject to native operation permissions. Clearly identify product-family versus
  existing SKU templates and goods/services applicability.
- Keep the native 200-command, 16-file and 8 MiB combined source bounds. Use shared
  FileUpload, Cards, Stepper, DataTable, Pager, notices and form controls.
- Native operations are bounded request-driven commands. Show an indeterminate
  pending state rather than inventing a row percentage or background worker.
- Keep exact request bodies/keys after ambiguous failures. Recover that same
  action before new changes. A stale review requires a fresh job read and validation.
- History is actor-owned and cursor-paged by the native API. Product entries are
  shown from each bounded Catalog history page; empty pages are labelled honestly
  and retain pagination. No unbounded fetch or invented total is introduced.

## Decision log

- 2026-11-04: Deliver flat, ready-product Simple imports, durable validation and
  admission continuations, owner-driven activation/opening and resume/history.

- 2026-10-27: User requested implementation of product import with validation,
  history, messages and existing UI styling. Reuse the delivered native import
  framework; keep party/supplier imports outside this delivery.
- 2026-10-28: Match product mode and applicable field settings using the existing
  native configuration and row commands; see product-import-configuration.md.

## Delivered behaviour

`/masters/items/import` provides New import / Import details and Import history
views. Product directory links use current company-scoped import-read authority;
readers can review their own history and available downloads, while write controls
require import management. Native product operation and field authority are still
checked by Catalog when preparing templates, validating, committing and downloading.

The page downloads configured CSV, TSV and XLSX templates. It supports single products
or product families with their first SKU according to company configuration, plus
updates to existing SKUs in advanced mode. Existing-SKU imports are update-only;
new variants use the native variant workflow. It supports goods/services templates,
create-only or update-only product operations, independent-group or all-together
atomicity and stop/continue error handling. It retains exact source bytes, validates
combined file bounds and normalizes filenames for the native source-file contract.

The [configuration-aware import delivery](product-import-configuration.md) extends
template context with the effective date, published product type and group, applicable
field settings and native row checks. Internal guards are derived by Catalog; Excel
includes nested-field definitions. Stale template downloads can be refreshed while
retaining selected files. Required activation setup keeps native draft semantics.

Uploading stages a job; validation does not save product changes. The result view
shows file/sheet/row keys, statuses and per-attempt field messages. Commit requires
an explicit review of the current version/digest. Reports, normalized staged input,
correction files and original sources use private short-lived native tickets.
Corrected files create a revision; partial/failed work uses native retry/revalidation
before another reviewed commit. Completed effects are never repeated.

History and every child list use bounded signed cursors without unsupported sort
parameters or fabricated totals. Historical source downloads include the matching
revision. Row-location lookups are bounded to the native 200-command maximum.
Expired payloads keep the retained native summary/history behaviour.

## Review findings and fixes

1. Transport and workflow review: the ordinary Console JSON boundary is only 16 KiB
   and its service timeout is shorter than the bounded import command window. The
   dedicated import route uses a fixed 13 MiB envelope bound and a 35-second upstream
   timeout while preserving the ordinary defaults everywhere else. Strict path/query
   allowlists, origin/session/step-up checks and private download headers remain shared.
   Stale commits require reload and revalidation; ambiguous writes retain their exact
   request/key and lock unrelated changes until recovery.
2. Interaction/security review: selected correction files now block actions on the
   old revision; template content cannot change while files are selected. Historical
   source downloads use their original revision rather than the latest revision.
   Import list cursors are bound to their current list source. Review includes a
   normalized-input download so the exact file-declared commands can be inspected.
   Existing shared controls/styles are reused, with a horizontal Stepper variant for
   desktop and its shared two-column mobile layout.

Both reviews walked the repository security/correctness rules. No remaining issue
was found in the delivered scope. Dedicated `/simplify` and `/security-review`
commands were unavailable; the equivalent reviews were performed manually.

## Verification

- Focused Console suite: 134 tests passed across import UI, files, strict proxy,
  scoped server page, product experience and existing product proxy tests. The final
  normalized-input download case raised the covered total to 135; the 18 affected
  import UI/file tests passed after the final receipt checks.
- Shared Stepper, wizard-layout and token tests: 34 passed. TypeScript passed.
- Existing native Catalog import API suite: 6 passed, covering goods/services,
  CSV/TSV/XLSX, price compatibility, tenant authority and template configuration.
- Real tenant3 flow in the isolated verification company: configured CSV template,
  staged missing-name input, INVALID row/field messages, validation rollback verified
  by absent SKU, private error/correction downloads, corrected revision, READY review,
  successful commit and exactly one created SKU (`IMP-MVQSE874`). Reload resumed the
  completed job and offered no duplicate commit; history reopened it and downloaded
  its original first-revision source after the second revision completed.
- A second real TSV job validated as INVALID and was cancelled through the mobile
  confirmation without creating products. Native XLSX and TSV templates downloaded
  correctly. The Excel file was verified as a ZIP workbook.
- Visual/interaction review: 36 combinations across new, prepared, invalid, completed,
  history and historical-message views, in light/dark/ledger at 1440/390-pixel widths.
  No document/main overflow or browser runtime errors. Mobile cancellation dialog
  stayed within the viewport. Desktop and mobile screenshots were inspected.

Native public APIs, models and database migrations are unchanged. Existing generated
Catalog DTOs are consumed directly, and live MySQL staging/validation/commit confirmed
the existing import tables are usable. No product or financial activation was forced.
Private browser state, sources, templates, reports and evidence remain under ignored
`.tools/extension-masters`; they are not publication artifacts.
