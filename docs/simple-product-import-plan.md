# Simple product import

The [combined creation/import review](simple-product-create-import-review.md)
adds Barcode columns when configured, file-wide GTIN duplicate checks and safer
continuation retries after timeout/rate-limit responses.
The [multiple-price follow-up](simple-product-multiple-prices.md) adds named selling
level columns, exact per-level validation and protected result values.

Requested 2026-11-04 after the Simple product creation review. The user authorized
template, UI, API, validation, execution, history and result improvements.

The subsequent [review and fixes](simple-product-import-review.md) cover original
attempt downloads, historical report values, lost-response status recovery and
Excel input formatting.

## Delivery phases

1. Add a configuration-aware Simple creation import definition and flat templates
   using the existing import storage, bounded file handling and history. Resolve
   business references through Catalog; reuse Simple creation preparation. Keep
   existing import history readable.
2. Validate without saving products. On Import, retain a durable creation command
   per row and complete it through the existing Simple creation coordinator,
   including native prices, activation and opening posting. Record pending,
   completed and failed rows accurately; resume with the same identities.
3. Simplify the Simple import UI, expose validation and execution results, preserve
   correction/download/history navigation, and make interruption recovery explicit.
4. Verify file formats, configuration, permissions, isolation, monetary effects,
   retries, history/downloads, UI and responsive layouts. Synchronize contracts and
   shared-library consumers; perform security and simplicity review.

## Decisions

- New Simple imports create products. Updating existing product masters stays in
  the existing workflow; product master editing is outside this task.
- Each row represents one independent product. Cross-service stock postings cannot
  honestly offer all-file rollback. The Simple UI therefore uses independent rows
  and continues other rows when one fails.
- Product codes may be blank and are generated once. Group defaults to the company
  Default group. Product type/default profiles come from published configuration.
  Goods and Services templates expose their applicable tax, prices and stock fields.
- User-facing reference columns accept business codes. UUIDs, product type revisions,
  internal version guards and nested initial-setup commands are not required input.
- Validation and its row messages are retained without saving product changes.
  Import is the explicit write action; activation/submission/posting remain automatic.
- Completed rows are immutable. Pending rows retain durable commands and resume
  without repeating completed financial effects. Correction files cannot silently
  replace commands that have already begun execution.
- Shared import storage and reports remain authoritative. No remote call occurs
  inside the import database transaction or a native financial transaction.
- Source files/downloads retain current ownership, permission and expiry controls.
  Pending native commands must remain recoverable even when original files expire.
- Native testing found that full readiness validation could exceed one file-wide
  request budget. Simple imports therefore validate and admit one independent row
  per request, recording VALIDATING / IMPORTING continuations. The UI continues
  automatically and can resume from history. Each request has a 60-second ceiling;
  normal shared imports retain their 30-second ceiling.
- The first commit checks the reviewed configuration digest. Accepted input remains
  immutable during admission; each subsequent row and native owner command rechecks
  current permissions and business policy. A configuration change before the first
  commit requires another validation. It does not strand already accepted commands.
- Catalog migration 0219 and Accounting migration 0233 expand the shared import
  state constraint, each with one ALTER. Downgrade refuses outstanding continuations.
  No product, price or stock table is changed by these migrations.
- Raw downloads still expire after 30 days. Input awaiting admission is retained
  until all accepted rows have durable owner commands; pending command history is
  excluded from the 365-day cleanup. Neither exception grants download authority.

## Delivered workflow

1. Products → Import products → choose Goods or Services and file format.
2. Download the current template; Excel includes instructions, fields and bounded
   reference-code options. Name and base unit are required. Code is optional; blank
   group uses Default. GST uses HSN/SAC and rule codes. Prices, MRP, Brand and Model
   follow configuration. Services have no opening columns.
3. Upload CSV, TSV or XLSX (up to 200 products, 16 files, 8 MiB combined), then
   Validate. Each row exercises native creation, price publication and activation
   inside a rollback. No product, price, opening or creation receipt is retained.
4. Correct errors using the flat correction file, preserving its row keys, upload
   a replacement revision and validate. Every revision and attempt is retained.
5. Review and Import once. Rows reserve generated codes and native commands, then
   automatically create, publish prices, activate and post Goods opening stock.
   Opening value is purchase price multiplied by quantity. The result becomes
   Ready only after the native workflow completes.
6. History shows product name/code, source row, readiness, opening-posted status,
   errors, attempts and files. Private result downloads include generated codes.
   Resume reuses existing owner receipts after a lost response or owner failure.
   Earlier draft-workflow history remains readable in Simple mode.

## Review findings fixed

- Draft-only templates and internal product-type/setup controls replaced for new
  Simple imports; advanced and historical definitions remain compatible.
- Pending commands no longer count as imported products. Inputs cannot be revised
  or cancelled after admission starts. Completed effects are never repeated.
- Gateway requests carry fresh Accounting/Vouchers financial policy context.
- Retained templates recheck native-column permissions before returning data.
- Native fields are reauthorized for history/downloads and after payload expiry.
- Flat corrections retain keys; failed row diagnostics survive later checkpoints.
- Long validation/admission uses durable continuations instead of a file-wide
  transaction that can time out. Prior successful validation is reused only while
  the current configuration fingerprint remains the same.
- Missing/duplicate reference codes have safe, actionable field messages.
- MRP validation refreshes pricing generation after creating numeric settings,
  matching the native creation sequence. Validation still rolls back all prices.
- Templates omit opening columns when purchase price is disabled: the Simple
  opening value requires purchase price multiplied by opening quantity.
- Result files distinguish product codes from diagnostic codes; historical
  validation results never claim that a later opening stock posting already happened.
- Historical messages resolve to file names and row numbers. Failed native rows
  yield to other pending products; automatic processing stops when only failed
  rows remain. Expired validation input cannot offer a misleading Resume action.
- The existing shared design system supplies layout, navigation and responsive
  tables; no app-specific CSS or visual constants were added.

## Local database update

On 2026-11-04, Catalog 0219 and Accounting 0233 were applied to the configured
local MySQL databases using the authorized DDL connection. Both schemas had zero
import jobs before and after the update. Existing schemas and data were retained;
only the import-state constraints and Alembic heads changed. DDL snapshots are
available in the ignored local `.tools` folder. Credentials were not written to
repository files.

## Verification and review

- Native MySQL Catalog: seven import scenarios passed in the end-to-end wrapper
  (three file formats, correction/history/isolation, Goods and Services GST, and
  uncertain opening creation recovery). Both MRP variants passed separately,
  including numeric-only pricing and migration downgrade/re-upgrade.
- Existing Catalog regression coverage: all 25 legacy import, Simple creation
  and Product Configuration review tests passed.
- Native Accounting: seven opening-stock workflow tests passed. The native
  migration round trip preserved the company opening row and verified model
  parity. All 13 existing Accounting import tests passed.
- Shared import framework: 34 tests passed, covering flat templates, retained
  authority, deferred effects, continuation replay, expiry and cleanup.
- UI: eight Simple import tests, 13 existing import UI tests, five configuration
  tests and 76 Product/Party proxy checks passed. Four browser scenarios checked
  48 layouts across 320/390/768/1440 widths and light/dark/ledger themes. New mobile
  and pending desktop screenshots were also visually reviewed.
- Focused Catalog tests passed for configuration-dependent columns and expiry
  controls. The priced-MRP validation timeout under concurrent test load was
  rechecked successfully on SQLite; both native MySQL variants also passed.
- Identity gateway context: five tests passed. API client: eight transport tests
  passed. OpenAPI/generated-client checks, TypeScript checks, targeted Ruff and
  strict mypy checks passed. Catalog migration checks passed (four tests; the
  Docker-only check was skipped, with isolated native MySQL exercised separately).
- Manual simplicity/security review covered tenant/company/actor isolation,
  current field authority, exact Decimal cost, private downloads, signed paging,
  immutable accepted inputs, idempotent owner commands and audit transactions.
  The `/simplify` and `/security-review` commands are unavailable in this session;
  their required checks were performed manually. Findings are recorded above.
- The temporary MySQL server on port 13398 was shut down after native checks;
  the configured local database server was left running.

## Findings before implementation

The existing Simple import uses the old aggregate-create schema, requires native
product type/internal setup, creates DRAFT products and does not publish prices or
post opening stock. Its generic controls also offer update and whole-file atomicity
that do not describe the requested new-product workflow. Existing file revisions,
validation attempts and private downloads provide reusable history infrastructure.
